import re

CRISIS_KEYWORDS = [
    "kill myself", "killing myself", "suicide", "suicidal", "end my life",
    "want to die", "wanna die", "unalive", "don't want to be here",
    "dont want to be here", "do not want to be here", "hurt myself", "self harm", "self-harm",
    "no reason to live", "better off dead", "can't go on", "ending it all",
]
# Short slang that would match inside unrelated words, so it needs word
# boundaries ("kms" = "kill myself").
CRISIS_KEYWORDS_WORD_BOUNDARY = ["kms"]

_CRISIS_PATTERN = re.compile(
    r"|".join(
        [re.escape(k) for k in CRISIS_KEYWORDS]
        + [rf"\b{re.escape(k)}\b" for k in CRISIS_KEYWORDS_WORD_BOUNDARY]
    ),
    re.IGNORECASE,
)

# Deliberately narrow: these exact phrases are removed before matching, so
# they can't trip a keyword on their own, but any other crisis phrase in the
# same message is still caught. Do not add broad negation handling here — a
# missed crisis message is worse than a false alarm.
_SAFE_PHRASES_PATTERN = re.compile(
    r"\b(?:don't|dont|do not)\s+want\s+to\s+die\b|\bsuicide\s+squad\b",
    re.IGNORECASE,
)


def _normalize(text):
    # Phone keyboards send curly apostrophes ("can’t"); collapse whitespace
    # so "want  to die" still matches.
    return " ".join(text.replace("’", "'").replace("‘", "'").split())


CRISIS_RESPONSE = (
    "Hey, I'm really glad you told me. This is a lot to hold on your own, and "
    "you deserve real people with you right now, more than I can be from here. "
    "They can help straight away:\n\n"
    "• US: call or text 988 (Suicide & Crisis Lifeline)\n"
    "• Anywhere else: https://findahelpline.com\n\n"
    "If you're in danger right now, please call your local emergency number. "
    "I'm still here whenever you want to keep talking 🌿"
)


def contains_crisis_language(text: str) -> bool:
    if not text:
        return False
    text = _SAFE_PHRASES_PATTERN.sub(" ", _normalize(text))
    return bool(_CRISIS_PATTERN.search(text))
