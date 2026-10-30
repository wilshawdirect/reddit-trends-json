import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from reddit_trends.cli import main, previous_snapshot, snapshot
from reddit_trends.fetch import DEFAULT_UA, Fetcher, FeedRefused
from reddit_trends.parse import parse_feed
from reddit_trends.trends import count_terms, rising, tokens

FIX = (Path(__file__).parent / "fixtures" / "diy_top_day.xml").read_bytes()
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)


def test_url_is_the_official_feed_and_inputs_are_checked():
    f = Fetcher()
    assert f.url("DIY", "top", "day", 50) == "https://www.reddit.com/r/DIY/top/.rss?t=day&limit=50"
    assert f.url("DIY", limit=999).endswith("limit=100")
    for bad in ("", "../etc", "a b", "DIYé", "ab", "x" * 22):
        with pytest.raises(ValueError):
            f.url(bad)
    with pytest.raises(ValueError):
        f.url("DIY", listing="controversial")


def test_the_pause_never_goes_below_two_seconds_on_a_real_run():
    assert Fetcher(pause_s=0).pause_s == 2.0 and Fetcher(pause_s=-5).pause_s == 2.0 and Fetcher(pause_s=3).pause_s == 3.0


def test_one_honest_user_agent_and_a_pause_between_requests(monkeypatch):
    seen, sleeps = [], []
    monkeypatch.setattr("reddit_trends.fetch.time.sleep", lambda s: sleeps.append(s))
    f = Fetcher(pause_s=2.0, opener=lambda req, t: seen.append(req.get_header("User-agent")) or FIX)
    f.feed("DIY")
    f.feed("DIY")
    assert seen == [DEFAULT_UA, DEFAULT_UA] and sleeps and sleeps[0] > 0


@pytest.mark.parametrize("code", [403, 429])
def test_a_refusal_stops_and_is_never_retried(code):
    calls = []

    def opener(req, t):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, code, "no", {}, io.BytesIO(b""))

    with pytest.raises(FeedRefused):
        Fetcher(pause_s=0, opener=opener).feed("DIY")
    assert calls == [1]


def test_parse_reads_every_entry():
    posts = parse_feed(FIX, "DIY")
    assert [p["id"] for p in posts] == ["t3_aaa111", "t3_bbb222", "t3_ccc333"]
    assert posts[0]["link"].startswith("https://www.reddit.com/r/DIY/") and posts[2]["published"].startswith("2026-10-26T20")
    with pytest.raises(ValueError):
        parse_feed(b"<not xml", "DIY")
    bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse_feed(bomb, "DIY")
    # advisor bypasses: a DOCTYPE after a > 4 KB comment, and a UTF-16 feed
    late = b"<?xml version='1.0'?><!--" + b"x" * 5000 + b'--><!DOCTYPE f [<!ENTITY e "pwn">]><feed xmlns="http://www.w3.org/2005/Atom"/>'
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse_feed(late, "DIY")
    with pytest.raises(ValueError, match="UTF-8"):
        parse_feed(bomb.decode().encode("utf-16"), "DIY")


def test_only_reddits_https_feed_is_ever_requested():
    with pytest.raises(ValueError):
        Fetcher(pause_s=0, opener=lambda r, t: b"").get("file:///etc/passwd")


def test_terms_count_once_per_post_and_drop_singletons():
    assert tokens("Shed insulation - what did I miss?") == ["shed", "insulation", "miss"]
    t = count_terms(p["title"] for p in parse_feed(FIX, "DIY"))
    assert ["insulation", 2] in t["words"] and ["shed", 2] in t["words"]
    assert ["shed insulation", 2] in t["phrases"]
    assert all(v > 1 for _, v in t["words"])


def test_rising_compares_with_the_previous_snapshot():
    now = {"words": [["shed", 5], ["paint", 3], ["tile", 2]]}
    before = {"words": [["shed", 2], ["paint", 3]]}
    assert rising(now, before) == [["shed", 5, 2], ["tile", 2, 0]]
    # full counts: a term outside yesterday's top list is not a false 'new' riser
    assert rising(now, {"words": [["shed", 2]], "all_words": {"shed": 2, "paint": 3, "tile": 2}}) == [["shed", 5, 2]]


def test_snapshot_records_a_refusal_and_keeps_what_it_read():
    def opener(req, t):
        if "/r/second/" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", {}, io.BytesIO(b""))
        return FIX

    snap = snapshot(["DIY", "second", "third"], Fetcher(pause_s=0, opener=opener), now=NOW)
    assert snap["post_count"] == 3 and "429" in snap["stopped"] and snap["generated_at"] == "2026-10-27T09:00:00+00:00"


def test_a_stopped_or_empty_file_is_never_the_baseline(tmp_path):
    (tmp_path / "2026-10-25.json").write_text(json.dumps({"post_count": 3, "terms": {"words": [["shed", 1]]}}), encoding="utf-8")
    (tmp_path / "2026-10-26.json").write_text(json.dumps({"post_count": 0, "stopped": "HTTP 429"}), encoding="utf-8")
    assert previous_snapshot(tmp_path, "2026-10-27")["post_count"] == 3


def test_a_refused_rerun_keeps_todays_good_file_and_exit_codes(tmp_path, monkeypatch):
    def refused(req, t):
        raise urllib.error.HTTPError(req.full_url, 429, "slow", {}, io.BytesIO(b""))

    monkeypatch.setattr("reddit_trends.cli.Fetcher", lambda **kw: Fetcher(pause_s=0, opener=lambda r, t: FIX))
    assert main(["--sub", "DIY", "--out", str(tmp_path)]) == 0
    good = next(tmp_path.glob("????-??-??.json")).read_text(encoding="utf-8")
    monkeypatch.setattr("reddit_trends.cli.Fetcher", lambda **kw: Fetcher(pause_s=0, opener=refused))
    assert main(["--sub", "DIY", "--out", str(tmp_path)]) == 2
    assert next(tmp_path.glob("????-??-??.json")).read_text(encoding="utf-8") == good
    monkeypatch.setattr("reddit_trends.cli.Fetcher", lambda **kw: Fetcher(pause_s=0, opener=lambda r, t: b"<bad"))
    assert main(["--sub", "DIY", "--out", str(tmp_path / "x")]) == 1  # every feed failed -> exit 1


def test_cli_writes_a_dated_file_and_reads_the_previous_one(tmp_path, monkeypatch):
    (tmp_path / "2026-10-26.json").write_text(json.dumps({"post_count": 1, "terms": {"words": [["shed", 1]]}}), encoding="utf-8")
    monkeypatch.setattr("reddit_trends.cli.Fetcher", lambda **kw: Fetcher(pause_s=0, opener=lambda r, t: FIX))
    assert previous_snapshot(tmp_path, "2026-10-27")["terms"]["words"] == [["shed", 1]]
    assert main(["--sub", "DIY", "--out", str(tmp_path)]) == 0
    files = sorted(p.name for p in tmp_path.glob("????-??-??.json"))
    newest = json.loads((tmp_path / files[-1]).read_text(encoding="utf-8"))
    assert newest["post_count"] == 3 and ["shed", 2, 1] in newest["rising"]
