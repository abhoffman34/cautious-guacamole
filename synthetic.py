"""Synthetic price histories with known institutional behaviour, used by the tests."""

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
DAYS = 420
IDX = pd.bdate_range("2024-12-02", periods=DAYS)


def make(regime: str, base_vol=4_000_000, start=100.0) -> pd.DataFrame:
    """regime: 'accum' | 'dist' | 'churn' | 'dry_pullback'"""
    drift = {"accum": 0.0016, "dist": -0.0016, "churn": 0.0, "dry_pullback": 0.0012}[regime]
    close = start * np.cumprod(1 + drift + rng.normal(0, 0.013, DAYS))

    if regime == "dry_pullback":
        # a 20-day pullback at the end, on thin volume
        close[-20:] = close[-21] * np.cumprod(1 + rng.normal(-0.0018, 0.008, 20))

    chg = np.diff(close, prepend=close[0])
    up = chg > 0

    # Where in the day's range does it close? This is the institutional tell.
    where = {"accum": 0.80, "dist": 0.20, "churn": 0.50, "dry_pullback": 0.72}[regime]
    where_arr = np.clip(rng.normal(where, 0.10, DAYS), 0.05, 0.95)

    span = close * rng.uniform(0.012, 0.028, DAYS)
    low = close - where_arr * span
    high = low + span
    open_ = np.clip(low + rng.uniform(0.2, 0.8, DAYS) * span, low, high)

    vol = base_vol * rng.uniform(0.85, 1.15, DAYS)
    if regime == "accum":
        vol = np.where(up, vol * 1.55, vol * 0.80)
        vol[-40:] *= 1.35                       # institutions stepping in
    elif regime == "dist":
        vol = np.where(up, vol * 0.80, vol * 1.55)
        vol[-40:] *= 1.35
    elif regime == "churn":
        vol *= 1.35                             # heavy volume, no progress
    elif regime == "dry_pullback":
        vol = np.where(up, vol * 1.4, vol * 0.9)
        vol[-20:] *= 0.55                       # the pullback dries up

    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=IDX)


def check(name, got, cond, expect):
    ok = "PASS" if cond else "FAIL"
    print(f"  [{ok}] {name}: {got}   (expected {expect})")
    return cond


