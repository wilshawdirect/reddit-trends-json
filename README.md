# reddit-trends-json

Snapshot a niche's public subreddit feeds into one dated JSON file a day: the posts read, the top words and two-word phrases, and the terms
that rose since the previous snapshot. Built to answer "what is this community talking about this week?" for product and content research.

**Official feeds only.** It reads the Atom/RSS feed Reddit publishes for every subreddit (`/r/<sub>/<listing>/.rss`). No login, no HTML
scraping, no rotating user agents, no proxies. One User-Agent that names you, a pause of at least 2 s between requests, and a hard stop
on HTTP 403 or 429 - a refused feed ends the run and is written into the file; nothing is retried around it. The response is size-capped,
redirects off Reddit's feed are refused, and a feed that declares a DOCTYPE/ENTITY (Atom never does) is rejected. Standard library only.

## Use

```bash
pip install -e .
reddit-trends --sub DIY --sub homeimprovement --out data/ \
  --user-agent "script:my-trends:0.1 (by /u/yourname)"              # -> data/2026-10-27.json
reddit-trends --sub DIY --listing top --window week --limit 100 --out data/
```

**Set your own `--user-agent`** (Reddit asks for `<platform>:<app id>:<version> (by /u/<username>)`; generic agents get refused more
often). Run it once a day (cron / Task Scheduler); each run compares itself with the newest earlier *usable* file in the folder (a file
from a refused or empty run is never the baseline, and a refused re-run never overwrites a good file from earlier the same day).
Exit codes: 0 ok, 1 every feed failed, 2 Reddit refused (403/429) and the run stopped.

## The file

```json
{
  "generated_at": "2026-10-27T09:00:00+00:00",
  "subreddits": ["DIY"], "listing": "top", "window": "day", "post_count": 50,
  "terms": {"words": [["insulation", 6], ...], "phrases": [["shed insulation", 3], ...]},
  "rising": [["insulation", 6, 2], ...],
  "posts": [{"id": "t3_...", "title": "...", "link": "https://www.reddit.com/r/DIY/...", "author": "/u/...", "published": "...", "subreddit": "DIY"}],
  "errors": [], "stopped": null
}
```

- A term counts at most once per post, and a term seen in only one post is not reported (one post is not a trend).
- `rising` = `[term, posts now, posts in the previous snapshot]`, biggest gain first, compared against the previous file's full counts
  (`terms.all_words`), not only its top list.
- `errors` lists a feed that could not be read or parsed; `stopped` is set when Reddit refused (403/429) and the run ended.

## Limits

The public feed carries titles, links, authors and times - not scores or comment counts - so "trend" here means *how many posts mention
a term*, not engagement. Respect Reddit's terms and rate limits: one run a day per niche. **Check Reddit's User Agreement and Data API
Terms before any commercial use.** The output contains Reddit usernames - keep `data/` private (it is git-ignored here).

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
```

MIT licence.
