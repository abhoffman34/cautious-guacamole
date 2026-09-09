"""Verification: build synthetic price histories with known institutional
behaviour and confirm the metrics read them the way the article says they should.

Also writes a sample HTML report so the layout can be inspected without a
live data pull.
"""

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from institutional_screener import (analyze, up_down_volume_ratio, weekly_pattern,
                                    distribution_days, pullback_dryness, classify,
                                    add_momentum_residual, ad_line_slope, Metrics,
                                    DIST_DAY_DROP, DIST_DAY_SIGMA, add_sector_ranks,
                                    _lin, PULLBACK_BOUNDS, VS_50DMA_BOUNDS,
                                    VS_200DMA_BOUNDS, OFF_HIGH_BOUNDS,
                                    article_score, UNIVERSE_SETS)
from report import write_report

from synthetic import make, check

def frame(bars):
    """bars: list of (open, high, low, close, volume)"""
    idx = pd.bdate_range("2026-01-01", periods=len(bars))
    return pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"],
                        index=idx)


print("Deterministic unit tests (hand-built bars, exact answers)\n" + "-" * 62)
ok = True

# -- up/down volume ratio: 3 up days at 200 volume, 2 down days at 100 -> 3.0
b = [(0, 0, 0, 100, 100)]
for c, v in [(101, 200), (102, 200), (101, 100), (102, 200), (101, 100)]:
    b.append((0, 0, 0, c, v))
r = up_down_volume_ratio(frame(b), window=5)
ok &= check("up/down ratio on 600 up vs 200 down volume", f"{r:.2f}", abs(r - 3.0) < 1e-9, "3.00")

# -- distribution days: exactly the bars that drop >=0.2% on rising volume
b = [(0, 0, 0, 100.0, 1000),
     (0, 0, 0, 99.5, 1200),    # -0.50%, volume up   -> counts
     (0, 0, 0, 99.0, 900),     # -0.50%, volume down -> no
     (0, 0, 0, 98.95, 1500),   # -0.05%, too small   -> no
     (0, 0, 0, 100.0, 1800),   # up day              -> no
     (0, 0, 0, 99.6, 2000)]    # -0.40%, volume up   -> counts
dd = distribution_days(frame(b), window=5, threshold=DIST_DAY_DROP)
ok &= check("distribution days in a 5-day window with 2 qualifying", dd, dd == 2, "2")

# -- the same rule, scaled to the instrument's own volatility, must be stricter
#    on a volatile stock than the index-calibrated -0.2% ever is
vol_stock = make("churn")                      # ~1.3% daily sigma
fixed = distribution_days(vol_stock, threshold=DIST_DAY_DROP)
scaled = distribution_days(vol_stock)
ok &= check("vol-scaled distribution days on a volatile stock",
            f"{scaled} scaled vs {fixed} at the flat -0.2%", scaled < fixed,
            "fewer - a 0.2% down day is noise for a single stock")
sigma = float(vol_stock["Close"].pct_change().tail(100).std())
ok &= check("the scaled threshold reproduces ~0.2% at index-like volatility",
            f"{-DIST_DAY_SIGMA * 0.009:.4f} at sigma=0.9%",
            abs(-DIST_DAY_SIGMA * 0.009 - DIST_DAY_DROP) < 0.0005, "about -0.0020")

# -- weekly range position: closing at the weekly high on heavy volume
b = []
for w in range(14):                       # 14 weeks, last 4 heavy-volume and strong
    for d in range(5):
        base = 100 + w
        heavy = w >= 10
        b.append((base, base + 2, base - 2, base + 2 if heavy else base,
                  3000 if heavy else 1000))
a_w, d_w, streak, pat, press = weekly_pattern(frame(b), lookback=8)
ok &= check("weeks closing at the top of range on 3x volume", f"{a_w} acc, streak {streak}",
            a_w >= 3 and streak >= 3, ">= 3 accumulation weeks, consecutive")
