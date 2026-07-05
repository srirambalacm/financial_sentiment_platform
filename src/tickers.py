"""The ticker universe tracked by FinSent.

We deliberately keep this to a curated set of ~25 large-cap, highly liquid
S&P 500 names across sectors. Liquid names have dense news coverage, which
gives the sentiment model plenty of signal to work with.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ticker:
    symbol: str
    name: str
    sector: str


UNIVERSE: list[Ticker] = [
    # Technology
    Ticker("AAPL", "Apple Inc.", "Technology"),
    Ticker("MSFT", "Microsoft Corp.", "Technology"),
    Ticker("NVDA", "NVIDIA Corp.", "Technology"),
    Ticker("AVGO", "Broadcom Inc.", "Technology"),
    Ticker("ORCL", "Oracle Corp.", "Technology"),
    # Communication Services
    Ticker("GOOGL", "Alphabet Inc.", "Communication Services"),
    Ticker("META", "Meta Platforms Inc.", "Communication Services"),
    Ticker("NFLX", "Netflix Inc.", "Communication Services"),
    # Consumer Discretionary
    Ticker("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    Ticker("TSLA", "Tesla Inc.", "Consumer Discretionary"),
    Ticker("HD", "Home Depot Inc.", "Consumer Discretionary"),
    Ticker("MCD", "McDonald's Corp.", "Consumer Discretionary"),
    # Financials
    Ticker("JPM", "JPMorgan Chase & Co.", "Financials"),
    Ticker("BAC", "Bank of America Corp.", "Financials"),
    Ticker("V", "Visa Inc.", "Financials"),
    Ticker("GS", "Goldman Sachs Group Inc.", "Financials"),
    # Health Care
    Ticker("UNH", "UnitedHealth Group Inc.", "Health Care"),
    Ticker("JNJ", "Johnson & Johnson", "Health Care"),
    Ticker("LLY", "Eli Lilly & Co.", "Health Care"),
    Ticker("PFE", "Pfizer Inc.", "Health Care"),
    # Energy
    Ticker("XOM", "Exxon Mobil Corp.", "Energy"),
    Ticker("CVX", "Chevron Corp.", "Energy"),
    # Consumer Staples
    Ticker("WMT", "Walmart Inc.", "Consumer Staples"),
    Ticker("KO", "Coca-Cola Co.", "Consumer Staples"),
    Ticker("PG", "Procter & Gamble Co.", "Consumer Staples"),
]


def symbols() -> list[str]:
    """Return just the ticker symbols in the universe."""
    return [t.symbol for t in UNIVERSE]
