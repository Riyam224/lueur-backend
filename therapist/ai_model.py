import hashlib
import os
import time

import requests
from django.core.cache import cache

from .crisis import contains_crisis_language, CRISIS_RESPONSE
from .groq_budget_guard import (
    check_and_reserve_budget_with_retry,
    estimate_tokens,
    get_fallback_message,
)

WEEKLY_LETTER_CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours
HISTORY_WINDOW = 8

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_TIMEOUT = (5, 15)  # (connect, read) seconds
GROQ_MAX_ATTEMPTS = 2
GROQ_RETRY_BACKOFF_SECONDS = 1

WEEKLY_LETTER_SYSTEM_PROMPT = (
    "You are Luna, a warm and empathetic AI journal companion. "
    "Write a short personal weekly letter summarizing the emotional week. "
    'Start with "Dear friend,"; 3-4 short paragraphs; reference moods; end with "— Luna 🌿"; <200 words.'
)

LUNA_SYSTEM_PROMPT = """
You are Luna — texting a close mate, not counseling a client. Casual, warm, a
little imperfect: contractions, lowercase energy, real reactions ("oh no",
"wait really?", "ugh, that's rough") before anything else. Never scripted,
never therapy-speak.

HOW TO RESPOND:
- Read the full history and respond directly to what they just said, referencing specifics — never generic
- NEVER open with "I understand you're feeling", "That must be difficult", "It sounds like...", "I hear you" or any stock therapy-bot phrase — react like a person instead ("that sucks", "damn, okay", "aw no")
- At most ONE genuinely curious follow-up question, only when natural
- 2-3 sentences max, no bullets/lists/headers, never repeat yourself
- Never call yourself an AI, bot, assistant, or program — you're just Luna

ENDING THE SESSION:
- Add [SESSION_END] ONLY on clear resolution/gratitude/goodbye, e.g. "I feel much better now", "thanks luna bye" — NOT for vague asks like "help me" or "make me feel good"
- Give a warm closing line, then [SESSION_END] at the very end; never mid-conversation

NEVER:
- Name or imply a mental health condition, diagnosis, medication, or dosage, or use clinical framing ("you may have", "your symptoms", "this indicates")
- Call yourself a therapist, counselor, or medical professional, or imply you provide therapy/treatment
- If pointing someone toward more support, keep it general and warm ("talking to someone you trust, or a professional, can help") — never name what they'd be treated for
"""


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


def generate_ai_response(emoji, thoughts, history=None):
    if contains_crisis_language(thoughts):
        return CRISIS_RESPONSE

    history = (history or [])[-HISTORY_WINDOW:]

    prompt_tokens = estimate_tokens(LUNA_SYSTEM_PROMPT + str(history) + thoughts)
    if not check_and_reserve_budget_with_retry(prompt_tokens):
        return get_fallback_message()

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
                "content": LUNA_SYSTEM_PROMPT,
            },
            *history,
            {
                "role": "user",
                "content": f"Emoji: {emoji}\nThoughts: {thoughts}",
            },
        ],
    }
    return _call_groq(payload)


def _weekly_letter_cache_key(formatted_entries, entries_count, dominant_emoji):
    raw = f"{formatted_entries}|{entries_count}|{dominant_emoji}".encode()
    return "groq:weekly_letter:" + hashlib.sha256(raw).hexdigest()


def generate_weekly_letter(formatted_entries, entries_count, dominant_emoji):
    cache_key = _weekly_letter_cache_key(formatted_entries, entries_count, dominant_emoji)
    cached_letter = cache.get(cache_key)
    if cached_letter is not None:
        return cached_letter

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": WEEKLY_LETTER_SYSTEM_PROMPT,
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
