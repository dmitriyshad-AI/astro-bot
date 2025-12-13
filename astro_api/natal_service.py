"""Natal calculation service for API using existing natal_engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from kerykeion import ChartDataFactory, to_context

from astro_api import db, config
from astro_bot import natal_engine
from astro_bot import openai_client


def resolve_location(conn, query: str) -> natal_engine.LocationResult:
    """Resolve location with cache; use Nominatim if not cached."""
    norm_query = query.strip()
    if not norm_query:
        raise natal_engine.NatalError("Место рождения не задано.")
    cached = db.get_cached_location(conn, norm_query)
    if cached:
        return natal_engine.LocationResult(
            query=norm_query,
            display_name=cached["display_name"] or norm_query,
            lat=cached["lat"],
            lng=cached["lng"],
            tz_str=cached["tz_str"],
        )
    location = natal_engine.geocode_nominatim(norm_query)
    db.upsert_cached_location(
        conn,
        query=norm_query,
        lat=location.lat,
        lng=location.lng,
        tz_str=location.tz_str,
        display_name=location.display_name,
    )
    return location


def build_chart_payload(chart_data, location: natal_engine.LocationResult, birth_date, birth_time):
    """Prepare chart JSON payload."""
    subject_dump = chart_data.subject.model_dump()
    aspects_dump = [a.model_dump() for a in chart_data.aspects]
    return {
        "subject": subject_dump,
        "aspects": aspects_dump,
        "location": {
            "display_name": location.display_name,
            "lat": location.lat,
            "lng": location.lng,
            "tz_str": location.tz_str,
        },
        "birth_date": birth_date.isoformat(),
        "birth_time": birth_time.isoformat() if birth_time else None,
    }


def calculate_natal_chart(
    *,
    conn,
    birth_date_str: str,
    birth_time_str: Optional[str],
    place_query: str,
    user_identifier: str,
    charts_dir: Optional[Path] = None,
    telegram_user_id: Optional[int] = None,
    label: Optional[str] = None,
) -> dict:
    """Full cycle: parse, geocode, compute, save profile+chart, return data."""
    charts_dir = charts_dir or natal_engine.config.get_charts_dir()
    natal_engine.cleanup_old_svgs(charts_dir)

    birth_date = natal_engine.parse_birth_date(birth_date_str)
    birth_time = natal_engine.parse_birth_time(birth_time_str)
    location = resolve_location(conn, place_query)

    # Check for existing profile/chart
    existing_profile = db.find_profile(
        conn,
        telegram_user_id=telegram_user_id,
        birth_date=birth_date.isoformat(),
        birth_time=birth_time.isoformat() if birth_time else None,
        time_unknown=birth_time is None,
        place_query=place_query,
        lat=location.lat,
        lng=location.lng,
        tz_str=location.tz_str,
    )
    if existing_profile:
        chart_row = db.get_latest_chart_for_profile(conn, existing_profile["id"])
        if chart_row:
            return {
                "chart_id": chart_row["id"],
                "profile_id": existing_profile["id"],
                "summary": chart_row["summary"] or "",
                "context_text": "",
                "wheel_path": chart_row["wheel_path"],
                "chart": json.loads(chart_row["chart_json"]),
                "location": {
                    "display_name": location.display_name,
                    "lat": location.lat,
                    "lng": location.lng,
                    "tz_str": location.tz_str,
                },
            }

    # Build subject and chart data under lock inside natal_engine
    subject = natal_engine.build_subject(
        name=user_identifier,
        birth_date=birth_date,
        birth_time=birth_time,
        location=location,
    )
    chart_data = ChartDataFactory.create_natal_chart_data(subject)
    summary = natal_engine.build_summary(subject, chart_data.aspects, location, birth_date, birth_time)
    context_text = to_context(subject)
    svg_path = natal_engine.render_svg(
        subject, charts_dir, f"natal_{user_identifier}_{chart_data.subject.julian_day}"
    )

    llm_summary = None
    if config.get_openai_api_key():
        prompt = (
            "Ты профессиональный астролог. Объясни натальную карту простым языком для новичка. "
            "Сделай 5–7 коротких пунктов: основные черты, сильные стороны, зоны роста. "
            "Избегай жаргона, не пиши градусы/аспекты. Каждый пункт закончи строкой 'Основано на: ...' "
            "со ссылкой на факт (Солнце в X, Луна в Y, дом, аспект). "
            "В конце сделай самопроверку одной строкой: 'Проверка: все пункты опираются на перечисленные факты, без выдумок'. "
            "Используй только факты из контекста ниже.\n\n"
            f"{context_text}"
        )
        try:
            llm_summary = openai_client.ask_gpt(prompt, role="астролог")
        except Exception:
            llm_summary = None

    profile_id = db.insert_profile(
        conn,
        telegram_user_id=telegram_user_id,
        label=label,
        birth_date=birth_date.isoformat(),
        birth_time=birth_time.isoformat() if birth_time else None,
        time_unknown=birth_time is None,
        place_query=place_query,
        lat=location.lat,
        lng=location.lng,
        tz_str=location.tz_str,
    )

    chart_payload = build_chart_payload(chart_data, location, birth_date, birth_time)
    chart_json = json.dumps(chart_payload, ensure_ascii=False)
    chart_id = db.insert_chart(
        conn,
        profile_id=profile_id,
        chart_json=chart_json,
        wheel_path=str(svg_path),
        summary=summary,
        llm_summary=llm_summary,
    )

    return {
        "chart_id": chart_id,
        "profile_id": profile_id,
        "summary": summary,
        "llm_summary": llm_summary,
        "context_text": context_text,
        "wheel_path": str(svg_path),
        "chart": chart_payload,
        "location": {
            "display_name": location.display_name,
            "lat": location.lat,
            "lng": location.lng,
            "tz_str": location.tz_str,
        },
    }
