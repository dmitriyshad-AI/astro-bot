"""Натальная карта: геокодинг, расчёт и рендер SVG."""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence
from threading import Lock

import requests
from kerykeion import (
    AstrologicalSubjectFactory,
    ChartDataFactory,
    ChartDrawer,
    to_context,
)
from timezonefinder import TimezoneFinder

from astro_bot import config, repositories

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ACTIVE_POINTS: Sequence[str] = [
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "Mean_North_Lunar_Node",
    "Mean_South_Lunar_Node",
    "True_North_Lunar_Node",
    "True_South_Lunar_Node",
    "Ceres",
    "Pallas",
    "Juno",
    "Vesta",
    "Chiron",
    "Ascendant",
    "Medium_Coeli",
    "Descendant",
    "Imum_Coeli",
]
MAJOR_ASPECTS = {"conjunction", "opposition", "trine", "square", "sextile"}
CHART_CLEANUP_DAYS = 7

tz_finder = TimezoneFinder()
natal_lock = Lock()


class NatalError(Exception):
    """Общее исключение для расчёта натальной карты."""


@dataclass
class LocationResult:
    query: str
    display_name: str
    lat: float
    lng: float
    tz_str: str


@dataclass
class NatalResult:
    summary: str
    svg_path: Path
    context_text: str
    location: LocationResult


