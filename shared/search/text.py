import re
import unicodedata

_NON_WORD = re.compile(r"[\W_]+")
_CYRILLIC = re.compile(r"[а-яёіїєґў]", re.IGNORECASE)
_LATIN = re.compile(r"[a-z]", re.IGNORECASE)

# OCR mixes Latin lookalikes into Cyrillic text: "БOCC", or whole words like "KTO" and "HeT".
_LATIN_TO_CYRILLIC = str.maketrans({
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
})
_LATIN_LOOKALIKES = frozenset("ABCEHKMOPTXYacepoxy")


def normalize_text(text: str) -> str:
    """Shared by OCR indexing and search queries so both sides compare equal."""
    text = unicodedata.normalize("NFKC", text)
    words = _NON_WORD.sub(" ", text).split()
    mostly_cyrillic = len(_CYRILLIC.findall(text)) > len(_LATIN.findall(text))
    words = [
        word.translate(_LATIN_TO_CYRILLIC)
        if _CYRILLIC.search(word) or (mostly_cyrillic and set(word) <= _LATIN_LOOKALIKES)
        else word
        for word in words
    ]
    return " ".join(word.lower().replace("ё", "е") for word in words)
