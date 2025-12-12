"""Обертка для запросов к OpenAI Chat Completions API."""

from __future__ import annotations

import logging
from typing import Optional

import requests

from astro_bot import config

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIError(Exception):
    """Базовая ошибка работы с OpenAI API."""


def ask_gpt(question: str, role: str = "астролог/коуч/психолог") -> str:
    """
    Отправить вопрос в OpenAI и вернуть ответ.

    :param question: текст вопроса пользователя
    :param role: стиль ответа
    """
    api_key = config.get_openai_api_key()
    if not api_key:
        raise OpenAIError("Не задан OPENAI_API_KEY")

    model = config.get_openai_model()
    temperature = config.get_openai_temperature()

    system_prompt = (
        "Ты отвечаешь как дружелюбный астролог/коуч/психолог. "
        "Давай краткие, понятные ответы без сложного жаргона."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Стиль: {role}. Вопрос: {question}"},
        ],
    }

    try:
        response = requests.post(OPENAI_URL, json=payload, headers=headers, timeout=30)
    except requests.RequestException as exc:
        logger.exception("Ошибка сети при обращении к OpenAI")
        raise OpenAIError(f"Ошибка сети: {exc}") from exc

    if response.status_code != 200:
        logger.error("OpenAI вернул статус %s: %s", response.status_code, response.text)
        raise OpenAIError(f"Ошибка OpenAI: {response.status_code}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        logger.exception("Неожиданный формат ответа OpenAI: %s", data)
        raise OpenAIError("Неожиданный ответ OpenAI") from exc
