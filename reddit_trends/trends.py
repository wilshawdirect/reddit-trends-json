"""Turn post titles into trend counts: words and two-word phrases, stop words removed, counted once per post."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List

STOP = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how i if in into is it its just
like me more most my no not of on or our out so some than that the their them then there these they this to too up us was we what
when where which who why will with would you your about after all also any because before being best get got here im ive dont
does doesnt one only other over really still such very via vs""".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9'+-]*")


def tokens(title: str) -> List[str]:
    words = [w.strip("'+-") for w in _WORD.findall((title or "").lower())]
    return [w for w in words if len(w) > 2 and w not in STOP and not w.isdigit()]


def count_terms(titles: Iterable[str], top: int = 25) -> dict:
    """{'words': [[term, posts]] (top N), 'phrases': [[term, posts]] (top N), 'all_words': {term: posts}} - each term counted at most
    once per post; the top lists drop terms seen in one post only; all_words keeps every count so the next run compares fairly."""
    words, phrases = Counter(), Counter()
    for t in titles:
        tk = tokens(t)
        words.update(set(tk))
        phrases.update({f"{a} {b}" for a, b in zip(tk, tk[1:], strict=False)})
    keep = lambda c: [[k, v] for k, v in c.most_common(top) if v > 1]  # noqa: E731 - a term in one post is not a trend
    return {"words": keep(words), "phrases": keep(phrases), "all_words": dict(words)}


def rising(today: dict, previous: dict, top: int = 15) -> list:
    """Terms whose post count grew against the previous snapshot's FULL counts: [[term, now, before]], biggest gain first."""
    before = previous.get("all_words") or {k: v for k, v in previous.get("words", [])}
    gains = [[k, v, int(before.get(k, 0))] for k, v in today.get("words", []) if v > int(before.get(k, 0))]
    return sorted(gains, key=lambda g: (g[1] - g[2], g[1]), reverse=True)[:top]