ok &= check("no distribution weeks in that pattern", d_w, d_w == 0, "0")
ok &= check("weekly pressure is strongly positive there", f"{press:.2f}",
            press > 0.8, "> 0.8 on a +-2 scale")

# -- continuous pressure must separate a 59%-of-range week from a 5% one, where
#    the old threshold count scored both as zero
near = [(100, 102, 98, 100 + 2 * (2 * 0.59 - 1), 1000) for _ in range(70)]
weak = [(100, 102, 98, 100 + 2 * (2 * 0.05 - 1), 1000) for _ in range(70)]
_, _, _, _, p_near = weekly_pattern(frame(near))
_, _, _, _, p_weak = weekly_pattern(frame(weak))
ok &= check("pressure separates a 59%-of-range close from a 5% one",
            f"{p_near:.2f} vs {p_weak:.2f}", p_near > p_weak + 0.5,
            "clearly higher (both scored 0 accumulation weeks under the old count)")

# -- A/D line: closing at the high every day must slope up
b = [(100, 102, 98, 102, 1000) for _ in range(120)]
slope_up = ad_slope_check = None
from institutional_screener import ad_line_slope
slope_up = ad_line_slope(frame(b))
ok &= check("A/D slope when every close is at the high", f"{slope_up:.2f}", slope_up > 0.9, "> 0.9")
b = [(100, 102, 98, 98, 1000) for _ in range(120)]
slope_dn = ad_line_slope(frame(b))
ok &= check("A/D slope when every close is at the low", f"{slope_dn:.2f}", slope_dn < -0.9, "< -0.9")

print("\nMetric behaviour on synthetic histories\n" + "-" * 62)

acc = make("accum")
dis = make("dist")
chu = make("churn")
dry = make("dry_pullback")

print("\nAccumulation stock (the Sandisk pattern in the article):")
r = up_down_volume_ratio(acc)
ok &= check("up/down volume ratio", f"{r:.2f}", r > 1.6, "> 1.6, article calls 2.0 strong")
a, d, s, _, press_a = weekly_pattern(acc)
ok &= check("accumulation weeks of 8", f"{a} acc / {d} dist", a >= 3 and a > d, "several, and more than distribution")
ok &= check("consecutive run", s, s >= 2, ">= 2, 'repeated for several consecutive weeks'")

print("\nDistribution stock (the Trade Desk pattern):")
r = up_down_volume_ratio(dis)
ok &= check("up/down volume ratio", f"{r:.2f}", r < 1.0, "< 1.0, heavier volume on down days")
a, d, s, _, press_d = weekly_pattern(dis)
ok &= check("distribution weeks of 8", f"{a} acc / {d} dist", d >= 3 and d > a, "several, and more than accumulation")
dd_dis, dd_acc = distribution_days(dis, 60), distribution_days(acc, 60)
ok &= check("distribution days vs the accumulation stock (60d)",
            f"{dd_dis} vs {dd_acc}", dd_dis > dd_acc, "more on the distribution stock")

print("\nChurn (heavy volume, no progress):")
r = up_down_volume_ratio(chu)
ok &= check("up/down volume ratio", f"{r:.2f}", 0.75 <= r <= 1.35, "near 1.0, 'neither buyers nor sellers'")

print("\nPullback on drying volume (institutions taking a break):")
p = pullback_dryness(dry)
ok &= check("down-day volume vs 50d avg", f"{p:.2f}x", p < 1.0, "< 1.0, selling on lighter volume")

print("\nComposite scores must rank the regimes correctly:")
scored = {k: analyze(k, df, k, "Test").score
          for k, df in [("ACCUM", acc), ("DRYPB", dry), ("CHURN", chu), ("DISTR", dis)]}
for k, v in scored.items():
    print(f"    {k}: {v}")
ok &= check("accumulation outranks churn", f"{scored['ACCUM']} > {scored['CHURN']}",
            scored["ACCUM"] > scored["CHURN"], "yes")
ok &= check("churn outranks distribution", f"{scored['CHURN']} > {scored['DISTR']}",
            scored["CHURN"] > scored["DISTR"], "yes")
ok &= check("weekly pressure positive on accumulation, negative on distribution",
            f"{press_a:+.2f} vs {press_d:+.2f}", press_a > 0 > press_d, "opposite signs")

# ---- percentile banding, the A/D gate, and the momentum residual -----------
print("\nPercentile banding and the A/D gate\n" + "-" * 62)


def field(n=100, score=lambda i: i, ad=0.3, ud=1.5, ret=lambda i: 0.0):
    out = []
    for i in range(n):
        m = Metrics(ticker=f"N{i:03d}")
        m.score, m.ad_slope, m.ud_ratio, m.ret_63d = score(i), ad, ud, ret(i)
        out.append(m)
    return out


f = field(100)
classify(f)
bands = {}
for m in f:
    bands.setdefault(m.classification, []).append(m.score)
ok &= check("top 5% get Strong Accumulation", len(bands.get("Strong Accumulation", [])),
            len(bands.get("Strong Accumulation", [])) == 5, "5 of 100")
ok &= check("bottom 15% get Heavy Distribution", len(bands.get("Heavy Distribution", [])),
            len(bands.get("Heavy Distribution", [])) == 15, "15 of 100")
ok &= check("the median name is not labelled Distribution",
            sorted(f, key=lambda m: m.score)[50].classification,
            sorted(f, key=lambda m: m.score)[50].classification == "Neutral / Churn",
            "Neutral / Churn — the old bug put it in Distribution")
ok &= check("percentiles span 0-100",
            f"{min(m.pctile for m in f):.0f}-{max(m.pctile for m in f):.0f}",
            min(m.pctile for m in f) == 0 and max(m.pctile for m in f) == 100, "0-100")

# the gate: a top-percentile name with a falling A/D line cannot be accumulation
g = field(100, ad=-0.11)
classify(g)
top = max(g, key=lambda m: m.score)
ok &= check("negative A/D slope blocks an accumulation label", top.classification,
            top.classification == "Neutral / Churn" and top.gated,
            "downgraded and flagged (FERG and GEF ranked top-20 before this)")
g2 = field(100, ad=0.3, ud=0.8)
classify(g2)
ok &= check("U/D below 1.0 also blocks it", max(g2, key=lambda m: m.score).classification,
            max(g2, key=lambda m: m.score).classification == "Neutral / Churn", "downgraded")
g3 = field(19)
classify(g3)
ok &= check("under 20 names falls back to absolute bands",
            f"pctile={g3[0].pctile}", not np.isfinite(g3[0].pctile),
            "no percentile assigned")

print("\nMomentum residual\n" + "-" * 62)
# scores built to be exactly linear in the 63-day return must leave no residual
lin = field(60, score=lambda i: 20 + 100 * (i / 60) * 0.5, ret=lambda i: i / 60)
for m in lin:
    m.score = 20 + 50 * m.ret_63d
fit = add_momentum_residual(lin)
ok &= check("a score that is pure momentum leaves ~zero residual",
            f"max |ex_mom| = {max(abs(m.ex_mom) for m in lin):.3f}",
            max(abs(m.ex_mom) for m in lin) < 0.05, "~0")
ok &= check("and the fit reports R^2 = 1", f"{fit['r2']:.2f}", fit["r2"] > 0.99, "1.00")

# a name scoring well with a flat price must surface as the biggest residual
mixed = field(60, score=lambda i: 20 + 50 * (i / 60), ret=lambda i: i / 60)
for m in mixed:
    m.score = 20 + 50 * m.ret_63d
odd = mixed[5]
odd.score, odd.ret_63d = 70.0, 0.0        # strong footprint, price has not moved
add_momentum_residual(mixed)
ok &= check("high score on a flat price is the top ex-momentum name",
            f"{odd.ticker} at {odd.ex_mom:+.1f}",
            odd.ex_mom == max(m.ex_mom for m in mixed) and odd.ex_mom > 20,
            "the largest residual in the field")

