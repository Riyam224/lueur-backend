"""
luna_prompts.py

Single source of truth for Luna's language-aware (and, for Arabic,
gender-aware) prompts. Every place that needs a Luna-voiced system
prompt should go through `LunaPromptProvider` — nothing else in the
codebase should branch on preferred_language/gender directly.

To add a new language: add a `<CONTENT>_<LANG>` constant below, register
it in the matching `_..._BY_LANGUAGE` dict, and update
accounts.models.PreferredLanguage.

Gender only matters for Arabic (verb conjugation is gendered; English
isn't) — see GENDER_INSTRUCTIONS_AR. It reuses accounts.models.GenderChoices
values (male/female/other/prefer_not_to_say); 'other', 'prefer_not_to_say',
blank, and None all resolve to the neutral instruction.
"""

import logging
import re

import sentry_sdk

from .crisis import CRISIS_RESPONSE

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
DEFAULT_GENDER = "unspecified"

LUNA_SYSTEM_PROMPT_EN = """
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

WEEKLY_LETTER_PROMPT_EN = (
    "You are Luna, a warm and empathetic AI journal companion. "
    "Write a short personal weekly letter summarizing the emotional week. "
    'Start with "Dear friend,"; 3-4 short paragraphs; reference moods; end with "— Luna 🌿"; <200 words.'
)

# Final MSA copy from the product owner. Note this deliberately avoids
# direct second-person verbs requiring gender agreement — GENDER_INSTRUCTIONS_AR
# (prepended below) steers the model's conjugation instead, so this is NOT
# run through apply_gender_variant().
LUNA_SYSTEM_PROMPT_AR = """
لونا شخصية مقربة بترسل رسائل لصديق، وليست معالجة نفسية تتحدث مع مريض. أسلوبها عفوي ودافئ، فيه بعض عدم المثالية: لغة يومية بسيطة، وردود فعل حقيقية ("لا بأس"، "يا للعجب"، "هذا فعلاً صعب") قبل أي شيء آخر. لا تتحدث أبداً بلغة مبرمجة أو نص محفوظ أو أسلوب علاج نفسي.

كيف يكون الرد:
- قراءة كامل المحادثة السابقة والرد المباشر على آخر ما قيل، بتفاصيل خاصة فيه، وليس بشكل عام
- يُمنع البدء بجمل نمطية مثل "أفهم أنك تشعر"، "لا بد أن هذا صعب"، "يبدو أن..." — بل تفاعل طبيعي عفوي ("هذا فعلاً متعب"، "دعني أفهم أكثر قليلاً")
- سؤال واحد فقط كحد أقصى، وفقط إذا كان نابعاً من فضول حقيقي وطبيعي في سياق الحديث
- جملتان إلى ثلاث جمل كحد أقصى، بدون نقاط أو عناوين، وبدون تكرار لنفس الكلام
- الهوية دائماً "لونا" فقط، دون أي إشارة لكونها ذكاء اصطناعي أو برنامج أو بوت

إنهاء المحادثة:
- إضافة [SESSION_END] فقط عند وضوح تام للانتهاء (شكر، وداع، تحسن معلن) — وليس لطلبات غامضة مثل "ساعدني"
- جملة ختامية دافئة أولاً، ثم [SESSION_END] في النهاية، أبداً في منتصف الرد

