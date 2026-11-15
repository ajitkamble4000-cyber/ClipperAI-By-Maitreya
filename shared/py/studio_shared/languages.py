"""Languages captions can be translated into. Limited to scripts the bundled caption fonts can draw
(Latin, Cyrillic, Devanagari), so every translated caption renders correctly in every preset."""

from __future__ import annotations

TRANSLATE_TO: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese (Brazil)",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "id": "Indonesian",
    "ms": "Malay",
    "fil": "Filipino",
    "vi": "Vietnamese",
    "sv": "Swedish",
    "ro": "Romanian",
    "ru": "Russian",
    "uk": "Ukrainian",
    "hi": "Hindi",
    "mr": "Marathi",
    "ne": "Nepali",
    "hinglish": "Hinglish (Hindi in Latin letters)",
    "sw": "Swahili",
    "cs": "Czech",
    "hu": "Hungarian",
}


def name(code: str) -> str:
    return TRANSLATE_TO.get(code, code)
