"""Fetch a subreddit's public RSS feed - the official, unauthenticated feed Reddit publishes for every subreddit.

No login, no scraping of HTML, no rotating user agents or proxies. One User-Agent that names you (set your own - see the README), a pause
of at least MIN_PAUSE_S between requests, and a hard stop on HTTP 429 or 403 (the feed asked us to slow down or refused) - never a retry.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

FEED_PREFIX = "https://www.reddit.com/r/"
FEED_URL = FEED_PREFIX + "{sub}/{listing}/.rss?t={window}&limit={limit}"
DEFAULT_UA = "script:reddit-trends-json:0.1 (set your own with --user-agent)"
LISTINGS = ("top", "new", "hot")
WINDOWS = ("hour", "day", "week", "month", "year", "all")
MIN_PAUSE_S = 2.0
MAX_BYTES = 5_000_000
_SUB = re.compile(r"^[A-Za-z0-9_]{3,21}$")


class FeedRefused(RuntimeError):
    """The feed answered 403 / 429: stop, do not retry around it."""


@dataclass
class Fetcher:
    user_agent: str = DEFAULT_UA
    pause_s: float = MIN_PAUSE_S
    timeout_s: float = 20.0
    opener: Optional[Callable[[urllib.request.Request, float], bytes]] = None
    _last: float = 0.0

    def __post_init__(self):
        if self.opener is None:  # tests inject an opener; a real run never goes below the published pause
            self.pause_s = max(MIN_PAUSE_S, float(self.pause_s))

    def url(self, sub: str, listing: str = "top", window: str = "day", limit: int = 50) -> str:
        if not isinstance(sub, str) or not _SUB.match(sub):
            raise ValueError(f"not a subreddit name (3-21 ASCII letters, digits, _): {sub!r}")
        if listing not in LISTINGS:
            raise ValueError(f"listing must be one of {LISTINGS}")
        if window not in WINDOWS:
            raise ValueError(f"window must be one of {WINDOWS}")
        return FEED_URL.format(sub=sub, listing=listing, window=window, limit=max(1, min(int(limit), 100)))

    def get(self, url: str) -> bytes:
        if not url.startswith(FEED_PREFIX):
            raise ValueError(f"only Reddit's https feed is read, not {url!r}")
        wait = self.pause_s - (time.monotonic() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/atom+xml"})  # noqa: S310 - https only
        try:
            if self.opener is not None:
                return self.opener(req, self.timeout_s)
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - fixed https feed URL
                if not resp.geturl().startswith(FEED_PREFIX):
                    raise ValueError(f"redirected off Reddit's feed to {resp.geturl()!r} - refused")
                return resp.read(MAX_BYTES)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise FeedRefused(f"HTTP {exc.code} from {url} - stopping, not retrying") from exc
            raise
        finally:
            self._last = time.monotonic()

    def feed(self, sub: str, listing: str = "top", window: str = "day", limit: int = 50) -> bytes:
        return self.get(self.url(sub, listing, window, limit))
