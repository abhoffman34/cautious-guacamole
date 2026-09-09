#!/usr/bin/env python3
"""
Institutional Accumulation / Distribution Screener
==================================================

Implements the strategy described in "Institutional Investors Move Markets.
Here's How to Read Their Signs." (WSJ / IBD Insights, Sept. 7 2026).

The article's thesis: institutions are too big to hide. Their buying and selling
shows up as a signature in price *range* and *volume*:

  ACCUMULATION  - price closes in the upper part of its weekly range on
                  above-average volume, repeatedly, and holds a support floor.
  DISTRIBUTION  - price closes in the lower part of its range on above-average
                  volume; supply is being fed into strong demand.
  CHURN         - heavy volume, no price progress. Neither side winning.

This script turns that into six measurable components, scores every stock in a
universe 0-100, and writes a self-contained interactive HTML report.

Usage
-----
    pip install yfinance pandas numpy lxml
    python institutional_screener.py                    # S&P 500 + 400 + NDX
    python institutional_screener.py --universe sp500
    python institutional_screener.py --tickers-file my_watchlist.txt
    python institutional_screener.py --min-price 10 --min-dollar-vol 10e6

Outputs (into --outdir, default ./output):
    institutional_screener.html   <- open this
    screen_results.csv
    screen_results.json
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
import warnings
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    from report import write_report
except ImportError:
    # In the Colab notebook report.py's contents are defined in an earlier cell,
    # so write_report is already in the namespace and there is no module to import.
    pass

# ----------------------------------------------------------------------------
# Tunable parameters. Every threshold the strategy depends on lives here.
# ----------------------------------------------------------------------------

UD_WINDOW = 50          # article: "up/down volume ratio ... over a 50-day period"
WEEK_LOOKBACK = 8       # weeks of range/volume pattern to read
WEEK_VOL_MULT = 1.05    # a week counts as "heavy volume" above this x its 10wk avg
ACC_RANGE_POS = 0.60    # close in the top 40% of the weekly range = accumulation
DIST_RANGE_POS = 0.40   # close in the bottom 40% of the weekly range = distribution
AD_SLOPE_WINDOW = 25    # days for the Accumulation/Distribution line regression
PULLBACK_WINDOW = 15    # days over which to test whether selling volume is drying up
DIST_DAY_WINDOW = 25    # article: "many distribution days in a short period"
DIST_DAY_DROP = -0.002  # article: "closes 0.2% lower or more on higher volume"

# The article's -0.2% distribution-day rule is calibrated for an INDEX, whose
# daily standard deviation runs near 0.9%. That is about 0.22 sigma. Applied
# unchanged to a single stock - three to five times as volatile - a 0.2% down
# day is noise, and nearly every name looks like it is under distribution. So
# single stocks use the same rule expressed in their own sigma; indexes keep the
# literal threshold.
DIST_DAY_SIGMA = 0.22

# Score component maximums (sum = 100)
W_UD_RATIO = 30
W_WEEKLY = 25
W_AD_LINE = 20
W_PULLBACK = 10
W_VOL_EXPANSION = 5
W_TREND = 10

# Component bounds, calibrated against the 10th and 90th percentiles of a live
# 899-name scan so that each component spends its points across the field rather
# than handing most of them to everybody. Before this, pullback-dryness paid out
# 79% of its maximum with a third of names maxed and trend paid 68% with 40%
# maxed - 20 of the 100 points behaving as a constant. A component that almost
# everyone maxes is not scoring, it is padding.
PULLBACK_BOUNDS = (1.10, 0.68)      # (zero-point, full-marks) - lower is drier
VS_50DMA_BOUNDS = (-0.08, 0.10)
VS_200DMA_BOUNDS = (-0.12, 0.23)
OFF_HIGH_BOUNDS = (-0.36, -0.03)

# Classification is by rank within the scan, not by absolute score. Absolute
# cutoffs guessed ahead of time do not survive contact with a real cross-section:
# in the first live run the median stock scored 36 and landed in a band labelled
# "Distribution" while two thirds of the market sat above its 200-day average.
# (cumulative percentile from the bottom, label)
PCTILE_BANDS = [
    (0.95, "Strong Accumulation"),
    (0.80, "Accumulation"),
    (0.40, "Neutral / Churn"),
    (0.15, "Distribution"),
    (0.00, "Heavy Distribution"),
]

# Below this many names a percentile is meaningless, so fall back to absolutes.
PCTILE_MIN_N = 20
CLASS_BANDS = [
    (62, "Strong Accumulation"),
    (50, "Accumulation"),
    (35, "Neutral / Churn"),
    (22, "Distribution"),
    (0,  "Heavy Distribution"),
]

# A name cannot be called accumulation while the measure of accumulation itself
# is falling. In the first live run seven of the top twenty had a flat or
# negative A/D slope; the other components had simply outvoted the one that most
# directly answers the question being asked.
GATE_MIN_AD_SLOPE = 0.0
GATE_MIN_UD_RATIO = 1.0

# Fallback universe if Wikipedia is unreachable. Deliberately short - the most
# liquid US large caps - so the script degrades instead of dying.
FALLBACK_TICKERS = """
AAPL MSFT NVDA AMZN GOOGL GOOG META AVGO TSLA BRK-B LLY JPM V UNH XOM MA COST
HD PG JNJ WMT NFLX CRM BAC ABBV ORCL CVX KO AMD PEP MRK TMO ADBE LIN ACN CSCO
MCD ABT WFC DHR PM TXN GE INTU VZ IBM DIS QCOM AMGN CAT NOW NEE PFE UBER SPGI
CMCSA AMAT RTX HON UNP GS LOW ISRG BKNG COP AXP ELV SYK BLK PGR VRTX MU LRCX
TJX ADI SCHW MDT C REGN BSX PLD ETN MMC ADP CB DE PANW KLAC SO FI CI SBUX BMY
MDLZ ANET UPS ICE ZTS SHW GILD MO CME DUK EQIX WM PYPL CDNS SNPS APH MCK ITW
CSX AON PH TDG MSI NOC CL EOG PNC MMM USB FDX ORLY MAR MPC ROP EMR APD NSC
TGT AJG SLB HLT AFL NXPI PSX TRV DHI ABNB WMB DELL CRWD FTNT ADSK IDXX ROST
"""


# ----------------------------------------------------------------------------
# Universe construction
# ----------------------------------------------------------------------------

WIKI_HEADERS = {"User-Agent": "Mozilla/5.0 (screener; educational use)"}

# Column names vary a little between these tables, so each field lists the
# candidates in order of preference. GICS Sub-Industry is the important one: it
# is what separates four oil refiners from four independent Energy ideas, and it
# has been sitting in these tables all along.
WIKI_SOURCES = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    "ndx":   "https://en.wikipedia.org/wiki/Nasdaq-100",
}

WIKI_COLS = {
    "ticker": ["Symbol", "Ticker", "Ticker symbol"],
    "name": ["Security", "Company", "Company name"],
    "sector": ["GICS Sector", "Sector"],
    "sub_industry": ["GICS Sub-Industry", "GICS Sub Industry", "Sub-Industry"],
}

UNIVERSE_SETS = {
    "sp500": ["sp500"],
    "sp400": ["sp400"],
    "sp600": ["sp600"],
    "ndx": ["ndx"],
    "broad": ["sp500", "sp400", "ndx"],           # ~1,000 large and mid caps
    "wide": ["sp500", "sp400", "sp600", "ndx"],   # ~1,600, adds small caps
}


def _pick(table_cols, candidates):
    for c in candidates:
        if c in table_cols:
            return c
    return None


def _read_wiki_table(url: str) -> pd.DataFrame:
    import requests
    resp = requests.get(url, headers=WIKI_HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    for t in tables:
        cols = {str(c) for c in t.columns}
        tick = _pick(cols, WIKI_COLS["ticker"])
        name = _pick(cols, WIKI_COLS["name"])
        if not (tick and name):
            continue
        sector = _pick(cols, WIKI_COLS["sector"])
        sub = _pick(cols, WIKI_COLS["sub_industry"])
        if sector is None:          # a table with a ticker but no GICS data is
            continue                # some other table on the page
        return pd.DataFrame({
            "ticker": t[tick].astype(str).str.strip(),
            "name": t[name].astype(str).str.strip(),
            "sector": t[sector].astype(str).str.strip(),
            "sub_industry": (t[sub].astype(str).str.strip()
                             if sub else "Unknown"),
        })
    raise ValueError(f"no matching table at {url}")


def build_universe(which: str) -> pd.DataFrame:
    frames = []
    for key in UNIVERSE_SETS[which]:
        try:
            df = _read_wiki_table(WIKI_SOURCES[key])
            subs = df.sub_industry.nunique()
            print(f"  {key}: {len(df)} names, {subs} sub-industries")
            frames.append(df)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  {key}: FAILED ({exc})")

    if not frames:
        print("  falling back to the bundled large-cap list "
              "(index membership may be stale)")
        tick = FALLBACK_TICKERS.split()
        return pd.DataFrame({"ticker": tick, "name": tick, "sector": "Unknown",
                             "sub_industry": "Unknown"})

    uni = pd.concat(frames, ignore_index=True)
    uni["ticker"] = uni["ticker"].str.replace(".", "-", regex=False).str.upper()
    uni = uni.drop_duplicates(subset="ticker").reset_index(drop=True)
    return uni


def load_tickers_file(path: str) -> pd.DataFrame:
    with open(path) as fh:
        raw = [ln.split("#")[0].strip() for ln in fh]
    tick = [t.upper().replace(".", "-") for t in raw if t]
    return pd.DataFrame({"ticker": tick, "name": tick, "sector": "Unknown",
                         "sub_industry": "Unknown"})


# ----------------------------------------------------------------------------
# Data download
# ----------------------------------------------------------------------------

def download_prices(tickers: list[str], period: str = "2y",
                    batch: int = 100, pause: float = 1.0) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    total = len(tickers)
    for i in range(0, total, batch):
        chunk = tickers[i:i + batch]
        print(f"  downloading {i + 1}-{min(i + batch, total)} of {total} ...",
              flush=True)
        for attempt in range(3):
            try:
                data = yf.download(chunk, period=period, interval="1d",
                                   group_by="ticker", auto_adjust=True,
                                   threads=True, progress=False)
                break
            except Exception as exc:                              # noqa: BLE001
                if attempt == 2:
                    print(f"    batch failed: {exc}")
                    data = None
                else:
                    time.sleep(3 * (attempt + 1))
        if data is None:
            continue
        for t in chunk:
            try:
                df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            except KeyError:
                continue
            df = df.dropna(subset=["Close", "Volume"])
            if len(df) >= 220:
                out[t] = df
        if i + batch < total:
            time.sleep(pause)
    return out


# ----------------------------------------------------------------------------
# The metrics. Each is a direct translation of one idea in the article.
# ----------------------------------------------------------------------------

@dataclass
class Metrics:
    ticker: str
    name: str = ""
    sector: str = "Unknown"
    sub_industry: str = "Unknown"
    price: float = float("nan")
    avg_dollar_vol: float = float("nan")

    ud_ratio: float = float("nan")        # up/down volume ratio, 50d
    acc_weeks: int = 0                    # heavy-volume weeks closing high in range
    dist_weeks: int = 0                   # heavy-volume weeks closing low in range
    acc_streak: int = 0                   # longest consecutive accumulation run
    week_pressure: float = float("nan")   # continuous weekly range/volume pressure
    ad_slope: float = float("nan")        # A/D line slope, normalized
    pullback_dryness: float = float("nan")  # down-day volume vs 50d average
    vol_expansion: float = float("nan")   # 50d avg volume / 200d avg volume
    dist_days: int = 0                    # volatility-scaled, last 25 sessions

    pct_vs_50dma: float = float("nan")
    pct_vs_200dma: float = float("nan")
    pct_off_high: float = float("nan")
    ret_63d: float = float("nan")

    score: float = 0.0
    art_score: float = 0.0               # the article's own tests, scored alone
    art_rank: int = 0
    ex_mom: float = float("nan")          # score minus what 63d return alone predicts
    pctile: float = float("nan")          # rank within this scan, 0-100
    sector_pctile: float = float("nan")   # rank within its own sector, 0-100
    sector_delta: float = float("nan")    # score minus its sector's median score
    sub_pctile: float = float("nan")      # rank within its own sub-industry
    components: dict = field(default_factory=dict)
    classification: str = ""
    churn_flag: bool = False
    gated: bool = False                   # capped by the A/D gate
    week_pattern: list = field(default_factory=list)  # last 8 weeks: A / D / -


def up_down_volume_ratio(df: pd.DataFrame, window: int = UD_WINDOW) -> float:
    """The article's headline gauge: up-day volume divided by down-day volume."""
    d = df.tail(window + 1)
    chg = d["Close"].diff()
    vol = d["Volume"]
    up = vol[chg > 0].sum()
    down = vol[chg < 0].sum()
    if down <= 0:
        return 9.99 if up > 0 else float("nan")
    return float(min(up / down, 9.99))


