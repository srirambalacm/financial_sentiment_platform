"""Diagnose Finnhub API connectivity and what the free tier actually returns.

Run this before any long ingest. It checks, in order:

1. Is a key loaded from .env at all?
2. Does a minimal request authenticate?
3. How far back does the free tier actually serve company news?

That third question matters more than it sounds. An API can accept a wide
date range, return HTTP 200, and still hand back only recent items -- which
looks like success but silently leaves your backtest with no history.

Usage
-----
    python -m scripts.check_api
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from config import FINNHUB_API_KEY

URL = "https://finnhub.io/api/v1/company-news"


def _probe(symbol: str, start: date, end: date) -> tuple[int, int | str]:
    """Return (http_status, item_count or error text) for one window."""
    try:
        resp = requests.get(
            URL,
            params={
                "symbol": symbol,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            timeout=20,
        )
    except Exception as exc:
        return 0, f"request failed: {exc}"

    if resp.status_code != 200:
        return resp.status_code, resp.text[:120]
    try:
        return 200, len(resp.json())
    except Exception:
        return 200, "response was not valid JSON"


def main() -> None:
    print("=" * 66)
    print("Finnhub API diagnostic")
    print("=" * 66)

    # -- 1. Is a key present? ---------------------------------------------
    if not FINNHUB_API_KEY:
        print("\n  NO KEY LOADED.")
        print("  Check that .env exists and contains a line like:")
        print("      FINNHUB_API_KEY=yourkeyhere")
        print("  with no spaces around the '=' and no quotes.")
        return

    key = FINNHUB_API_KEY
    print(f"\n  Key loaded: {key[:4]}...{key[-4:]}  (length {len(key)})")
    if key != key.strip():
        print("  ** Key has leading/trailing whitespace -- strip it in .env. **")

    # -- 2. Does it authenticate? -----------------------------------------
    today = date.today()
    status, result = _probe("AAPL", today - timedelta(days=3), today)
    print(f"\n  Auth check (AAPL, last 3 days): HTTP {status}")

    if status == 401:
        print("\n  401 UNAUTHORIZED -- the key is not valid.")
        print("  Most common cause: the key was regenerated on finnhub.io,")
        print("  which immediately invalidates the previous one.")
        print("\n  Fix: go to finnhub.io -> Dashboard -> API Key, copy the")
        print("  CURRENT key, and paste it into .env. Then re-run this script.")
        return
    if status == 429:
        print("\n  429 RATE LIMITED -- too many requests. Wait a few minutes,")
        print("  then increase FINSENT_REQUEST_DELAY in .env before retrying.")
        return
    if status != 200:
        print(f"\n  Unexpected response: {result}")
        return

    print(f"  Authenticated successfully ({result} headlines returned).")

    # -- 3. How far back does history actually go? -------------------------
    print("\n  Probing how much history the free tier serves for AAPL:")
    print(f"    {'window':<26}{'status':>8}{'items':>8}")
    print("    " + "-" * 42)

    probes = [
        ("last 7 days", 0, 7),
        ("~1 month ago", 30, 44),
        ("~2 months ago", 60, 74),
        ("~4 months ago", 120, 134),
        ("~8 months ago", 240, 254),
        ("~12 months ago", 350, 364),
    ]
    reachable = []
    for label, back_start, back_end in probes:
        end = today - timedelta(days=back_start)
        start = today - timedelta(days=back_end)
        st, res = _probe("AAPL", start, end)
        shown = res if isinstance(res, int) else "err"
        print(f"    {label:<26}{st:>8}{str(shown):>8}")
        if st == 200 and isinstance(res, int) and res > 0:
            reachable.append(label)

    print("\n" + "=" * 66)
    if len(reachable) <= 2:
        print("  The free tier appears to serve only RECENT news.")
        print("  A multi-month backtest window is not available on this plan,")
        print("  regardless of the 'from' date requested.")
    else:
        print(f"  History available across: {', '.join(reachable)}")
        print("  A paginated ingest should be able to fill the timeline.")
    print("=" * 66)


if __name__ == "__main__":
    main()