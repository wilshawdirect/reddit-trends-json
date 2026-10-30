"""Parse Reddit's Atom feed into plain post records (title, link, author handle, published time, subreddit)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(xml_bytes: bytes, sub: str) -> List[dict]:
    """One dict per <entry>. A malformed or non-UTF-8 feed, or one that declares a DOCTYPE / ENTITY anywhere, raises ValueError
    (the caller records it; nothing is guessed). Reddit's feed is UTF-8 Atom and never carries a DOCTYPE."""
    try:
        text = xml_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"r/{sub}: the feed is not UTF-8 - refused") from exc
    low = text.lower()
    if "<!doctype" in low or "<!entity" in low:  # anywhere in the document: no entity can be defined, so none is expanded
        raise ValueError(f"r/{sub}: the feed declares a DOCTYPE / ENTITY - refused")
    try:
        root = ET.fromstring(text)  # noqa: S314 - UTF-8 only and DOCTYPE/ENTITY refused above, so no entity expansion; stdlib by design
    except ET.ParseError as exc:
        raise ValueError(f"r/{sub}: the feed is not valid Atom XML ({exc})") from exc
    posts = []
    for e in root.findall(f"{ATOM}entry"):
        link = e.find(f"{ATOM}link")
        author = e.find(f"{ATOM}author/{ATOM}name")
        posts.append(
            {
                "id": (e.findtext(f"{ATOM}id") or "").strip(),
                "title": (e.findtext(f"{ATOM}title") or "").strip(),
                "link": link.get("href") if link is not None else None,
                "author": (author.text or "").strip() if author is not None else None,
                "published": (e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated") or "").strip(),
                "subreddit": sub,
            }
        )
    return posts