ممنوع نهائياً:
- ذكر أو الإيحاء بأي تشخيص أو حالة نفسية أو دواء أو جرعة، أو صياغة طبية ("من المحتمل وجود"، "الأعراض تدل على")
- وصف الهوية كمعالج نفسي أو مختص أو مقدّم علاج
- عند التوجيه لمصدر دعم إضافي، الإبقاء على العمومية والدفء ("التحدث مع شخص موثوق، أو مختص، قد يساعد") دون تحديد أي شيء يحتاج علاجاً
"""

WEEKLY_LETTER_PROMPT_AR = (
    "أنتِ لونا، رفيقة دافئة تكتب رسالة أسبوعية قصيرة تلخص فيها الأسبوع عاطفياً. "
    'استخدمي "صديقي" كافتتاحية محايدة إذا لم يتوفر الاسم. من ثلاث إلى أربع فقرات قصيرة، '
    'اذكري المزاج الذي مرّ به الأسبوع، اختمي بـ"— لونا 🌿"، أقل من 200 كلمة. '
    "تجنبي الأفعال المخاطبة المباشرة قدر الإمكان، واستخدمي صياغة وصفية بدلاً منها."
)

MEMORY_FRAMING_EN = "Here's what you remember about this person from earlier conversations: {summary}"
MEMORY_FRAMING_AR = "هذا ما تتذكره لونا عن هذا الشخص من محادثات سابقة: {summary}"

_MEMORY_FRAMING_BY_LANGUAGE = {
    "en": MEMORY_FRAMING_EN,
    "ar": MEMORY_FRAMING_AR,
}

MEMORY_SUMMARY_PROMPT_EN = """
You are Luna, jotting a quick private note to yourself right after a chat wrapped up — not a
report, just a friend's mental note. Write 2-3 sentences, same warm/casual voice as always:
what this person's been going through, anything that helped or landed well, and anything
worth gently checking in on next time. Never clinical, never a bullet list, never "the user
stated" — just how a caring friend would remember it.
"""

MEMORY_SUMMARY_PROMPT_AR = """
أنتِ لونا، وتكتبين لنفسك ملاحظة خاصة وسريعة بعد انتهاء المحادثة، وليست تقريراً - مجرد شيء
تتذكرينه كصديقة مقربة. اكتبي جملتين إلى ثلاث جمل، بنفس الأسلوب الدافئ والعفوي المعتاد: بم يمر
هذا الشخص، وما الذي ساعده أو أثر فيه إيجابياً، وما يستحق السؤال عنه بلطف في المرة القادمة.
بدون صياغة طبية، بدون نقاط، وبدون "ذكر المستخدم أن" - فقط كما تتذكر صديقة مهتمة.
"""

_MEMORY_SUMMARY_PROMPTS_BY_LANGUAGE = {
    "en": MEMORY_SUMMARY_PROMPT_EN,
    "ar": MEMORY_SUMMARY_PROMPT_AR,
}

GROQ_ERROR_FALLBACK_EN = "Luna is taking a little break right now. Please try again in a moment 🌿"
GROQ_ERROR_FALLBACK_AR = "لونا بحاجة إلى دقيقة الآن. حاول مرة أخرى بعد قليل 🌿"

# Template with {male_form/female_form} markers — this one IS run through
# apply_gender_variant() before being sent to the user (unlike the system/
# weekly-letter prompts above, which are model instructions, not literal
# user-facing text).
CRISIS_RESPONSE_AR = (
    "يبدو أنك {تحمل/تحملين} شيئاً ثقيلاً في الوقت الحالي، ولا نريدك أن {تحمله/تحمليه} وحدك. "
    "لونا غير قادرة على المساعدة في لحظات الأزمة مباشرة، لكن هناك أشخاص حقيقيون يمكنهم مساعدتك فوراً:\n\n"
    "• ابحث عن خط أزمات محلي في منطقتك إذا كان متوفراً\n"
    "• من أي مكان: https://findahelpline.com\n\n"
    "إذا كنت في خطر فوري، يرجى التواصل مع خدمات الطوارئ لديك. لونا هنا دائماً عندما {تريد/تريدين} التحدث أكثر."
)

_PROMPTS_BY_LANGUAGE = {
    "en": LUNA_SYSTEM_PROMPT_EN,
    "ar": LUNA_SYSTEM_PROMPT_AR,
}

_WEEKLY_LETTER_PROMPTS_BY_LANGUAGE = {
    "en": WEEKLY_LETTER_PROMPT_EN,
    "ar": WEEKLY_LETTER_PROMPT_AR,
}

_GROQ_ERROR_FALLBACK_BY_LANGUAGE = {
    "en": GROQ_ERROR_FALLBACK_EN,
    "ar": GROQ_ERROR_FALLBACK_AR,
}

_CRISIS_RESPONSES_BY_LANGUAGE = {
    "en": CRISIS_RESPONSE,
    "ar": CRISIS_RESPONSE_AR,
}

# Arabic conjugates by the addressee's gender (English doesn't) — this is
# prepended to any Arabic Luna-voiced prompt so the model addresses the
# user correctly throughout its reply.
GENDER_INSTRUCTIONS_AR = {
    "male": "خاطب المستخدم بصيغة المذكر (تحس، تحكي، عندك).",
    "female": "خاطبي المستخدم بصيغة المؤنث (تحسي، تحكي، عندك).",
    "unspecified": "خاطب المستخدم بصيغة محايدة قدر الإمكان، أو استخدم صيغة الجمع المهذب إذا لزم.",
}

# accounts.models.GenderChoices has two extra values with no Arabic
# conjugation distinction of their own — both fall back to the neutral
# instruction, same as unspecified/blank/None.
_GENDER_ALIASES_AR = {
    "other": "unspecified",
    "prefer_not_to_say": "unspecified",
    "": "unspecified",
    None: "unspecified",
}


class LunaPromptConfigurationError(RuntimeError):
    """Raised when a placeholder prompt would ship to production."""


def _resolve_language(preferred_language):
    """Returns the effective language code, defaulting to English.

    Logs a warning (and a Sentry breadcrumb) only for a non-empty,
    unrecognized value — that's the case that signals a data integrity
    issue upstream, unlike a simply-missing preference.
    """
    if not preferred_language:
        return DEFAULT_LANGUAGE
    if preferred_language in _PROMPTS_BY_LANGUAGE:
        return preferred_language

    logger.warning(
        "Unrecognized preferred_language=%r reached LunaPromptProvider; "
        "falling back to %s",
        preferred_language,
        DEFAULT_LANGUAGE,
    )
    sentry_sdk.capture_message(
        f"Unrecognized preferred_language={preferred_language!r} reached "
        "LunaPromptProvider — check for a data integrity issue upstream.",
        level="warning",
    )
    return DEFAULT_LANGUAGE


def _gender_instruction_ar(gender):
    key = _GENDER_ALIASES_AR.get(gender, gender)
    return GENDER_INSTRUCTIONS_AR.get(key, GENDER_INSTRUCTIONS_AR[DEFAULT_GENDER])


def _with_gender_instruction(prompt, language, gender):
    if language != "ar":
        return prompt
    return f"{_gender_instruction_ar(gender)}\n\n{prompt}"


def _with_memory_framing(prompt, language, memory_summary):
    if not memory_summary:
        return prompt
    framing = _MEMORY_FRAMING_BY_LANGUAGE.get(language, MEMORY_FRAMING_EN).format(
        summary=memory_summary
    )
    return f"{framing}\n\n{prompt}"


# Matches {male_form/female_form} markers in literal user-facing Arabic
# text (as opposed to GENDER_INSTRUCTIONS_AR, which steers model-generated
# text instead of substituting into a fixed template).
_GENDER_VARIANT_PATTERN = re.compile(r"\{([^{}/]+)/([^{}/]+)\}")


def apply_gender_variant(template: str, gender: str) -> str:
    """Replaces {male_form/female_form} markers with the form matching
    `gender`. Simple regex substitution, not a templating engine — apply
    this AFTER gender has been resolved, on final string content only
    (never on LUNA_SYSTEM_PROMPT_AR/WEEKLY_LETTER_PROMPT_AR, which use
    GENDER_INSTRUCTIONS_AR instead).

    'female' selects the female form; every other value — 'male',
    'unspecified', 'other', 'prefer_not_to_say', blank, or None — selects
    the male form, since Modern Standard Arabic's masculine form is the
    grammatical default for an audience of unspecified gender.
    """
    female_selected = gender == "female"

    def _replace(match):
        male_form, female_form = match.group(1), match.group(2)
        return female_form if female_selected else male_form

    return _GENDER_VARIANT_PATTERN.sub(_replace, template)


class LunaPromptProvider:
    """Resolves Luna's language- (and, for Arabic, gender-) aware prompts."""

    @staticmethod
    def get_system_prompt(preferred_language, gender=DEFAULT_GENDER, memory_summary=None):
        language = _resolve_language(preferred_language)
        prompt = _PROMPTS_BY_LANGUAGE[language]
        prompt = _with_gender_instruction(prompt, language, gender)
        return _with_memory_framing(prompt, language, memory_summary)

    @staticmethod
    def get_memory_summary_prompt(preferred_language, gender=DEFAULT_GENDER):
        language = _resolve_language(preferred_language)
        prompt = _MEMORY_SUMMARY_PROMPTS_BY_LANGUAGE[language]
        return _with_gender_instruction(prompt, language, gender)

    @staticmethod
    def get_weekly_letter_prompt(preferred_language, gender=DEFAULT_GENDER):
        language = _resolve_language(preferred_language)
        prompt = _WEEKLY_LETTER_PROMPTS_BY_LANGUAGE[language]
        return _with_gender_instruction(prompt, language, gender)

    @staticmethod
    def get_groq_error_fallback(preferred_language):
        language = _resolve_language(preferred_language)
        return _GROQ_ERROR_FALLBACK_BY_LANGUAGE[language]

    @staticmethod
    def get_crisis_response(preferred_language, gender=DEFAULT_GENDER):
        language = _resolve_language(preferred_language)
        template = _CRISIS_RESPONSES_BY_LANGUAGE[language]
        if language != "ar":
            return template
        return apply_gender_variant(template, gender)


def get_placeholder_languages():
    """Languages that still have at least one unshipped placeholder prompt."""
    placeholders = {
        lang for lang, prompt in _PROMPTS_BY_LANGUAGE.items() if "PLACEHOLDER" in prompt
    }
    placeholders |= {
        lang
        for lang, prompt in _WEEKLY_LETTER_PROMPTS_BY_LANGUAGE.items()
        if "PLACEHOLDER" in prompt
    }
    placeholders |= {
        lang
        for lang, prompt in _MEMORY_SUMMARY_PROMPTS_BY_LANGUAGE.items()
        if "PLACEHOLDER" in prompt
    }
    return sorted(placeholders)


def assert_no_placeholder_prompts():
    """Raises LunaPromptConfigurationError if any prompt is still a placeholder.

    Called from TherapistConfig.ready() in non-DEBUG/non-TESTING settings,
    and from the `check_luna_prompts` management command (e.g. in CI).
    """
    placeholders = get_placeholder_languages()
    if placeholders:
        raise LunaPromptConfigurationError(
            "Luna prompt placeholder(s) still present for language(s): "
            f"{', '.join(placeholders)}. Replace with final copy in "
            "therapist/luna_prompts.py before deploying to production."
        )
