"""Tokenization shared by keyword extraction, FTS expressions and highlighting.

FTS5 uses `porter unicode61 remove_diacritics 2`: split on non-alphanumerics, fold case and
accents, Porter-stem. Python-side matching mirrors that with PyStemmer's Porter algorithm.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import Stemmer

_STEMMER = Stemmer.Stemmer("porter")
WORD = re.compile(r"[^\W_]+", re.UNICODE)
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ACRONYM = re.compile(r"^(?:[A-Z][A-Za-z0-9]*[A-Z0-9]s?|[A-Z]{2,})$")

STOPWORDS = frozenset(["a", "an", "the", "and", "or", "but", "nor", "of", "in", "on", "at", "to", "for", "from", "by", "with", "without", "within", "into", "onto", "upon", "over", "under", "about", "above", "below", "between", "among", "through", "during", "before", "after", "against", "via", "per", "as", "than", "then", "that", "this", "these", "those", "it", "its", "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "doing", "have", "has", "had", "having", "can", "could", "should", "would", "may", "might", "must", "will", "shall", "not", "no", "yes", "so", "such", "very", "more", "most", "less", "least", "much", "many", "few", "several", "some", "any", "all", "each", "every", "other", "another", "same", "own", "only", "also", "just", "even", "which", "who", "whom", "whose", "what", "when", "where", "why", "how", "whether", "if", "else", "while", "because", "since", "until", "unless", "though", "although", "we", "our", "ours", "you", "your", "yours", "they", "their", "theirs", "he", "she", "his", "her", "him", "i", "me", "my", "mine", "us", "them", "one", "two", "three", "paper", "papers", "work", "works", "study", "studies", "approach", "approaches", "method", "methods", "methodology", "propose", "proposed", "proposes", "novel", "new", "recent", "recently", "show", "shows", "shown", "use", "used", "uses", "using", "based", "towards", "toward", "via", "find", "finding", "look", "looking", "want", "need", "needs", "related", "relating", "regarding", "concerning", "survey", "overview", "introduction", "literature", "research", "researches", "good", "better", "best", "effective", "efficient", "improve", "improving", "improved", "improves", "improvement"])

CJK_STOP = ("的", "地", "得", "和", "与", "及", "以及", "或", "或者", "在", "对", "对于", "关于", "用", "用于", "于", "如何",
            "怎么", "怎样", "什么", "哪些", "哪个", "基于", "通过", "让", "使", "使得", "更", "最", "能", "能够", "可以",
            "进行", "研究", "方法", "论文", "文章", "工作", "问题", "相关", "有关", "一种", "一个", "我们", "以", "并", "从",
            "到", "中", "上", "下", "是", "有", "被", "将", "把", "这", "那", "其", "之", "等", "吗", "呢", "了", "着", "过",
            "自己", "他们", "其中", "以及", "如果", "为什么", "为了", "一些", "提升", "提高", "改进", "找", "查找", "寻找",
            "推荐", "最新", "近期", "相关的")


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=200_000)
def stem(word: str) -> str:
    return _STEMMER.stemWord(fold(word))


def words(text: str) -> list[str]:
    return WORD.findall(text)


def stems(text: str) -> list[str]:
    return [stem(w) for w in words(text)]


def spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, stem) for each token, for highlighting."""
    return [(m.start(), m.end(), stem(m.group(0))) for m in WORD.finditer(text)]


def is_cjk(text: str) -> bool:
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return False
    return sum(1 for c in letters if CJK.match(c)) / len(letters) >= 0.3


def fts_phrase(text: str) -> str | None:
    """A safe FTS5 phrase for `text` (tokens joined, quotes escaped)."""
    toks = words(text)
    if not toks:
        return None
    return '"' + " ".join(toks).replace('"', '""') + '"'


def cjk_chunks(text: str) -> list[str]:
    """Split a Chinese query into content chunks at punctuation and function words."""
    parts = re.split(r"[\s,，。．.!！?？;；:：、()（）\[\]【】“”\"'‘’/]+", text)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        pieces = [p]
        for sw in sorted(CJK_STOP, key=len, reverse=True):
            nxt = []
            for piece in pieces:
                nxt.extend(x for x in piece.split(sw))
            pieces = nxt
        out.extend(x.strip() for x in pieces if len(x.strip()) >= 2)
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq
