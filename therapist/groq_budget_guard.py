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

This guard covers two call sites today: the main chat call in
generate_ai_response(), and the fire-and-forget post-session memory
summarization in trigger_memory_update()/_generate_session_memory_summary()
(therapist/ai_model.py). The summarization call runs on a background thread
after the HTTP response is already sent, so a budget miss there just skips
that turn's memory update (memory_summary stays as it was) rather than
risking tipping the account over Groq's rate limit.
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

# Fallback lines shown when Luna can't reply (budget near the ceiling, or a
# Groq error). Be honest and warm: say plainly that Luna can't reply right
# now and invite them to try again. Never make a human excuse ("got
# distracted", "dropped my phone", "someone's talking to me irl"), and never
# sound like a system error ("server", "error", "rate limit"). Same casual
# voice as LUNA_SYSTEM_PROMPT. These are never saved to the journal.
# Rotated randomly so repeated hits don't feel canned.
BUDGET_EXCEEDED_MESSAGES = [
    "Luna can't reply right now, give me a minute and try again? 🌿",
    "sorry, Luna's a bit slow to reply right now. try again in a minute?",
    "can't answer just this second, send it again in a minute? 🌿",
]

# Arabic equivalents, gender-neutral by design (verbal-noun phrasing, no
# gendered imperatives) — no gender substitution needed.
BUDGET_EXCEEDED_MESSAGES_AR = [
    "لا تستطيع لونا الرد الآن، ممكن المحاولة مرة أخرى بعد دقيقة؟ 🌿",
    "لونا بطيئة قليلاً في الرد الآن، ممكن المحاولة بعد دقيقة؟",
    "لا تستطيع لونا الإجابة في هذه اللحظة، ممكن إرسالها مرة أخرى بعد قليل؟ 🌿",
]


def get_fallback_message(preferred_language=None):
    """Pick a random honest "Luna can't reply right now" line, in the
    requested language (anything other than 'ar' gets English — same
    missing/unrecognized-defaults-to-English behavior used elsewhere).
    Call this fresh each time so repeated hits don't feel canned."""
    messages = BUDGET_EXCEEDED_MESSAGES_AR if preferred_language == "ar" else BUDGET_EXCEEDED_MESSAGES
    return random.choice(messages)


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
    max_wait_seconds: float = 12,
    retry_interval: float = 1.5,
) -> bool:
    """
    Same contract as check_and_reserve_budget, but rides out momentary
    bursts instead of failing immediately: rechecks every retry_interval
    seconds until max_wait_seconds elapses. A request-heavy second that
    clears up shortly after should resolve silently rather than falling
    back to the "Luna can't reply right now" message.
    """
    deadline = time.time() + max_wait_seconds
    while True:
        if check_and_reserve_budget(estimated_prompt_tokens, estimated_response_tokens):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(retry_interval)