def cleanup_old_svgs(charts_dir: Path, days: int = CHART_CLEANUP_DAYS) -> None:
    """Удалить старые SVG-чарты."""
    if not charts_dir.exists():
        return
    cutoff = time.time() - days * 86400
    for path in charts_dir.glob("*.svg"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def parse_birth_date(date_str: str) -> dt.date:
    try:
        return dt.datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
    except ValueError as exc:
        raise NatalError("Дата должна быть в формате ДД.ММ.ГГГГ") from exc


def parse_birth_time(time_str: Optional[str]) -> Optional[dt.time]:
    if time_str is None:
        return None
    text = time_str.strip()
    if not text or text.casefold() in {"не знаю", "не помню", "нет", "неизвестно"}:
        return None
    try:
        return dt.datetime.strptime(text, "%H:%M").time()
    except ValueError as exc:
        raise NatalError("Время должно быть в формате ЧЧ:ММ или напишите «не знаю».") from exc


def resolve_location(query: str, conn) -> LocationResult:
    """Геокодинг места рождения с кэшем в БД."""
    norm_query = query.strip()
    if not norm_query:
        raise NatalError("Место рождения не задано.")

    cached = repositories.get_cached_location(conn, norm_query)
    if cached:
        return LocationResult(
            query=norm_query,
            display_name=cached["display_name"] or norm_query,
            lat=cached["lat"],
            lng=cached["lng"],
            tz_str=cached["tz_str"],
        )

    location = geocode_nominatim(norm_query)
    repositories.upsert_cached_location(
        conn,
        query=norm_query,
        lat=location.lat,
        lng=location.lng,
        tz_str=location.tz_str,
        display_name=location.display_name,
    )
    return location


def geocode_nominatim(query: str) -> LocationResult:
    """Запрос к Nominatim (с паузой <=1 rps) + определение таймзоны, c ретраями."""
    user_agent = config.get_user_agent()
    headers = {"User-Agent": user_agent}
    params = {"q": query, "format": "json", "limit": 1}

    last_exc = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(1 + attempt * 0.5)
        else:
            time.sleep(1.0)
        try:
            resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.Timeout as exc:
            last_exc = exc
            logger.warning("Timeout Nominatim for query=%s attempt=%s", query, attempt + 1)
            continue
        except requests.RequestException as exc:
            logger.exception("Ошибка геокодинга Nominatim")
            raise NatalError("Не удалось определить координаты. Попробуйте другое место.") from exc
    else:
        raise NatalError("Сервис геокодинга не ответил. Попробуйте ещё раз или уточните место.") from last_exc

    if not data:
        raise NatalError("Место не найдено. Уточните город/страну.")

    first = data[0]
    lat = float(first["lat"])
    lng = float(first["lon"])
    display_name = first.get("display_name", query)

    tz_str = tz_finder.timezone_at(lat=lat, lng=lng)
    if not tz_str:
        raise NatalError("Не удалось определить часовую зону для этого места.")

    return LocationResult(
        query=query,
        display_name=display_name,
        lat=lat,
        lng=lng,
        tz_str=tz_str,
    )


def build_subject(
    name: str,
    birth_date: dt.date,
    birth_time: Optional[dt.time],
    location: LocationResult,
):
    hour = birth_time.hour if birth_time else 12
    minute = birth_time.minute if birth_time else 0
    return AstrologicalSubjectFactory.from_birth_data(
        name=name,
        year=birth_date.year,
        month=birth_date.month,
        day=birth_date.day,
        hour=hour,
        minute=minute,
        lng=location.lng,
        lat=location.lat,
        tz_str=location.tz_str,
        houses_system_identifier="P",
        active_points=list(ACTIVE_POINTS),
        online=False,
    )


def render_svg(subject, charts_dir: Path, filename: str) -> Path:
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_data = ChartDataFactory.create_natal_chart_data(subject)
    drawer = ChartDrawer(chart_data)
    drawer.save_svg(output_path=charts_dir, filename=filename)
    return charts_dir / f"{filename}.svg"


def format_position(point) -> str:
    deg = int(point.position)
    minutes = int(round((point.position - deg) * 60))
    return f"{point.sign} {deg:02d}°{minutes:02d}'"


def format_house(point, idx: int) -> str:
    return f"Дом {idx}: {format_position(point)}"


def format_point(point) -> str:
    retro = " R" if point.retrograde else ""
    return f"{point.name.replace('_', ' ')}: {format_position(point)} (дом {pretty_house(point.house)}){retro}"


def pretty_house(house_name: Optional[str]) -> str:
    if not house_name:
        return "-"
    mapping = {
        "First_House": "1",
        "Second_House": "2",
        "Third_House": "3",
        "Fourth_House": "4",
        "Fifth_House": "5",
        "Sixth_House": "6",
        "Seventh_House": "7",
        "Eighth_House": "8",
        "Ninth_House": "9",
        "Tenth_House": "10",
        "Eleventh_House": "11",
        "Twelfth_House": "12",
    }
    return mapping.get(house_name, house_name)


def format_aspect(aspect_obj) -> str:
    name_map = {
        "conjunction": "Соединение",
        "opposition": "Оппозиция",
        "trine": "Тригон",
        "square": "Квадрат",
        "sextile": "Секстиль",
    }
    asp = aspect_obj.aspect
    name = name_map.get(asp, asp.title())
    orb = round(abs(aspect_obj.orbit), 2)
    return f"{aspect_obj.p1_name} — {aspect_obj.p2_name}: {name} (орб {orb}°)"


def build_summary(subject, aspects, location: LocationResult, birth_date: dt.date, birth_time: Optional[dt.time]) -> str:
    time_part = birth_time.strftime("%H:%M") if birth_time else "неизвестно"
    header = (
        f"Натальная карта\n"
        f"Дата: {birth_date.strftime('%d.%m.%Y')}, Время: {time_part}\n"
        f"Место: {location.display_name}\n"
        f"Система домов: Placidus\n"
    )

    angles = [
        subject.ascendant,
        subject.medium_coeli,
        subject.descendant,
        subject.imum_coeli,
    ]
    angles_labels = ["Asc", "MC", "Desc", "IC"]
    angles_lines = [
        f"{label}: {format_position(point)} (дом {pretty_house(point.house)})"
        for label, point in zip(angles_labels, angles)
    ]

    houses = [
        subject.first_house,
        subject.second_house,
        subject.third_house,
        subject.fourth_house,
        subject.fifth_house,
        subject.sixth_house,
        subject.seventh_house,
        subject.eighth_house,
        subject.ninth_house,
        subject.tenth_house,
        subject.eleventh_house,
        subject.twelfth_house,
    ]
    house_lines = [format_house(h, idx) for idx, h in enumerate(houses, 1)]

    points_attrs = [
        "sun",
        "moon",
        "mercury",
        "venus",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
        "chiron",
        "mean_north_lunar_node",
        "true_north_lunar_node",
        "mean_south_lunar_node",
        "true_south_lunar_node",
        "ceres",
        "pallas",
        "juno",
        "vesta",
        "ascendant",
        "medium_coeli",
        "descendant",
        "imum_coeli",
    ]
    point_lines = []
    for attr in points_attrs:
        point = getattr(subject, attr, None)
        if point:
            point_lines.append(format_point(point))

    filtered_aspects = [
        a for a in aspects if a.aspect in MAJOR_ASPECTS
    ]
    filtered_aspects.sort(key=lambda a: abs(a.orbit))
    aspect_lines = [format_aspect(a) for a in filtered_aspects[:20]]

    parts = [
        header,
        "Углы:",
        "\n".join(angles_lines),
        "Дома:",
        "\n".join(house_lines),
        "Планеты и точки:",
        "\n".join(point_lines),
        "Аспекты:",
        "\n".join(aspect_lines) if aspect_lines else "нет точных аспектов",
    ]
    return "\n".join(parts)


def generate_natal_chart(
    *,
    birth_date_str: str,
    birth_time_str: Optional[str],
    place_query: str,
    db_conn,
    user_identifier: str,
    charts_dir: Optional[Path] = None,
) -> NatalResult:
    charts_dir = charts_dir or config.get_charts_dir()
    cleanup_old_svgs(charts_dir, CHART_CLEANUP_DAYS)

    birth_date = parse_birth_date(birth_date_str)
    birth_time = parse_birth_time(birth_time_str)
    location = resolve_location(place_query, db_conn)
    with natal_lock:
        subject = build_subject(
            name=user_identifier,
            birth_date=birth_date,
            birth_time=birth_time,
            location=location,
        )
        svg_path = render_svg(subject, charts_dir, f"natal_{user_identifier}_{int(time.time())}")
        chart_data = ChartDataFactory.create_natal_chart_data(subject)
        summary = build_summary(subject, chart_data.aspects, location, birth_date, birth_time)
        context_text = to_context(subject)
    return NatalResult(summary=summary, svg_path=svg_path, context_text=context_text, location=location)


def generate_natal_chart_from_location(
    *,
    birth_date: dt.date,
    birth_time: Optional[dt.time],
    lat: float,
    lng: float,
    tz_str: str,
    place_label: str,
    user_identifier: str,
    charts_dir: Optional[Path] = None,
) -> NatalResult:
    charts_dir = charts_dir or config.get_charts_dir()
    cleanup_old_svgs(charts_dir, CHART_CLEANUP_DAYS)

    location = LocationResult(
        query=place_label,
        display_name=place_label,
        lat=lat,
        lng=lng,
        tz_str=tz_str,
    )
    with natal_lock:
        subject = build_subject(
            name=user_identifier,
            birth_date=birth_date,
            birth_time=birth_time,
            location=location,
        )
        svg_path = render_svg(subject, charts_dir, f"natal_{user_identifier}_{int(time.time())}")
        chart_data = ChartDataFactory.create_natal_chart_data(subject)
        summary = build_summary(subject, chart_data.aspects, location, birth_date, birth_time)
        context_text = to_context(subject)
    return NatalResult(summary=summary, svg_path=svg_path, context_text=context_text, location=location)
