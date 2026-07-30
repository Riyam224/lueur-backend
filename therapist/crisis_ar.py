"""
crisis_ar.py

Arabic-language sibling to therapist/crisis.py's English crisis-language
detector. therapist/crisis.py is frozen — this module deliberately does
NOT edit or extend it; it runs alongside it as a second, independent
detection source (see integration in therapist/views.py).

Mirrors crisis.py's detection philosophy exactly: broad matching,
tolerant of false positives (a missed crisis message is worse than a
false alarm), plain substring/regex matching — no NLP, nothing clever —
so this stays as easy to audit as the English list.

CRISIS_KEYWORDS_AR is a flat list (direct statements, self-harm, indirect/
euphemistic expressions, hopelessness, intent, plan, time/imminence,
farewell, and attempt-in-progress phrases) — any match is treated as a
crisis, exactly like crisis.py's English list. No weighting, negation
detection, or third-person/fiction detection: those are deliberately
deferred to a future, smarter version. Two categories of words were
deliberately left out of this list for the same reason: very short/
generic death-related words ("الموت", "أموت", "ميتا") are common in
everyday non-crisis speech (e.g. "مت من الضحك") and would cause excessive
false positives without context logic; and third-person/fiction/negation
markers require exactly the contextual logic this phase doesn't have.
"""

import re

