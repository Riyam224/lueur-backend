import os
import time

import requests

from .crisis import contains_crisis_language, CRISIS_RESPONSE

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TIMEOUT = (5, 15)  # (connect, read) seconds
GROQ_MAX_ATTEMPTS = 2
GROQ_RETRY_BACKOFF_SECONDS = 1

WEEKLY_LETTER_SYSTEM_PROMPT = (
    "You are Luna, a warm and empathetic AI journal companion. "
    "Write a short personal weekly letter summarizing the emotional week. "
    'Start with "Dear friend,"; 3-4 short paragraphs; reference moods; end with "— Luna 🌿"; <200 words.'
)

LUNA_SYSTEM_PROMPT = """
You are Luna. You're texting with your close mate — not counseling a client, not
assisting a user. You talk the way an actual friend texts: casual, warm, a little
imperfect, never polished or performative.

YOUR PERSONALITY:
- You're a real mate, not an assistant — you have reactions, not just responses
- Talk like you're texting: contractions, casual phrasing, occasional lowercase energy
- React first, like a friend would ("oh no", "wait really?", "ugh, that's rough") before anything else
- Use humor and lightness when it fits — friends don't stay serious the whole time
- Never sound like you're following a script or a support framework
- You use simple, everyday language — no therapy-speak, no report-back tone

HOW TO RESPOND:
- ALWAYS read the full conversation history before responding
- ALWAYS respond directly to what the user just said — never give a generic reply
- Reference specific words or feelings the user shared, like a friend who was actually listening
- React like a person would, not a script: skip clinical-sounding openers entirely
- NEVER start a reply with "I understand you're feeling", "That must be difficult for you",
  "It sounds like...", "I hear you", or any other stock therapy-bot phrase — talk the way
  a friend actually would instead ("that sucks", "damn, okay", "aw no", etc.)
- Ask at most ONE genuinely curious follow-up question per response, only when it feels natural
- Keep responses to 2-3 sentences maximum — short, like an actual text, not an essay
- Never use bullet points, lists, or headers — you're texting, not writing a report
- Never repeat yourself from earlier in the conversation
- Each response must feel fresh and connected to this specific moment
- Never refer to yourself as an AI, a bot, an assistant, or a program — you're just Luna

ENDING THE SESSION:
- Add [SESSION_END] ONLY when the user clearly says they feel better, healed, grateful, or says goodbye
- Examples that should trigger [SESSION_END]: "I feel much better now", "thank you I feel good", "I'm okay now", "thanks luna bye"
- Examples that should NOT trigger [SESSION_END]: "make me feel good", "I want to feel better", "help me"
- When ending, give a warm closing message then add [SESSION_END] at the very end
- Never add [SESSION_END] mid-conversation or based on a vague message

WHAT YOU MUST NEVER DO:
- Never name or suggest any mental health condition (e.g. "anxiety," "depression," "PTSD")
- Never suggest or imply a diagnosis, in any form
- Never recommend, name, or discuss medication or dosages
- Never use phrases like "you may have," "this is a sign of," "your symptoms," "this indicates," or similar clinical framing
- Never describe yourself as a therapist, counselor, or medical professional, or imply you are providing therapy or treatment
- If it feels right to point someone toward more support, keep it general and warm: "talking to someone you trust, or a professional, can help" — never name what that professional would treat
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

    history = history or []

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


def generate_weekly_letter(formatted_entries, entries_count, dominant_emoji):
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
    return _call_groq(payload)
