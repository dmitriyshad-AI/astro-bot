"""Synastry (compatibility) calculation service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from kerykeion import ChartDataFactory, ChartDrawer

from astro_api import db, config
from astro_bot import natal_engine


def resolve_location(conn, query: str) -> natal_engine.LocationResult:
    """Reuse natal_service resolve logic (with cache)."""
    return natal_engine.resolve_location(query, conn)


def build_top_aspects(aspects, limit: int = 20, key_limit: int = 5):
    aspects_sorted = sorted(aspects, key=lambda a: abs(a.orbit))[:limit]
    top = [
        {
            "p1": a.p1_name,
            "p2": a.p2_name,
            "aspect": a.aspect,
            "orbit": a.orbit,
        }
        for a in aspects_sorted
    ]
    key_names = {"Sun", "Moon", "Venus", "Mars", "Ascendant"}
    key_aspects = [
        t
        for t in top
        if (t["p1"] in key_names or t["p2"] in key_names)
    ][:key_limit]
    return top, key_aspects


def calculate_compatibility(
    *,
    conn,
    user_id: Optional[str],
    self_birth_date: str,
    self_birth_time: Optional[str],
    self_place: str,
    partner_birth_date: str,
    partner_birth_time: Optional[str],
    partner_place: str,
    charts_dir: Optional[Path] = None,
) -> dict:
    charts_dir = charts_dir or (config.get_webapp_dist_dir().parent / "charts")
    charts_dir.mkdir(parents=True, exist_ok=True)
    natal_engine.cleanup_old_svgs(charts_dir)

    # Parse inputs
    self_date = natal_engine.parse_birth_date(self_birth_date)
    self_time = natal_engine.parse_birth_time(self_birth_time)
    partner_date = natal_engine.parse_birth_date(partner_birth_date)
    partner_time = natal_engine.parse_birth_time(partner_birth_time)

    self_loc = natal_engine.resolve_location(self_place, conn)
    partner_loc = natal_engine.resolve_location(partner_place, conn)

    # Build subjects under lock (Swiss Ephemeris is global)
    with natal_engine.natal_lock:
        self_subject = natal_engine.build_subject(
            name=user_id or "self",
            birth_date=self_date,
            birth_time=self_time,
            location=self_loc,
        )
        partner_subject = natal_engine.build_subject(
            name="partner",
            birth_date=partner_date,
            birth_time=partner_time,
            location=partner_loc,
        )
        synastry_data = ChartDataFactory.create_synastry_chart_data(
            self_subject,
            partner_subject,
            include_house_comparison=True,
            include_relationship_score=True,
        )
        drawer = ChartDrawer(chart_data=synastry_data)
        svg_path = drawer.save_svg(charts_dir / f"compat_{self_subject.julian_day}_{partner_subject.julian_day}.svg")

    top_aspects, key_aspects = build_top_aspects(synastry_data.aspects)
    score = None
    if getattr(synastry_data, "relationship_score", None):
        rs = synastry_data.relationship_score
        score = {
            "value": getattr(rs, "score_value", None),
            "description": getattr(rs, "score_description", None),
        }

    # Partner profile
    partner_profile_id = db.insert_profile(
        conn,
        telegram_user_id=None,
        label="Партнер",
        birth_date=self_date.isoformat(),  # self info
        birth_time=self_time.isoformat() if self_time else None,
        time_unknown=self_time is None,
        place_query=self_place,
        lat=self_loc.lat,
        lng=self_loc.lng,
        tz_str=self_loc.tz_str,
    )

    synastry_json = json.dumps(
        {
            "aspects": [a.model_dump() for a in synastry_data.aspects],
            "house_comparison": synastry_data.house_comparison.model_dump() if synastry_data.house_comparison else None,
        },
        ensure_ascii=False,
    )
    score_json = json.dumps(score, ensure_ascii=False) if score else None
    top_aspects_json = json.dumps({"top": top_aspects, "key": key_aspects}, ensure_ascii=False)

    comp_id = db.insert_compatibility(
        conn,
        user_id=user_id,
        self_profile_id=None,
        partner_profile_id=partner_profile_id,
        synastry_json=synastry_json,
        score_json=score_json,
        top_aspects_json=top_aspects_json,
        wheel_path=str(svg_path),
    )

    return {
        "id": comp_id,
        "score": score,
        "top_aspects": top_aspects,
        "key_aspects": key_aspects,
        "wheel_path": str(svg_path),
    }
