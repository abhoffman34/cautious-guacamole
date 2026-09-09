"""End-to-end smoke test of main(): stubs the network layer with synthetic
histories so the universe -> score -> filter -> CSV/JSON/HTML path is exercised
without a live data pull."""

import sys, json, os
import pandas as pd
sys.path.insert(0, ".")

import institutional_screener as S
from synthetic import make

TICKERS = ["ACCUM", "DRYPB", "CHURN", "DISTR", "PENNY", "THIN"]
REGIME = {"ACCUM": "accum", "DRYPB": "dry_pullback", "CHURN": "churn",
          "DISTR": "dist", "PENNY": "accum", "THIN": "accum"}


def fake_download(tickers, period="2y", batch=100, pause=1.0):
    out = {}
    for t in tickers:
        df = make(REGIME[t], base_vol=200 if t == "THIN" else 4_000_000,
                  start=2.0 if t == "PENNY" else 100.0)
        out[t] = df
    return out


def fake_health():
    return [{"label": "S&P 500", "count": 1, "state": "good",
             "note": "Institutions are not exiting.", "last": 6000.0, "chg": 0.003}]


S.download_prices = fake_download
S.market_health = fake_health

with open("_smoke_tickers.txt", "w") as fh:
    fh.write("\n".join(TICKERS))

sys.argv = ["x", "--tickers-file", "_smoke_tickers.txt", "--outdir", "smoke_out",
            "--min-price", "7", "--min-dollar-vol", "5e6"]
rc = S.main()

payload = json.load(open("smoke_out/screen_results.json"))
names = [r["ticker"] for r in payload["rows"]]
csv = pd.read_csv("smoke_out/screen_results.csv")
html = open("smoke_out/institutional_screener.html").read()

print("\n" + "-" * 62)
checks = [
    ("main() returned 0", rc == 0),
    ("PENNY filtered out by --min-price", "PENNY" not in names),
    ("THIN filtered out by --min-dollar-vol", "THIN" not in names),
    ("four names survive", len(names) == 4),
    ("ranked best-first", names[0] == "ACCUM" and names[-1] == "DISTR"),
    ("ranks are 1..n", [r["rank"] for r in payload["rows"]] == [1, 2, 3, 4]),
    ("CSV has one row per name", len(csv) == 4),
    ("CSV carries the score column", "score" in csv.columns),
    ("HTML is self-contained (no external src/href)",
     "src=\"http" not in html and "href=\"http" not in html),
    ("HTML embeds the payload", "\"ACCUM\"" in html),
    ("week_pattern survives into the payload",
     len(payload["rows"][0]["week_pattern"]) == 8),
    ("components survive into the payload",
     len(payload["rows"][0]["components"]) == 6),
    ("sector ranks are in the payload", "sectors" in payload),
    ("rows carry a sector percentile column", "sector_pctile" in payload["rows"][0]),
    ("CSV carries the sector percentile", "sector_pctile" in csv.columns),
    ("CSV carries ex-momentum", "ex_mom" in csv.columns),
]
bad = [n for n, c in checks if not c]
for n, c in checks:
    print(f"  [{'PASS' if c else 'FAIL'}] {n}")
os.remove("_smoke_tickers.txt")
print("\n" + ("SMOKE TEST PASSED" if not bad else f"FAILED: {bad}"))
sys.exit(0 if not bad else 1)
