"""Filter out headlines that are not actually about the tagged company.

Finnhub's company-news feed is generous about tagging: a story about Entergy
can arrive tagged to META, and a SpaceX story tagged to ORCL. Averaging those
into a company's sentiment adds noise with no signal, so we drop headlines
that never mention the company.

Matching rules
--------------
A headline is relevant to a symbol if it contains either

* one of the company's name aliases (case-insensitive, word-boundary), or
* the ticker symbol itself, either parenthesized -- "(AAPL)" -- or as a
  standalone uppercase token of at least three characters.

The three-character floor matters: short tickers like V, GS, HD, KO and PG
would otherwise match ordinary English ("HD" in "HD video", a lone "V"
anywhere). Those symbols are covered by their name aliases instead.

This is deliberately a precision-oriented filter. It will drop some genuinely
relevant headlines that refer to a company obliquely, and that trade-off is
the right one: a smaller, cleaner sample beats a larger, noisier one when the
whole point is measuring a weak signal.

Known imperfections, kept deliberately rather than patched with ever more
special cases:

* "visa" matches travel-visa stories as well as Visa Inc.
* "meta" as an ordinary adjective is avoided by requiring "meta platforms",
  which in turn misses headlines that say only "Meta".
* A company can be the true subject of a story that never names it (an
  earnings-reaction piece about "the iPhone maker's supplier").

Each of these is a bounded, measurable error rather than a silent one, and
the per-ticker retention printed by `scripts/tag_relevance.py` makes the
filter's aggressiveness visible instead of hidden.
"""
from __future__ import annotations

import re

# Lowercase substrings that identify each company. Aliases are chosen to be
# specific: "lilly" is safe, a bare "johnson" is not (too many people).
ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("apple", "iphone", "ipad", "tim cook"),
    "MSFT": ("microsoft", "azure", "xbox", "satya nadella"),
    "NVDA": ("nvidia", "jensen huang"),
    "AVGO": ("broadcom", "vmware"),
    "ORCL": ("oracle", "safra catz", "larry ellison"),
    "GOOGL": ("alphabet", "google", "youtube", "sundar pichai", "waymo"),
    "META": ("meta platforms", "facebook", "instagram", "whatsapp", "zuckerberg"),
    "NFLX": ("netflix",),
    "AMZN": ("amazon", "aws", "andy jassy"),
    "TSLA": ("tesla",),
    "HD": ("home depot",),
    "MCD": ("mcdonald",),
    "JPM": ("jpmorgan", "jp morgan", "j.p. morgan", "jamie dimon"),
    "BAC": ("bank of america", "bofa", "merrill lynch"),
    "V": ("visa",),
    "GS": ("goldman sachs", "goldman"),
    "UNH": ("unitedhealth", "united health", "optum"),
    "JNJ": ("johnson & johnson", "johnson and johnson", "j&j"),
    "LLY": ("eli lilly", "lilly", "mounjaro", "zepbound"),
    "PFE": ("pfizer",),
    "XOM": ("exxon",),
    "CVX": ("chevron",),
    "WMT": ("walmart", "wal-mart"),
    "KO": ("coca-cola", "coca cola", "coke"),
    "PG": ("procter & gamble", "procter and gamble", "p&g"),
}

# Ticker symbols short enough to cause false positives if matched bare.
MIN_SYMBOL_LEN = 3


def _build_patterns() -> dict[str, re.Pattern]:
    """Precompile one combined, word-bounded regex per symbol.

    Word boundaries stop 'coke' matching inside 'cokehead' and let an alias
    match at the end of a headline, where a trailing-space pattern would not.
    """
    compiled: dict[str, re.Pattern] = {}
    for symbol, aliases in ALIASES.items():
        parts = [re.escape(a) for a in aliases]
        pattern = r"\b(?:" + "|".join(parts) + r")\b"
        compiled[symbol] = re.compile(pattern, re.IGNORECASE)
    return compiled


_ALIAS_PATTERNS = _build_patterns()
_SYMBOL_PATTERNS = {
    symbol: re.compile(rf"\({re.escape(symbol)}\)|\b{re.escape(symbol)}\b")
    for symbol in ALIASES
}


def is_relevant(symbol: str, headline: str) -> bool:
    """True if the headline plausibly concerns the given ticker."""
    if not headline:
        return False

    alias_pattern = _ALIAS_PATTERNS.get(symbol)
    if alias_pattern and alias_pattern.search(headline):
        return True

    # Parenthesized symbols are unambiguous at any length: "(V)", "(KO)".
    if re.search(rf"\({re.escape(symbol)}\)", headline):
        return True

    # Bare uppercase symbol, but only when long enough to be unambiguous.
    if len(symbol) >= MIN_SYMBOL_LEN:
        if re.search(rf"\b{re.escape(symbol)}\b", headline):
            return True

    return False


def relevance_flags(rows: list[tuple[int, str, str]]) -> list[tuple[int, int]]:
    """Map (id, symbol, headline) rows to (relevant_flag, id) update tuples."""
    return [(int(is_relevant(sym, text)), rid) for rid, sym, text in rows]