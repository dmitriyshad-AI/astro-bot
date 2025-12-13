"""AI insights generation based on chart context."""

from __future__ import annotations

from typing import Any

from astro_bot import openai_client


HOUSE_NAMES = {
    "first_house": "1",
    "second_house": "2",
    "third_house": "3",
    "fourth_house": "4",
    "fifth_house": "5",
    "sixth_house": "6",
    "seventh_house": "7",
    "eighth_house": "8",
    "ninth_house": "9",
    "tenth_house": "10",
    "eleventh_house": "11",
    "twelfth_house": "12",
}


def build_context_from_chart(chart_payload: Any) -> str:
    """Compose plain-text context from stored chart payload (subject/aspects)."""
    if not chart_payload or not isinstance(chart_payload, dict):
        return ""

    subject = chart_payload.get("subject") or {}
    aspects = chart_payload.get("aspects") or []

    placements = []
    houses = []
    for key, data in subject.items():
        if not isinstance(data, dict):
            continue
        lower_key = key.lower()
        if "house" in lower_key:
            sign = data.get("sign")
            pos = data.get("position")
            if sign and pos is not None:
                house_num = HOUSE_NAMES.get(lower_key, key)
                houses.append(f"Дом {house_num}: {sign} {float(pos):.2f}°")
            continue
        sign = data.get("sign")
        pos = data.get("position")
        if sign is None or pos is None:
            continue
        name = data.get("name") or key
        house = data.get("house")
        retro = data.get("retrograde")
        house_text = f", дом {house}" if house else ""
        retro_text = " R" if retro else ""
        placements.append(f"{name}: {sign} {float(pos):.2f}°{house_text}{retro_text}")

    aspect_lines = []
    for asp in aspects:
        if not isinstance(asp, dict):
            continue
        p1 = asp.get("p1_name") or asp.get("p1")
        p2 = asp.get("p2_name") or asp.get("p2")
        aspect_name = asp.get("aspect")
        orbit = asp.get("orbit")
        if not (p1 and p2 and aspect_name and orbit is not None):
            continue
        aspect_lines.append(
            f"{p1} — {p2}: {aspect_name} (орб {abs(float(orbit)):.2f}°)"
        )

    parts = []
    if placements:
        parts.append("Планеты и точки:")
        parts.extend(placements)
    if houses:
        parts.append("Дома (куспиды):")
        parts.extend(houses)
    if aspect_lines:
        parts.append("Аспекты:")
        parts.extend(aspect_lines[:20])
    return "\n".join(parts)


def build_prompt(context_text: str) -> str:
    return (
        "Ты профессиональный астролог. Дай 5–7 кратких инсайтов на основе натальной карты. "
        "Не выдумывай позиции; опирайся только на данные ниже. Для каждого инсайта укажи, на чём он основан.\n\n"
        f"{context_text}"
    )


def generate_insights(context_text: str) -> dict:
    """Ask OpenAI for insights with the prepared context."""
    answer = openai_client.ask_gpt(build_prompt(context_text), role="астролог")
    return {"insights_text": answer}
