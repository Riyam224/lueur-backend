import hashlib
import os
import time

import requests
from django.core.cache import cache

from .crisis import contains_crisis_language
from .groq_budget_guard import (
    check_and_reserve_budget_with_retry,
    estimate_tokens,
    get_fallback_message,
)
from .luna_prompts import LunaPromptProvider

WEEKLY_LETTER_CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours
HISTORY_WINDOW = 8

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_TIMEOUT = (5, 15)  # (connect, read) seconds
GROQ_MAX_ATTEMPTS = 2
GROQ_RETRY_BACKOFF_SECONDS = 1


def _call_groq(payload):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(GROQ_MAX_ATTEMPTS):
        try:
            response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=GROQ_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            last_error = exc
            if attempt < GROQ_MAX_ATTEMPTS - 1:
                time.sleep(GROQ_RETRY_BACKOFF_SECONDS)

    raise last_error


def generate_ai_response(emoji, thoughts, history=None, preferred_language=None, gender=None):
    if contains_crisis_language(thoughts):
        # Currently unreachable: views.py already runs its own (bilingual)
        # crisis check and returns before ever calling this function. Kept
        # correct defensively — localized/gendered like views.py's crisis
        # path, in case a future caller reaches generate_ai_response()
        # without doing its own crisis check first.
        return LunaPromptProvider.get_crisis_response(preferred_language, gender)

    history = (history or [])[-HISTORY_WINDOW:]
    system_prompt = LunaPromptProvider.get_system_prompt(preferred_language, gender)

    prompt_tokens = estimate_tokens(system_prompt + str(history) + thoughts)
    if not check_and_reserve_budget_with_retry(prompt_tokens):
        return get_fallback_message(preferred_language)

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.85,  # more natural, less robotic
        "max_tokens": 180,  # keeps responses short
        "top_p": 0.9,  # more varied word choices
        "frequency_penalty": 0.6,  # prevents Luna repeating herself
        "presence_penalty": 0.5,  # encourages fresh responses each turn
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            *history,
            {
                "role": "user",
                "content": f"Emoji: {emoji}\nThoughts: {thoughts}",
            },
        ],
    }
    return _call_groq(payload)


def _weekly_letter_cache_key(formatted_entries, entries_count, dominant_emoji, preferred_language, gender):
    # preferred_language/gender are part of the key because they change the
    # rendered prompt — without this, a cached English letter could be
    # served to a user who prefers Arabic (or vice versa).
    raw = f"{formatted_entries}|{entries_count}|{dominant_emoji}|{preferred_language}|{gender}".encode()
    return "groq:weekly_letter:" + hashlib.sha256(raw).hexdigest()


def generate_weekly_letter(
    formatted_entries, entries_count, dominant_emoji, preferred_language=None, gender=None
):
    cache_key = _weekly_letter_cache_key(
        formatted_entries, entries_count, dominant_emoji, preferred_language, gender
    )
    cached_letter = cache.get(cache_key)
    if cached_letter is not None:
        return cached_letter

    system_prompt = LunaPromptProvider.get_weekly_letter_prompt(preferred_language, gender)
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": f"Entries:\n{formatted_entries}\nCount: {entries_count}\nDominant: {dominant_emoji}",
            },
        ],
    }
    letter = _call_groq(payload)
    cache.set(cache_key, letter, timeout=WEEKLY_LETTER_CACHE_TIMEOUT)
    return letter
