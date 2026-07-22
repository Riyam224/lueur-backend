"""
groq_budget_guard.py

Lightweight, dependency-free guard to keep Lueur inside Groq's Free tier
limits (30 requests/min, 14,400 requests/day, 6,000 tokens/min for
llama-3.1-8b-instant as of writing) without needing Redis or Celery.

Uses Django's cache framework as the counter store. Works out of the box
with LocMemCache (Django's default) for a single-process Railway deploy.
If you ever scale to multiple workers/dynos, swap CACHES to a shared
backend (e.g. Railway's Redis add-on) — LocMemCache counters don't share
state across processes.

Drop this file into your `therapist` app (or `core`), then wire it into
groq_client.py as shown at the bottom of this file.
"""

import random
import time
from datetime import date

from django.core.cache import cache

# ---- Groq Free tier limits (leave headroom — don't run to the exact edge) ----
LIMIT_REQUESTS_PER_MINUTE = 30
LIMIT_REQUESTS_PER_DAY = 14_400
LIMIT_TOKENS_PER_MINUTE = 6_000

# Safety margins: stop ourselves before we actually hit Groq's ceiling,
# so a burst of a few extra requests doesn't tip us into a hard 429.
SAFE_REQUESTS_PER_MINUTE = int(LIMIT_REQUESTS_PER_MINUTE * 0.8)   # 24
SAFE_REQUESTS_PER_DAY = int(LIMIT_REQUESTS_PER_DAY * 0.9)          # ~12,960
SAFE_TOKENS_PER_MINUTE = int(LIMIT_TOKENS_PER_MINUTE * 0.8)        # 4,800

# Fallback lines for when we're near the ceiling. These must NEVER reveal
# there's any system/infrastructure behind Luna — no "I'm getting a lot of
# messages", no "server", no "try again in a minute" framing. A real friend
# just seems distracted, mid-something-else, or slow to type back — never
# explains a technical reason. Keep these consistent with LUNA_SYSTEM_PROMPT's
# voice: casual, lowercase energy, texting-style, never a stock phrase.
# Rotated randomly so repeated hits in the same session don't feel canned.
BUDGET_EXCEEDED_MESSAGES = [
    "wait sorry, got distracted for a sec — say that again? 👀",
    "omg my bad, totally spaced out there. what were you saying?",
    "hang on, someone's talking to me irl lol. one sec",
    "ugh sorry, dropped my phone mid-scroll 😭 go on though",
    "wait what, sorry i zoned out. tell me again?",
    "hold that thought, brb 2 sec",
]


def get_fallback_message():
    """Pick a random in-character 'distracted friend' line. Call this
    fresh each time you need a fallback — never cache/reuse a single
    instance, since repetition is what breaks the illusion."""
    return random.choice(BUDGET_EXCEEDED_MESSAGES)


def _minute_bucket():
    return int(time.time() // 60)


def _day_bucket():
    return date.today().isoformat()


def estimate_tokens(text):
    """
    Rough, dependency-free token estimate (~4 chars per token for English).
    Good enough for a soft budget check — we don't need tiktoken-level
    precision, just enough to avoid blowing the TPM ceiling.
    """
    return max(1, len(text) // 4)


def check_and_reserve_budget(estimated_prompt_tokens: int, estimated_response_tokens: int = 180) -> bool:
    """
    Call this BEFORE making a Groq request. Returns True if it's safe to
    proceed, False if we're near the ceiling and should show the fallback
    message instead of calling Groq at all.

    On True, this also increments the counters (i.e. "reserves" the budget),
    so call it exactly once per actual Groq call you intend to make.
    """
    minute_key = f"groq:reqs:min:{_minute_bucket()}"
    day_key = f"groq:reqs:day:{_day_bucket()}"
    tokens_key = f"groq:tokens:min:{_minute_bucket()}"

    current_minute_reqs = cache.get(minute_key, 0)
    current_day_reqs = cache.get(day_key, 0)
    current_minute_tokens = cache.get(tokens_key, 0)

    projected_tokens = current_minute_tokens + estimated_prompt_tokens + estimated_response_tokens

    if current_minute_reqs >= SAFE_REQUESTS_PER_MINUTE:
        return False
    if current_day_reqs >= SAFE_REQUESTS_PER_DAY:
        return False
    if projected_tokens >= SAFE_TOKENS_PER_MINUTE:
        return False

    # Reserve — increment with appropriate expiry so buckets self-clean.
    cache.set(minute_key, current_minute_reqs + 1, timeout=65)
    cache.set(day_key, current_day_reqs + 1, timeout=60 * 60 * 26)
    cache.set(tokens_key, projected_tokens, timeout=65)

    return True


def check_and_reserve_budget_with_retry(
    estimated_prompt_tokens: int,
    estimated_response_tokens: int = 180,
    max_wait_seconds: float = 4,
    retry_interval: float = 1.5,
) -> bool:
    """
    Same contract as check_and_reserve_budget, but rides out momentary
    bursts instead of failing immediately: rechecks every retry_interval
    seconds until max_wait_seconds elapses. A request-heavy second that
    clears up shortly after should resolve silently rather than falling
    back to the "distracted friend" message.
    """
    deadline = time.time() + max_wait_seconds
    while True:
        if check_and_reserve_budget(estimated_prompt_tokens, estimated_response_tokens):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(retry_interval)


def get_budget_status():
    """Optional: surface current usage, e.g. for an admin dashboard widget."""
    minute_key = f"groq:reqs:min:{_minute_bucket()}"
    day_key = f"groq:reqs:day:{_day_bucket()}"
    tokens_key = f"groq:tokens:min:{_minute_bucket()}"

    return {
        "requests_this_minute": cache.get(minute_key, 0),
        "requests_today": cache.get(day_key, 0),
        "tokens_this_minute": cache.get(tokens_key, 0),
        "limits": {
            "requests_per_minute": SAFE_REQUESTS_PER_MINUTE,
            "requests_per_day": SAFE_REQUESTS_PER_DAY,
            "tokens_per_minute": SAFE_TOKENS_PER_MINUTE,
        },
    }


# -----------------------------------------------------------------------------
# INTEGRATION — how to wire this into your existing groq_client.py
# -----------------------------------------------------------------------------
#
# from .groq_budget_guard import check_and_reserve_budget_with_retry, estimate_tokens, get_fallback_message
#
# def generate_ai_response(emoji, thoughts, history=None):
#     if contains_crisis_language(thoughts):
#         return CRISIS_RESPONSE
#
#     history = history or []
#
#     # Rough estimate of prompt size: system prompt + history + this message
#     prompt_text = LUNA_SYSTEM_PROMPT + str(history) + thoughts
#     prompt_tokens = estimate_tokens(prompt_text)
#
#     if not check_and_reserve_budget_with_retry(prompt_tokens):
#         return get_fallback_message()   # in-character, never reveals a system limit
#
#     payload = { ... same as before ... }
#     return _call_groq(payload)