# a single huge return must not distort everyone else's residual (the MRNA case:
# one name up 207% gave quiet stocks residuals of -73 on a 0-100 scale)
out = field(60, score=lambda i: 20 + 50 * (i / 60), ret=lambda i: i / 60)
for m in out:
    m.score = 20 + 50 * m.ret_63d
out[-1].ret_63d = 2.07                    # the moonshot
add_momentum_residual(out)
worst = min(abs(m.ex_mom) if False else m.ex_mom for m in out[:-1])
ok &= check("one 207% outlier does not blow up the rest of the field",
            f"most negative residual among the others: {worst:+.1f}",
            worst > -25, "> -25 on a 0-100 scale (raw-return regression gave -73)")

# ---- component calibration -------------------------------------------------
print("\nComponent calibration — no component may pay out to nearly everyone\n" + "-" * 62)

# The trend component used to be pass/fail on two moving averages, which gave it
# four distinct values and put 40% of the field at the maximum.
trend_inputs = [(p50, p200, off)
                for p50 in np.linspace(-0.15, 0.15, 12)
                for p200 in np.linspace(-0.20, 0.30, 12)
                for off in np.linspace(-0.45, -0.01, 12)]
trend_vals = [round(_lin(a, *VS_50DMA_BOUNDS, 4) + _lin(b, *VS_200DMA_BOUNDS, 3)
                    + _lin(c, *OFF_HIGH_BOUNDS, 3), 2) for a, b, c in trend_inputs]
tv = pd.Series(trend_vals)
ok &= check("trend component takes many distinct values", tv.nunique(),
            tv.nunique() > 200, "hundreds, not the old four")
ok &= check("trend component does not max out for most inputs",
            f"{100 * (tv > 9.99).mean():.0f}% at the ceiling",
            (tv > 9.99).mean() < 0.10, "under 10% (was 40% of the live field)")

pull_vals = pd.Series([round(_lin(v, *PULLBACK_BOUNDS, 10), 2)
                       for v in np.linspace(0.55, 1.30, 400)])
ok &= check("pullback component does not max out for most inputs",
            f"{100 * (pull_vals > 9.99).mean():.0f}% at the ceiling",
            (pull_vals > 9.99).mean() < 0.25, "under 25% (was 34% of the live field)")
ok &= check("pullback still rewards drier volume monotonically",
            "decreasing in dryness",
            all(pull_vals.iloc[i] >= pull_vals.iloc[i + 1] for i in range(len(pull_vals) - 1)),
            "monotone")

# ---- sector-neutral ranking ------------------------------------------------
print("\nSector-neutral ranking and concentration\n" + "-" * 62)

sec = []
for i in range(40):                      # Energy sweeps the top of the field
    m = Metrics(ticker=f"E{i:02d}", sector="Energy")
    m.score, m.ad_slope, m.ud_ratio, m.ret_63d = 60 + i * 0.5, 0.3, 1.5, 0.1
    sec.append(m)
for i in range(60):                      # everything else scores lower
    m = Metrics(ticker=f"H{i:02d}", sector="Health Care")
    m.score, m.ad_slope, m.ud_ratio, m.ret_63d = 20 + i * 0.4, 0.3, 1.5, 0.1
    sec.append(m)
for i in range(4):                       # too small to rank within
    m = Metrics(ticker=f"U{i}", sector="Utilities")
    m.score = 50.0
    sec.append(m)

info = add_sector_ranks(sec, top_n=50)
energy = [m for m in sec if m.sector == "Energy"]
health = [m for m in sec if m.sector == "Health Care"]
ok &= check("every sector's own best name reaches the 100th percentile",
            f"Energy {max(m.sector_pctile for m in energy):.0f}, "
            f"Health Care {max(m.sector_pctile for m in health):.0f}",
            max(m.sector_pctile for m in energy) == 100
            and max(m.sector_pctile for m in health) == 100,
            "100 in both — that is the point of ranking within sector")
