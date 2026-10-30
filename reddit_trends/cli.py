"""reddit-trends: snapshot a niche's public subreddit feeds into one dated JSON file.

    reddit-trends --sub homeimprovement --sub DIY --out data/            -> data/2026-10-27.json
    reddit-trends --sub DIY --window week --listing top --out data/

Each file holds the posts it read, the top words / two-word phrases (counted once per post) and the terms that rose against the newest
earlier file in the same folder. A refused feed (HTTP 403 / 429) stops the run and is written into the file as such - nothing is retried
around it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .fetch import Fetcher, FeedRefused
from .parse import parse_feed
from .trends import count_terms, rising


def usable(snap: dict) -> bool:
    """A snapshot that can be a baseline: it read posts and was not stopped by a refusal (an empty file would make every term 'rise')."""
    return bool(snap) and not snap.get("stopped") and int(snap.get("post_count") or 0) > 0


def previous_snapshot(out: Path, today: str) -> dict:
    """The newest USABLE YYYY-MM-DD.json in `out` dated before `today` ({} when none)."""
    for p in sorted((p for p in out.glob("????-??-??.json") if p.stem < today), reverse=True):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if usable(snap):
            return snap
    return {}


def snapshot(
    subs: List[str],
    fetcher: Fetcher,
    listing: str = "top",
    window: str = "day",
    limit: int = 50,
    now: Optional[datetime] = None,
    previous: Optional[dict] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    posts, errors, stopped = [], [], None
    for sub in subs:
        try:
            posts += parse_feed(fetcher.feed(sub, listing, window, limit), sub)
        except FeedRefused as exc:
            stopped = str(exc)
            break
        except (ValueError, OSError) as exc:
            errors.append({"subreddit": sub, "error": f"{type(exc).__name__}: {exc}"[:300]})
    terms = count_terms(p["title"] for p in posts)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "subreddits": subs,
        "listing": listing,
        "window": window,
        "post_count": len(posts),
        "terms": terms,
        "rising": rising(terms, (previous or {}).get("terms", {})),
        "posts": posts,
        "errors": errors,
        "stopped": stopped,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="reddit-trends", description=__doc__.splitlines()[0])
    ap.add_argument("--sub", action="append", required=True, help="subreddit name (repeatable)")
    ap.add_argument("--listing", default="top", choices=["top", "new", "hot"])
    ap.add_argument("--window", default="day", choices=["hour", "day", "week", "month", "year", "all"])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default="data")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between feed requests (minimum 2)")
    ap.add_argument("--user-agent", default=None, help="your own UA, e.g. 'script:my-trends:0.1 (by /u/yourname)'")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    fetcher = Fetcher(pause_s=a.pause) if a.user_agent is None else Fetcher(user_agent=a.user_agent, pause_s=a.pause)
    snap = snapshot(a.sub, fetcher, a.listing, a.window, a.limit, now, previous_snapshot(out, today))
    path = out / f"{today}.json"
    kept = None
    if not usable(snap) and path.exists():  # a refused / empty re-run never replaces a good file from earlier today
        try:
            if usable(json.loads(path.read_text(encoding="utf-8"))):
                kept = path
        except (OSError, ValueError):
            kept = None
    if kept is None:
        path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"{path}: {snap['post_count']} posts, {len(snap['terms']['words'])} terms, {len(snap['rising'])} rising"
        + (f", STOPPED: {snap['stopped']}" if snap["stopped"] else "")
        + (" (kept the earlier file from today)" if kept else "")
    )
    if snap["stopped"]:
        return 2
    return 1 if snap["errors"] and not snap["post_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