CRISIS_KEYWORDS_AR = [
    # Direct suicide statements
    "أريد أن أنتحر", "أفكر في الانتحار", "أفكر بالانتحار", "سوف أنتحر",
    "سأنهي حياتي", "أريد إنهاء حياتي", "أريد أن أنهي حياتي",
    "قررت إنهاء حياتي", "قررت أن أنتحر", "سأقتل نفسي", "أريد قتل نفسي",
    "أريد أن أقتل نفسي", "أريد الموت", "أتمنى الموت", "أتمنى أن أموت",
    "أرغب في الموت", "لا أريد أن أعيش", "لم أعد أريد أن أعيش",
    "لا أرغب في البقاء حيا", "لا أريد البقاء على قيد الحياة",
    "أفضل أن أكون ميتا", "الموت أفضل لي", "سأموت بيدي",
    "أريد التخلص من حياتي", "أفكر في إنهاء وجودي", "سأضع حدا لحياتي",
    "أريد أن أضع حدا لحياتي",

    # Direct self-harm statements
    "أريد أن أؤذي نفسي", "أفكر في إيذاء نفسي", "سأؤذي نفسي",
    "أشعر برغبة في إيذاء نفسي", "أريد أن أجرح نفسي", "أفكر في جرح نفسي",
    "سأجرح نفسي", "جرحت نفسي", "لقد جرحت نفسي", "آذيت نفسي",
    "لقد آذيت نفسي", "أعاقب نفسي بالأذى", "أسبب الألم لنفسي",
    "لا أستطيع منع نفسي من إيذاء نفسي", "أشعر أنني قد أؤذي نفسي",
    "أخشى أن أؤذي نفسي",

    # Indirect/euphemistic expressions
    "أريد أن أختفي إلى الأبد", "أتمنى أن أختفي إلى الأبد",
    "لن أبقى موجودا", "قريبا لن أكون موجودا", "لن تروني مرة أخرى",
    "هذه هي النهاية بالنسبة إلي", "لقد وصلت إلى نهايتي",
    "سأتخلص من كل شيء", "أريد الخلاص من كل شيء", "أريد الهروب إلى الأبد",
    "أريد أن أنام ولا أستيقظ", "أتمنى ألا أستيقظ",
    "أتمنى أن تكون هذه آخر ليلة لي", "أتمنى ألا يأتي الغد",
    "سيكون الجميع أفضل من دوني", "ستكون الحياة أفضل من دوني",
    "سيرتاح الجميع من دوني", "لن يفتقدني أحد", "لن يشعر أحد بغيابي",
    "وجودي لا قيمة له", "لم يعد لوجودي معنى", "لا فائدة من بقائي",
    "لا داعي لبقائي", "لم يعد لدي سبب للبقاء", "لم يعد لدي سبب للعيش",
    "لا شيء يستحق أن أعيش من أجله", "أريد الرحيل بلا عودة",
    "سأرحل إلى مكان لا عودة منه", "أريد أن ينتهي كل شيء",
    "أتمنى أن ينتهي كل شيء", "قريبا سأتوقف عن إزعاج الجميع",
    "سأريح الجميع مني", "لن أكون مشكلة بعد الآن", "هذه رسالتي الأخيرة",
    "هذه كلماتي الأخيرة", "أودعكم جميعا", "سامحوني على كل شيء",

    # Severe hopelessness
    "لا يوجد أي أمل", "فقدت كل الأمل", "لم يعد لدي أمل",
    "لن تتحسن الأمور أبدا", "لا يمكن إصلاح أي شيء", "لا يوجد حل",
    "لا أرى أي مخرج", "أشعر أنني محاصر", "لا أستطيع الاستمرار",
    "لم أعد أستطيع الاستمرار", "لا أستطيع التحمل أكثر", "لم أعد أحتمل",
    "وصلت إلى أقصى ما أستطيع تحمله", "تعبت من الحياة", "كرهت حياتي",
    "حياتي بلا معنى", "كل شيء بلا معنى", "لا يوجد سبب للعيش",
    "وجودي بلا قيمة", "أنا بلا قيمة", "أنا عديم القيمة",
    "أنا عبء على الجميع", "يشكل وجودي عبئا على الآخرين",
    "الجميع أفضل من دوني", "لا أحد يحتاج إلي", "لا أحد يهتم بي",
    "أنا وحيد تماما", "لا أستطيع إنقاذ نفسي", "انتهى كل شيء",
    "لا مستقبل لي", "لم يعد هناك ما أنتظره", "الألم لا يحتمل",
    "لا أستطيع الهرب من هذا الألم", "لن أتخلص من هذا الألم أبدا",
    "لا أستطيع مواصلة حياتي", "لا أملك سببا للبقاء",

    # Intent indicators
    "أنوي فعل ذلك", "لدي نية لفعل ذلك", "اتخذت قراري", "قررت فعل ذلك",
    "أنا مصمم على ذلك", "لن أتراجع", "لا يستطيع أحد إيقافي",
    "هذه المرة سأفعلها", "أنا جاد", "أصبحت مستعدا",
    "أنا مستعد لفعل ذلك", "لم يعد لدي تردد", "لن أغير رأيي",
    "حسمت أمري", "سأنفذ ما قررته",

    # Plan indicators
    "لدي خطة", "وضعت خطة", "أعددت خطة", "خططت لكل شيء",
    "أعرف كيف سأفعل ذلك", "أعرف الطريقة", "اخترت الطريقة",
    "حددت الطريقة", "أعددت ما أحتاج إليه", "جهزت كل شيء",
    "حضرت كل شيء", "وجدت وسيلة", "لدي الوسيلة", "الوسيلة أمامي",
    "أستطيع الوصول إلى الوسيلة", "بحثت عن طريقة",
    "بحثت عن كيفية فعل ذلك", "اخترت المكان", "حددت المكان",
    "اخترت الوقت", "حددت الوقت", "رتبت كل شيء", "أنهيت ترتيباتي",

    # Time/imminence indicators
    "بعد قليل", "خلال دقائق", "قبل الصباح", "عندما أبقى وحدي",
    "عندما ينام الجميع", "عندما يغادر الجميع", "لقد حان الوقت",
    "هذا هو الوقت",

    # Farewell indicators
    "كتبت رسالة وداع", "أكتب رسالة وداع", "ودعت عائلتي",
    "ودعت أصدقائي", "ودعت الجميع", "قلت لهم وداعا",
    "أعطيت أشيائي للآخرين", "وزعت ممتلكاتي", "رتبت ممتلكاتي",
    "رتبت أموري الأخيرة", "أغلقت حساباتي", "مسحت كل شيء",
    "أنهيت كل التزاماتي", "طلبت من الجميع أن يسامحوني",
    "سامحوني جميعا", "اعتنوا بأنفسكم", "اعتنوا بعائلتي",

    # Attempt in progress
    "بدأت بالفعل", "فعلت ذلك بالفعل", "حاولت قتل نفسي",
    "حاولت الانتحار", "أقدمت على الانتحار", "آذيت نفسي بشدة",
    "أنا في خطر الآن", "لا أستطيع إنقاذ نفسي", "أحتاج إلى إسعاف",
    "أحتاج إلى مساعدة فورية", "قد أفقد الوعي", "أشعر أنني أحتضر",

    # Context words (used standalone per flat-list approach)
    "انتحار", "أنتحر", "أنهي حياتي", "إنهاء حياتي", "أقتل نفسي",
    "قتل نفسي", "نهاية حياتي", "إيذاء نفسي", "أؤذي نفسي",
    "جرح نفسي", "أجرح نفسي",
]
_CRISIS_PATTERN_AR = re.compile(r"|".join(re.escape(k) for k in CRISIS_KEYWORDS_AR), re.IGNORECASE)


def contains_crisis_language_ar(text: str) -> bool:
    return bool(text) and bool(_CRISIS_PATTERN_AR.search(text))


class CrisisArConfigurationError(RuntimeError):
    """Raised when placeholder Arabic crisis keywords would ship to production."""


def get_placeholder_keywords():
    """Keywords in CRISIS_KEYWORDS_AR that are still unshipped placeholders."""
    return [kw for kw in CRISIS_KEYWORDS_AR if "PLACEHOLDER" in kw]


def assert_no_placeholder_keywords():
    """Raises CrisisArConfigurationError if any placeholder keyword remains.

    Called from TherapistConfig.ready() in non-DEBUG/non-TESTING settings,
    and from the `check_crisis_ar_keywords` management command (e.g. CI).
    """
    placeholders = get_placeholder_keywords()
    if placeholders:
        raise CrisisArConfigurationError(
            "therapist/crisis_ar.py still contains placeholder crisis "
            f"keyword(s): {', '.join(placeholders)}. Replace with the "
            "reviewed Arabic keyword list before deploying to production."
        )