worst_energy = min(energy, key=lambda m: m.score)
best_health = max(health, key=lambda m: m.score)
ok &= check("a sector laggard outranks another sector's leader on raw score, "
            "but not on sector percentile",
            f"scores {worst_energy.score:.0f} vs {best_health.score:.0f}; "
            f"sector %iles {worst_energy.sector_pctile:.0f} vs {best_health.sector_pctile:.0f}",
            worst_energy.score > best_health.score
            and worst_energy.sector_pctile < best_health.sector_pctile,
            "the sector-neutral view flips them")
ok &= check("sectors below the minimum size get no percentile",
            [m.sector_pctile for m in sec if m.sector == "Utilities"][0],
            not np.isfinite([m.sector_pctile for m in sec if m.sector == "Utilities"][0]),
            "nan — four names cannot support a percentile")
conc = info["concentration"]
ok &= check("the Energy sweep is flagged as concentration",
            f"{conc[0]['sector']} {conc[0]['got']} vs {conc[0]['expected']} expected"
            if conc else "nothing flagged",
            bool(conc) and conc[0]["sector"] == "Energy" and conc[0]["got"] == 40,
            "Energy, 40 of the top 50 against 19.2 expected")
ok &= check("sector_delta is measured against the sector median",
            f"{max(energy, key=lambda m: m.score).sector_delta:+.1f}",
            abs(max(energy, key=lambda m: m.score).sector_delta
                - (79.5 - float(np.median([m.score for m in energy])))) < 0.11,
            "top Energy score minus the Energy median")

# ---- the article's own scoring -------------------------------------------
print("\nThe article-only score\n" + "-" * 62)

def am(ud=1.0, streak=0, acc=0, dist=0, pull=1.05, vs50=0.0, off=-0.20,
       ret=0.0, dd=6):
    m = Metrics(ticker="X")
    m.ud_ratio, m.acc_streak, m.acc_weeks, m.dist_weeks = ud, streak, acc, dist
    m.pullback_dryness, m.pct_vs_50dma, m.pct_off_high = pull, vs50, off
    m.ret_63d, m.dist_days = ret, dd
    return m

floor_case = am()
ok &= check("a churning name at U/D 1.0 scores near zero", f"{article_score(floor_case):.1f}",
            article_score(floor_case) < 5, "under 5 — the article calls 1.0 churn")

perfect = am(ud=2.4, streak=4, acc=5, dist=0, pull=0.70, vs50=0.15, off=-0.01,
             ret=0.40, dd=0)
ok &= check("a textbook Sandisk-shaped name scores near the top",
            f"{article_score(perfect):.1f}", article_score(perfect) > 95, "> 95")
ok &= check("the score is clamped to 100", f"{article_score(perfect):.1f}",
            article_score(perfect) == 100.0, "exactly 100, not 112")

# the article's headline gauge must dominate: 2.0 vs 1.0 is worth 30 points
lo, hi = am(ud=1.0), am(ud=2.0)
ok &= check("U/D 1.0 -> 2.0 is worth the full 30 points",
            f"{article_score(hi) - article_score(lo):.1f}",
            abs((article_score(hi) - article_score(lo)) - 30) < 0.2, "30")

# consecutive weeks must beat the same number of scattered weeks
run, scattered = am(ud=1.5, streak=3, acc=3), am(ud=1.5, streak=1, acc=3)
ok &= check("consecutive weeks beat the same count scattered",
            f"{article_score(run):.1f} vs {article_score(scattered):.1f}",
            article_score(run) > article_score(scattered) + 8,
            "clearly higher — 'repeated for several consecutive weeks'")

# and the article rewards a stock that has ALREADY run - unlike ex-momentum
ran, fallen = am(ud=1.8, streak=2, acc=2, ret=0.35, off=-0.03, vs50=0.12), \
              am(ud=1.8, streak=2, acc=2, ret=-0.05, off=-0.44, vs50=0.12)
ok &= check("the article prefers a name that has already run",
            f"{article_score(ran):.1f} vs {article_score(fallen):.1f}",
            article_score(ran) > article_score(fallen) + 8,
            "higher — its example was up 500% and still accumulating")

