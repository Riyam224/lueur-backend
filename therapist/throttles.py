from rest_framework.throttling import UserRateThrottle


class LunaChatRateThrottle(UserRateThrottle):
    """Per-user cap on chat generation calls, independent of the existing
    'ai_generate' scope — protects the shared Groq free-tier budget from
    any single user's burst rather than measuring overall endpoint traffic."""

    scope = "luna_chat"
