"""Builds a fuller sample report (synthetic data) so the page layout can be
previewed without a live data pull."""

import random
from dataclasses import asdict

from institutional_screener import (analyze, classify, add_momentum_residual,
                                    add_sector_ranks)
from report import write_report
from synthetic import make

random.seed(11)
SECTORS = ["Information Technology", "Health Care", "Industrials", "Financials",
           "Consumer Discretionary", "Energy", "Materials", "Communication Services"]
SUBS = {"Energy": ["Oil & Gas Refining", "Oil & Gas E&P"],
        "Information Technology": ["Application Software", "Semiconductors"],
        "Health Care": ["Life Sciences Tools", "Pharmaceuticals"]}
REGIMES = ["accum"] * 9 + ["dry_pullback"] * 7 + ["churn"] * 8 + ["dist"] * 12

metrics = []
for i, reg in enumerate(REGIMES, 1):
    df = make(reg, base_vol=random.uniform(1.5e6, 9e6),
              start=random.uniform(25, 400))
    # deliberately cluster the accumulating names in one sector so the sample
    # demonstrates the concentration warning
    sector = "Energy" if reg == "accum" and i % 3 != 0 else random.choice(SECTORS)
    sub = random.choice(SUBS.get(sector, [sector + " Products"]))
    m = analyze(f"SYN{i:02d}", df, f"Synthetic Holdings {i:02d} (sample data)",
                sector, sub)
    if m:
        metrics.append(m)

classify(metrics)
fit = add_momentum_residual(metrics)
sectors = add_sector_ranks(metrics, top_n=12)
rows = [asdict(m) for m in metrics]
rows.sort(key=lambda r: r["score"], reverse=True)
for i, r in enumerate(rows, 1):
    r["rank"] = i

write_report({
    "generated": "SAMPLE — synthetic data, not a live scan",
    "universe": "SAMPLE", "count": len(rows), "scanned": len(rows),
    "params": {"ud_window": 50, "week_lookback": 8, "dist_day_window": 25,
               "dist_day_sigma": 0.22, "min_price": 0, "min_dollar_vol": 0},
    "fit": fit,
    "gated": sum(1 for m in metrics if m.gated),
    "sectors": sectors,
    "health": [
        {"label": "S&P 500", "count": 2, "state": "good",
         "note": "Institutions are not exiting.", "last": 0, "chg": 0},
        {"label": "Nasdaq Composite", "count": 5, "state": "critical",
         "note": "Heavy selling. Be defensive.", "last": 0, "chg": 0},
    ],
    "rows": rows,
}, "sample_report.html")
print(f"sample_report.html — {len(rows)} synthetic names")