ok &= check("article score stays within 0-100 across extremes",
            f"{article_score(floor_case):.0f}-{article_score(perfect):.0f}",
            0 <= article_score(floor_case) and article_score(perfect) <= 100, "0-100")

# ---- sub-industry ranking -------------------------------------------------
print("\nSub-industry clustering\n" + "-" * 62)
ok &= check("wide universe adds the S&P 600", UNIVERSE_SETS["wide"],
            "sp600" in UNIVERSE_SETS["wide"] and "sp600" not in UNIVERSE_SETS["broad"],
            "sp600 in wide, not in broad")

sub = []
for i in range(6):                      # a refiner cluster sweeping the top
    m = Metrics(ticker=f"R{i}", sector="Energy", sub_industry="Oil & Gas Refining")
    m.score, m.ad_slope, m.ud_ratio, m.ret_63d = 90 - i, 0.3, 1.5, 0.1
    sub.append(m)
for i in range(30):
    m = Metrics(ticker=f"O{i:02d}", sector="Energy", sub_industry="Oil & Gas E&P")
    m.score, m.ad_slope, m.ud_ratio, m.ret_63d = 40 + i * 0.5, 0.3, 1.5, 0.1
    sub.append(m)
for i in range(30):
    m = Metrics(ticker=f"S{i:02d}", sector="Information Technology",
                sub_industry="Application Software")
    m.score, m.ad_slope, m.ud_ratio, m.ret_63d = 30 + i * 0.6, 0.3, 1.5, 0.1
    sub.append(m)
info2 = add_sector_ranks(sub, top_n=10)
refiners = [m for m in sub if m.sub_industry == "Oil & Gas Refining"]
ok &= check("names get a sub-industry percentile",
            f"{max(m.sub_pctile for m in refiners):.0f}",
            max(m.sub_pctile for m in refiners) == 100, "100 for the best refiner")
sc = info2.get("sub_concentration", [])
ok &= check("the refiner cluster is flagged separately from the sector",
            f"{sc[0]['sub_industry']} x{sc[0]['got']}" if sc else "nothing flagged",
            bool(sc) and sc[0]["sub_industry"] == "Oil & Gas Refining"
            and sc[0]["got"] == 6,
            "Oil & Gas Refining, 6 of the top 10")
ok &= check("sector-level view alone would have called this just 'Energy'",
            [c["sector"] for c in info2["concentration"]],
            any(c["sector"] == "Energy" for c in info2["concentration"]),
            "Energy flagged, which is why sub-industry matters")

# ---- sample report -------------------------------------------------------
from dataclasses import asdict
names = {"ACCUM": "Synthetic Accumulation Co", "DRYPB": "Synthetic Dry-Pullback Co",
         "CHURN": "Synthetic Churn Co", "DISTR": "Synthetic Distribution Co"}
frames = {"ACCUM": acc, "DRYPB": dry, "CHURN": chu, "DISTR": dis}
metrics = [analyze(t, df, names[t], "Information Technology")
           for t, df in frames.items()]
classify(metrics)
add_momentum_residual(metrics)
rows = [asdict(m) for m in metrics]
rows.sort(key=lambda r: r["score"], reverse=True)
for i, r in enumerate(rows, 1):
    r["rank"] = i

write_report({
    "generated": "sample output — synthetic data, not a live scan",
    "universe": "SAMPLE", "count": len(rows), "scanned": len(rows),
    "params": {"ud_window": 50, "week_lookback": 8, "dist_day_window": 25,
               "min_price": 0, "min_dollar_vol": 0},
    "health": [
        {"label": "S&P 500", "count": 2, "state": "good",
         "note": "Institutions are not exiting.", "last": 0, "chg": 0},
        {"label": "Nasdaq Composite", "count": 5, "state": "critical",
         "note": "Heavy selling. Be defensive.", "last": 0, "chg": 0},
    ],
    "rows": rows,
}, "sample_report.html")
print("\nWrote sample_report.html")

print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
sys.exit(0 if ok else 1)
