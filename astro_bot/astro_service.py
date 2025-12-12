"""Сервис генерации текста натальной карты через OpenAI."""

from __future__ import annotations

from typing import Optional

from astro_bot import openai_client


def generate_natal_report(
    *,
    birth_date: str,
    birth_time: Optional[str],
    birth_place: str,
) -> str:
    """Сформировать текстовый разбор натальной карты."""
    time_info = birth_time if birth_time else "время неизвестно"
    prompt = (
        "Составь краткий, дружелюбный астрологический профиль по данным рождения. "
        "Избегай сложного жаргона, дай 3-4 пункта про характер/ресурсы и 2-3 практических совета. "
        f"Дата: {birth_date}; Время: {time_info}; Место: {birth_place}."
    )
    return openai_client.ask_gpt(prompt, role="астролог")
