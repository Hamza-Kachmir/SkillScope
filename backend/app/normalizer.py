import re
import unicodedata


def display_label(value: str) -> str:
    label = " ".join(value.split())
    for index, character in enumerate(label):
        if character.isalpha():
            return f"{label[:index]}{character.upper()}{label[index + 1 :]}"
    return label


def search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())