def weekly_pattern(df: pd.DataFrame, lookback: int = WEEK_LOOKBACK):
    """Where in its weekly range did the stock close, and on what volume.

    The article's core visual: 'shares closed near the top of their trading
    range during the week ... on heavy volume. This pattern was repeated for
    several consecutive weeks.'
    """
    wk = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last", "Volume": "sum"}).dropna()
    if len(wk) < 14:
        return 0, 0, 0, [], float("nan")

    rng = (wk["High"] - wk["Low"]).replace(0, np.nan)
    pos = ((wk["Close"] - wk["Low"]) / rng).fillna(0.5)
    avg_vol = wk["Volume"].rolling(10).mean().shift(1)
    vol_mult = (wk["Volume"] / avg_vol).clip(0.5, 2.0)
    heavy = wk["Volume"] >= WEEK_VOL_MULT * avg_vol

    acc = (pos >= ACC_RANGE_POS) & heavy
    dist = (pos <= DIST_RANGE_POS) & heavy

    # Continuous weekly pressure. Counting weeks that cross a threshold throws
    # away most of the signal: a week closing at 59% of its range on 1.04x volume
    # scores identically to one closing at 5% on half volume. Every week now
    # contributes its own range position, weighted by how heavy its volume was.
    # Range: about -2 (every week closing at its low on double volume) to +2.
    pressure = float(((pos - 0.5) * 2 * vol_mult).tail(lookback).mean())

    a = acc.tail(lookback)
    d = dist.tail(lookback)
    p = pos.tail(lookback)

    pattern = []
    for ts, is_a, is_d, pv in zip(a.index, a.values, d.values, p.values):
        pattern.append({
            "week": ts.strftime("%b %d"),
            "kind": "A" if is_a else ("D" if is_d else "-"),
            "pos": round(float(pv), 3),
        })

    streak = best = 0
    for is_a in a.values:
        streak = streak + 1 if is_a else 0
        best = max(best, streak)

    return int(a.sum()), int(d.sum()), int(best), pattern, pressure


