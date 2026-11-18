"""A small, brace-aware BibTeX reader (enough for PMLR's bibliography.bib files)."""

from __future__ import annotations

import re

_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.S)
_LATEX_ACCENTS = {
    r"\'": "\u0301", r"\`": "\u0300", r"\^": "\u0302", r'\"': "\u0308", r"\~": "\u0303", r"\=": "\u0304",
    r"\.": "\u0307", r"\c": "\u0327", r"\v": "\u030c", r"\u": "\u0306", r"\H": "\u030b",
}


def _read_value(text: str, i: int) -> tuple[str, int]:
    """Read a braced, quoted or bare value starting at text[i]; return (value, next index)."""
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return "", i
    if text[i] == "{":
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[i + 1:j], j + 1
            j += 1
        return text[i + 1:], len(text)
    if text[i] == '"':
        j = i + 1
        depth = 0
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' and depth == 0:
                return text[i + 1:j], j + 1
            j += 1
        return text[i + 1:], len(text)
    m = re.match(r"[^,}\s]+", text[i:])
    if m:
        return m.group(0), i + m.end()
    return "", i


def parse_bibtex(text: str) -> list[dict]:
    entries = []
    pos = 0
    while True:
        m = _ENTRY.search(text, pos)
        if not m:
            break
        etype, key = m.group(1).lower(), m.group(2)
        i = m.end()
        fields: dict[str, str] = {}
        while i < len(text):
            while i < len(text) and (text[i].isspace() or text[i] == ","):
                i += 1
            if i >= len(text) or text[i] == "}":
                i += 1
                break
            fm = re.match(r"([A-Za-z_][\w\-]*)\s*=", text[i:])
            if not fm:
                nxt = text.find("\n", i)
                i = len(text) if nxt < 0 else nxt + 1
                continue
            name = fm.group(1).lower()
            i += fm.end()
            value, i = _read_value(text, i)
            fields[name] = value
        entries.append({"type": etype, "key": key, **fields})
        pos = i
    return entries


def delatex(value: str) -> str:
    """Strip common LaTeX markup from titles and abstracts."""
    import unicodedata

    s = value
    for cmd, comb in _LATEX_ACCENTS.items():
        s = re.sub(re.escape(cmd) + r"\{?\s*([A-Za-z])\}?", lambda m, c=comb: m.group(1) + c, s)
    s = s.replace(r"\&", "&").replace(r"\%", "%").replace(r"\_", "_").replace(r"\$", "$").replace("~", " ")
    s = re.sub(r"\\(?:emph|textit|textbf|textsc|texttt|mathrm|mathcal|mathbf|text)\s*\{([^{}]*)\}", r"\1", s)
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    return unicodedata.normalize("NFC", s)