def ad_line_slope(df: pd.DataFrame, window: int = AD_SLOPE_WINDOW) -> float:
    """Slope of the classic Accumulation/Distribution line, in units of
    'average daily volumes accumulated per day' so it compares across stocks."""
    d = df.tail(window + 60)
    rng = (d["High"] - d["Low"]).replace(0, np.nan)
    mfm = (((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / rng).fillna(0)
    ad = (mfm * d["Volume"]).cumsum()
    y = ad.tail(window).to_numpy(dtype=float)
    if len(y) < window:
        return float("nan")
    x = np.arange(len(y), dtype=float)
    slope = np.polyfit(x, y, 1)[0]
    denom = float(d["Volume"].tail(50).mean())
    return float(slope / denom) if denom > 0 else float("nan")


def pullback_dryness(df: pd.DataFrame, window: int = PULLBACK_WINDOW) -> float:
    """'The stock pulled back ... but that was accompanied by lower volume,
    indicating that institutions were taking a break from buying.'

    Down-day volume over the recent window, relative to the 50-day average.
    Below 1.0 means selling is happening on thin volume - a healthy pullback.
    """
    d = df.tail(window + 1)
    chg = d["Close"].diff()
    down_vol = d["Volume"][chg < 0]
    base = float(df["Volume"].tail(50).mean())
    if len(down_vol) == 0 or base <= 0:
        return 0.7          # no down days at all reads as maximally dry
    return float(down_vol.mean() / base)


def distribution_days(df: pd.DataFrame, window: int = DIST_DAY_WINDOW,
                      threshold: float | None = None) -> int:
    """'A distribution day occurs when [it] closes 0.2% lower or more on
    higher volume.'

    threshold=None scales that rule to the instrument's own volatility, which is
    what single stocks need. Pass DIST_DAY_DROP for the article's literal index
    figure.
    """
    d = df.tail(window + 1)
    ret = d["Close"].pct_change()
    if threshold is None:
        sigma = float(df["Close"].pct_change().tail(100).std())
        threshold = (-DIST_DAY_SIGMA * sigma
                     if np.isfinite(sigma) and sigma > 0 else DIST_DAY_DROP)
    vol_up = d["Volume"].diff() > 0
    return int(((ret <= threshold) & vol_up).sum())


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------

def _lin(x, lo, hi, out_max):
    """Linear map of x from [lo, hi] onto [0, out_max], clipped."""
    if not np.isfinite(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0, 1) * out_max)


def score_stock(m: Metrics) -> Metrics:
    c = {}

    # 1. Up/down volume ratio. Scored on a log scale: 0.7 -> 0, 2.5 -> full.
    #    The article calls 2.0 strong, 1.0 churn, below 1.0 distribution.
    r = m.ud_ratio
    c["Up/down volume (50d)"] = (
        _lin(math.log(r), math.log(0.70), math.log(2.50), W_UD_RATIO)
        if np.isfinite(r) and r > 0 else 0.0)

    # 2. Weekly close-in-range pressure (continuous), plus a bonus for
    #    consecutive accumulation weeks ("repeated for several consecutive weeks").
    c["Weekly range + volume"] = (_lin(m.week_pressure, -0.45, 0.55, W_WEEKLY * 0.8)
                                  + _lin(m.acc_streak, 0, 3, W_WEEKLY * 0.2))

    # 3. A/D line direction.
    c["A/D line slope (25d)"] = _lin(m.ad_slope, -0.25, 0.45, W_AD_LINE)

    # 4. Are pullbacks happening on drying volume? Bounds sit at the field's
    #    p90/p10 so the median name lands mid-scale instead of maxing out.
    c["Pullback volume drying"] = _lin(m.pullback_dryness, *PULLBACK_BOUNDS,
                                       W_PULLBACK)

    # 5. Is volume expanding at all? No footprints, no institutions. The band is
    #    centred below 1.0 because a 50-day window sitting inside the summer lull
    #    reads low against a 200-day for purely seasonal reasons - at 0.95 the
    #    old floor half the market scored zero here every August.
    c["Volume expansion"] = _lin(m.vol_expansion, 0.80, 1.30, W_VOL_EXPANSION)

    # 6. Trend/support context. Accumulation only counts if price holds a floor.
    #    Continuous rather than pass/fail: a stock 0.1% above its 50-day average
    #    was previously scored identically to one 20% above, which is why 40% of
    #    the field maxed this component.
    trend = (_lin(m.pct_vs_50dma, *VS_50DMA_BOUNDS, 4)
             + _lin(m.pct_vs_200dma, *VS_200DMA_BOUNDS, 3)
             + _lin(m.pct_off_high, *OFF_HIGH_BOUNDS, 3))
    c["Trend / support"] = trend

    m.components = {k: round(v, 2) for k, v in c.items()}
    m.score = round(float(sum(c.values())), 1)

    # Churn: heavy volume, no progress, ratio pinned near 1.0.
    m.churn_flag = bool(
        np.isfinite(m.vol_expansion) and m.vol_expansion > 1.15
        and np.isfinite(m.ret_63d) and abs(m.ret_63d) < 0.04
        and np.isfinite(m.ud_ratio) and 0.85 <= m.ud_ratio <= 1.20
    )
    return m


def article_score(m: Metrics) -> float:
    """A second, independent ranking built ONLY from what the article asserts.

    The composite score is my construction and reflects choices the article never
    makes - an A/D-line component, a momentum residual, sector neutrality. This
    function deliberately makes none of them. It scores each name against the
    article's own tests, in the article's own emphasis, so the two rankings can
    be compared and their disagreements read.

    The tests, and where they come from:
      "a stock's up/down volume ratio ... A resulting ratio of 2.0 means twice as
       much up volume ... a ratio below 1.0 points to heavier volume on down
       days"                                                        -> 30 points
      "shares closed near the top of their trading range ... on heavy volume.
       This pattern was repeated for several consecutive weeks"     -> 25 points
      "the stock pulled back ... accompanied by lower volume, indicating that
       institutions were taking a break from buying"                -> 15 points
      "institutions can keep a stock's price high ... creating what's called
       support", and its example had already made "an impressive run" -> 20 points
      "many distribution days in a short period is an early warning"  -> 10 points

    Note what this rewards that the composite does not: a stock that has ALREADY
    run. The article's worked example was up 500% on the year and still being
    accumulated. This is a momentum-continuation framework, not a bottom-fishing
    one, and scoring it faithfully means saying so.
    """
    s = 0.0
    # 1. The up/down volume ratio, the article's headline gauge. 1.0 earns
    #    nothing (its definition of churn); 2.0 earns full marks; above that a
    #    little extra, capped.
    if np.isfinite(m.ud_ratio):
        s += float(np.clip((m.ud_ratio - 1.0) / 1.0, 0, 1.4)) * 30

    # 2. Closing high in the weekly range on heavy volume, REPEATED. The
    #    consecutive run carries most of the weight because the article's own
    #    example turns on repetition, not on any single week.
    s += float(np.clip(m.acc_streak / 3, 0, 1)) * 18
    s += float(np.clip((m.acc_weeks - m.dist_weeks) / 4, 0, 1)) * 7

    # 3. Pullbacks arriving on lighter volume.
    if np.isfinite(m.pullback_dryness):
        s += float(np.clip((1.05 - m.pullback_dryness) / 0.30, 0, 1)) * 15

    # 4. The support floor holding, and a run already under way.
    if np.isfinite(m.pct_vs_50dma):
        s += float(np.clip(m.pct_vs_50dma / 0.10, 0, 1)) * 8
    if np.isfinite(m.pct_off_high):
        s += float(np.clip((m.pct_off_high + 0.20) / 0.20, 0, 1)) * 6
    if np.isfinite(m.ret_63d):
        s += float(np.clip(m.ret_63d / 0.30, 0, 1)) * 6

    # 5. Distribution days, few.
    s += float(np.clip((6 - m.dist_days) / 5, 0, 1)) * 10

    # The up/down term is allowed to overshoot its 30 points (the article treats
    # 2.0 as strong, not as a ceiling), so the raw total can pass 100. Clamp it,
    # so the column stays on the same 0-100 scale as the composite and a name
    # can reach 100 on exceptional volume without having to max every other test.
    return round(min(s, 100.0), 1)


def classify(results: list[Metrics]) -> None:
    """Assigns each name a percentile and a band, then applies the A/D gate.

    Bands are relative to the scan, so "Strong Accumulation" always means the top
    5% of what was actually scanned - never an absolute score that may or may not
    be reachable in a given tape. The gate is the absolute check that keeps a
    relative label honest.
    """
    n = len(results)
    if n == 0:
        return

    if n < PCTILE_MIN_N:
        for m in results:
            m.pctile = float("nan")
            for cutoff, label in CLASS_BANDS:
                if m.score >= cutoff:
                    m.classification = label
                    break
    else:
        ranked = sorted(results, key=lambda x: x.score)
        for i, m in enumerate(ranked):
            p = i / (n - 1)
            m.pctile = round(100 * p, 1)
            for cutoff, label in PCTILE_BANDS:
                if p >= cutoff:
                    m.classification = label
                    break

    for m in results:
        if m.classification in ("Strong Accumulation", "Accumulation"):
            ad_ok = np.isfinite(m.ad_slope) and m.ad_slope > GATE_MIN_AD_SLOPE
            ud_ok = np.isfinite(m.ud_ratio) and m.ud_ratio > GATE_MIN_UD_RATIO
            if not (ad_ok and ud_ok):
                m.classification = "Neutral / Churn"
                m.gated = True


def add_momentum_residual(results: list[Metrics]) -> dict:
    """The score correlates ~0.7 with the trailing 63-day return, partly by
    construction: a stock that rose had more up days, and up days carry the
    volume. So report what is left after the return is regressed out - the part
    of the accumulation signal the price has not already told you.

    A positive ex-momentum figure means more institutional footprint than this
    stock's own price action would lead you to expect.

    The regression runs against the *rank* of the 63-day return rather than the
    return itself. Raw returns have a long right tail - one name up 207% drags a
    least-squares line badly and hands quiet stocks residuals of -70 on a scale
    that only spans 100. Rank is bounded, so no single moonshot distorts the rest.
    """
    raw = np.array([m.ret_63d for m in results], dtype=float)
    y = np.array([m.score for m in results], dtype=float)
    ok = np.isfinite(raw) & np.isfinite(y)
    if ok.sum() < PCTILE_MIN_N:
        for m in results:
            m.ex_mom = float("nan")
        return {}

    x = np.full(len(raw), np.nan)
    x[ok] = pd.Series(raw[ok]).rank(pct=True).to_numpy()
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    r = float(np.corrcoef(x[ok], y[ok])[0, 1])
    for m, xi in zip(results, x):
        m.ex_mom = (round(float(m.score - (slope * xi + intercept)), 1)
                    if np.isfinite(xi) else float("nan"))
    return {"slope": float(slope), "intercept": float(intercept),
            "r2": round(r * r, 3), "n": int(ok.sum())}


SECTOR_MIN_N = 8        # below this a within-sector percentile is meaningless
SUB_MIN_N = 5           # sub-industries are smaller, so a lower floor


def add_sector_ranks(results: list[Metrics], top_n: int = 50) -> dict:
    """Ranks each name against its own sector, and measures how concentrated the
    top of the overall list is.

    A screen that sorts the whole market on one number will hand you whichever
    sector the macro currently favours. In the live run eight of the top fifty
    were Energy against 2.1 expected, four of them refiners sitting in the top
    fourteen - one bet on crack spreads wearing four tickers, not four
    independent institutional decisions. Sector percentile answers the different
    and more useful question: is this name being accumulated relative to the
    other places that money could sit inside its own sector?
    """
    by_sector: dict[str, list[Metrics]] = {}
    for m in results:
        by_sector.setdefault(m.sector or "Unknown", []).append(m)

    stats = {}
    for sector, group in by_sector.items():
        scores = sorted(m.score for m in group)
        median = float(np.median(scores)) if scores else float("nan")
        stats[sector] = {"n": len(group), "median": round(median, 1),
                         "top": round(max(scores), 1) if scores else None}
        if len(group) < SECTOR_MIN_N:
            continue
        ranked = sorted(group, key=lambda x: x.score)
        for i, m in enumerate(ranked):
            m.sector_pctile = round(100 * i / (len(ranked) - 1), 1)
            m.sector_delta = round(m.score - median, 1)

    # The same, one level down. Sector is too coarse to catch the real problem:
    # four oil refiners are one bet on crack spreads, but GICS calls them all
    # "Energy" alongside pipelines and drillers.
    by_sub: dict[str, list[Metrics]] = {}
    for m in results:
        by_sub.setdefault(m.sub_industry or "Unknown", []).append(m)
    for sub, group in by_sub.items():
        if len(group) < SUB_MIN_N or sub == "Unknown":
            continue
        ranked = sorted(group, key=lambda x: x.score)
        for i, m in enumerate(ranked):
            m.sub_pctile = round(100 * i / (len(ranked) - 1), 1)

    # Concentration of the overall top N against what the field share predicts.
    top = sorted(results, key=lambda x: x.score, reverse=True)[:top_n]
    n = len(results)
    conc = []
    for sector, group in by_sector.items():
        got = sum(1 for m in top if (m.sector or "Unknown") == sector)
        expected = top_n * len(group) / n
        if got and expected > 0 and got >= 1.6 * expected and got >= 3:
            conc.append({"sector": sector, "got": got,
                         "expected": round(expected, 1),
                         "ratio": round(got / expected, 1),
                         "tickers": [m.ticker for m in top
                                     if (m.sector or "Unknown") == sector]})
    conc.sort(key=lambda d: d["ratio"], reverse=True)

    # Sub-industry clusters in the top N. Three names from one sub-industry is
    # already a cluster worth naming, whatever the expected share says.
    sub_conc = []
    for sub, group in by_sub.items():
        if sub == "Unknown":
            continue
        got = [m.ticker for m in top if (m.sub_industry or "Unknown") == sub]
        if len(got) >= 3:
            sub_conc.append({"sub_industry": sub, "got": len(got),
                             "expected": round(top_n * len(group) / n, 1),
                             "tickers": got})
    sub_conc.sort(key=lambda d: d["got"], reverse=True)
    return {"sectors": stats, "concentration": conc,
            "sub_concentration": sub_conc, "top_n": top_n}


def analyze(ticker: str, df: pd.DataFrame, name: str, sector: str,
            sub_industry: str = "Unknown") -> Metrics | None:
    if len(df) < 220:
        return None
    close, vol = df["Close"], df["Volume"]

    m = Metrics(ticker=ticker, name=name, sector=sector,
                sub_industry=sub_industry)
    m.price = float(close.iloc[-1])
    m.avg_dollar_vol = float((close * vol).tail(50).mean())

    m.ud_ratio = up_down_volume_ratio(df)
    (m.acc_weeks, m.dist_weeks, m.acc_streak,
     m.week_pattern, m.week_pressure) = weekly_pattern(df)
    m.ad_slope = ad_line_slope(df)
    m.pullback_dryness = pullback_dryness(df)
    v50, v200 = float(vol.tail(50).mean()), float(vol.tail(200).mean())
    m.vol_expansion = v50 / v200 if v200 > 0 else float("nan")
    m.dist_days = distribution_days(df)

    ma50, ma200 = float(close.tail(50).mean()), float(close.tail(200).mean())
    hi52 = float(close.tail(252).max())
    m.pct_vs_50dma = m.price / ma50 - 1 if ma50 else float("nan")
    m.pct_vs_200dma = m.price / ma200 - 1 if ma200 else float("nan")
    m.pct_off_high = m.price / hi52 - 1 if hi52 else float("nan")
    m.ret_63d = float(close.iloc[-1] / close.iloc[-64] - 1) if len(close) > 64 else float("nan")

    m = score_stock(m)
    m.art_score = article_score(m)
    return m


# ----------------------------------------------------------------------------
# Market health - the article applies distribution days to the indexes
# ----------------------------------------------------------------------------

def market_health() -> list[dict]:
    import yfinance as yf
    out = []
    for sym, label in [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq Composite")]:
        try:
            df = yf.download(sym, period="6mo", interval="1d",
                             auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "Volume"])
            n = distribution_days(df, threshold=DIST_DAY_DROP)  # the literal rule
            if n <= 2:
                state, note = "good", "Institutions are not exiting."
            elif n <= 4:
                state, note = "warning", "Watch. Pressure is building."
            else:
                state, note = "critical", "Heavy selling. Be defensive."
            out.append({"label": label, "count": n, "state": state, "note": note,
                        "last": float(df["Close"].iloc[-1]),
                        "chg": float(df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1)})
        except Exception as exc:                                  # noqa: BLE001
            print(f"  market health {sym} failed: {exc}")
    return out


# ----------------------------------------------------------------------------
# The screen itself. main() is a thin argparse wrapper around this, and the
# Colab notebook calls it directly - one code path, one thing to test.
# ----------------------------------------------------------------------------

def run_screen(universe: str = "broad", tickers_file: str | None = None,
               outdir: str = "output", min_price: float = 7.0,
               min_dollar_vol: float = 5e6, period: str = "2y",
               batch: int = 100, limit: int | None = None) -> dict:
    """Runs the full screen and writes the report. Returns the payload dict."""
    os.makedirs(outdir, exist_ok=True)

    print("Building universe ...")
    uni = (load_tickers_file(tickers_file) if tickers_file
           else build_universe(universe))
    if limit:
        uni = uni.head(limit)
    print(f"  {len(uni)} tickers\n")

    print("Downloading price history (this is the slow part) ...")
    prices = download_prices(uni["ticker"].tolist(), period=period, batch=batch)
    print(f"  usable history for {len(prices)} of {len(uni)}\n")

    if not prices:
        raise RuntimeError("No price data came back. Check the network "
                           "connection to Yahoo Finance and try again.")

    print("Scoring ...")
    meta = uni.set_index("ticker")
    results: list[Metrics] = []
    for t, df in prices.items():
        try:
            row = meta.loc[t]
            m = analyze(t, df, str(row["name"]), str(row["sector"]),
                        str(row.get("sub_industry", "Unknown")))
        except Exception:                                         # noqa: BLE001
            continue
        if m is None:
            continue
        if m.price < min_price or m.avg_dollar_vol < min_dollar_vol:
            continue
        results.append(m)

    print(f"  {len(results)} passed the liquidity filter")

    # Cross-sectional passes: banding, the gate, and the momentum residual all
    # need the whole field, so they happen once here rather than per stock.
    classify(results)
    for i, m in enumerate(sorted(results, key=lambda x: x.art_score, reverse=True), 1):
        m.art_rank = i
    fit = add_momentum_residual(results)
    sectors = add_sector_ranks(results)
    gated = sum(1 for m in results if m.gated)
    if fit:
        print(f"  score vs 63-day return: R^2 {fit['r2']:.2f} "
              f"(the ex-momentum column strips this out)")
    if gated:
        print(f"  {gated} names capped by the A/D gate "
              f"(labelled accumulation with a falling A/D line)")
    for cx in sectors.get("sub_concentration", []):
        print(f"  cluster: {cx['got']} of the top {sectors['top_n']} are "
              f"{cx['sub_industry']} - {', '.join(cx['tickers'][:6])}")
    for cx in sectors["concentration"]:
        print(f"  concentration: {cx['got']} of the top {sectors['top_n']} are "
              f"{cx['sector']} vs {cx['expected']} expected ({cx['ratio']}x) - "
              f"{', '.join(cx['tickers'][:6])}"
              f"{' ...' if len(cx['tickers']) > 6 else ''}")
    print()

    results.sort(key=lambda x: x.score, reverse=True)
    for i, m in enumerate(results, 1):
        m.components["_rank"] = i

    print("Checking market health ...")
    health = market_health()
    for h in health:
        print(f"  {h['label']}: {h['count']} distribution days in "
              f"the last {DIST_DAY_WINDOW} sessions - {h['note']}")

    rows = [asdict(m) for m in results]
    for r in rows:
        r["rank"] = r["components"].pop("_rank")

    df_out = pd.DataFrame([{k: v for k, v in r.items()
                            if k not in ("components", "week_pattern")}
                           for r in rows])
    csv_path = os.path.join(outdir, "screen_results.csv")
    df_out.to_csv(csv_path, index=False)

    payload = {
        "generated": datetime.now(timezone.utc).astimezone().strftime("%b %d, %Y %I:%M %p %Z"),
        "universe": tickers_file or universe,
        "count": len(rows),
        "scanned": len(prices),
        "params": {"ud_window": UD_WINDOW, "week_lookback": WEEK_LOOKBACK,
                   "universe_set": UNIVERSE_SETS.get(universe, []),
                   "dist_day_window": DIST_DAY_WINDOW,
                   "dist_day_sigma": DIST_DAY_SIGMA,
                   "min_price": min_price, "min_dollar_vol": min_dollar_vol},
        "fit": fit,
        "gated": gated,
        "sectors": sectors,
        "health": health,
        "rows": rows,
    }
    json_path = os.path.join(outdir, "screen_results.json")
    with open(json_path, "w") as fh:
        json.dump(payload, fh, default=float)

    html_path = os.path.join(outdir, "institutional_screener.html")
    write_report(payload, html_path)

    print(f"\nWrote:\n  {html_path}\n  {csv_path}\n  {json_path}")
    print("\nTop 10 by institutional accumulation score:")
    for m in results[:10]:
        print(f"  {m.ticker:<6} {m.score:5.1f}  U/D {m.ud_ratio:4.2f}  "
              f"acc wks {m.acc_weeks}/{WEEK_LOOKBACK}  {m.classification}")

    ex = sorted((m for m in results if np.isfinite(m.ex_mom) and not m.gated),
                key=lambda x: x.ex_mom, reverse=True)[:10]
    if ex:
        print("\nTop 10 ex-momentum, gate-clean "
              "(accumulation the price has not shown yet):")
        for m in ex:
            print(f"  {m.ticker:<6} ex-mom {m.ex_mom:+5.1f}  score {m.score:5.1f}  "
                  f"63d return {m.ret_63d:+6.1%}")

    art = sorted(results, key=lambda x: x.art_score, reverse=True)[:10]
    print("\nTop 10 on the article's own criteria (independent of the composite):")
    for m in art:
        print(f"  {m.ticker:<6} article {m.art_score:5.1f}  composite {m.score:5.1f}  "
              f"U/D {m.ud_ratio:4.2f}  streak {m.acc_streak}")

    best = {}
    for m in results:
        if np.isfinite(m.sector_pctile):
            cur = best.get(m.sector)
            if cur is None or m.score > cur.score:
                best[m.sector] = m
    if best:
        print("\nBest name in each sector (the de-clustered list):")
        for sector, m in sorted(best.items(), key=lambda kv: -kv[1].score):
            print(f"  {sector:<24} {m.ticker:<6} score {m.score:5.1f}  "
                  f"ex-mom {m.ex_mom:+5.1f}  {m.classification}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", default="broad",
                    choices=list(UNIVERSE_SETS),
                    help="broad = S&P 500+400+NDX (~1,000); "
                         "wide adds S&P 600 small caps (~1,600)")
    ap.add_argument("--tickers-file", help="one ticker per line; overrides --universe")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--min-price", type=float, default=7.0)
    ap.add_argument("--min-dollar-vol", type=float, default=5e6,
                    help="minimum 50-day average dollar volume")
    ap.add_argument("--period", default="2y")
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--limit", type=int, help="cap universe size (for a quick test)")
    args = ap.parse_args()
    try:
        run_screen(universe=args.universe, tickers_file=args.tickers_file,
                   outdir=args.outdir, min_price=args.min_price,
                   min_dollar_vol=args.min_dollar_vol, period=args.period,
                   batch=args.batch, limit=args.limit)
    except RuntimeError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
