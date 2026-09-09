#!/usr/bin/env python3
"""Writes a compact week-over-week digest from two screener runs.

Deliberately small (a few KB). It is fetched whole over the network by the
weekly assessment task, so it has to survive being read in one piece - which
rules out pasting 900 rows in.
"""

from __future__ import annotations

import glob
import os
import sys
from datetime import datetime, timezone

import pandas as pd

ACC_BANDS = ("Strong Accumulation", "Accumulation")
HIST = "history"
LATEST = "latest"


def _load(path):
    df = pd.read_csv(path)
    return df.set_index("ticker", drop=False)


def _fmt(rows, cols, n=10):
    if len(rows) == 0:
        return "_none_\n"
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in rows.head(n).iterrows():
        vals = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, float):
                v = f"{v:+.1f}" if c.startswith(("d_", "ex_mom")) else f"{v:.2f}"
            # a pipe inside a company name would split the markdown table
            vals.append(str(v).replace("|", "/"))
        out += "| " + " | ".join(vals) + " |\n"
    return out


def build(cur_path: str, prev_path: str | None, out_path: str) -> str:
    cur = _load(cur_path)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# Weekly institutional accumulation scan",
         f"", f"- run: {stamp}",
         f"- names scanned: {len(cur)}",
         f"- previous run: {os.path.basename(prev_path) if prev_path else 'none (first run)'}",
         ""]

    # --- band counts -------------------------------------------------------
    counts = cur.classification.value_counts()
    prev = _load(prev_path) if prev_path else None
    pcounts = prev.classification.value_counts() if prev is not None else None
    L.append("## Bands")
    L.append("")
    L.append("| band | now | change |")
    L.append("|---|---|---|")
    for b in ["Strong Accumulation", "Accumulation", "Neutral / Churn",
              "Distribution", "Heavy Distribution"]:
        n = int(counts.get(b, 0))
        if pcounts is not None:
            d = n - int(pcounts.get(b, 0))
            L.append(f"| {b} | {n} | {d:+d} |")
        else:
            L.append(f"| {b} | {n} | — |")
    L.append("")

    if "gated" in cur.columns:
        L.append(f"Gated by the A/D rule: {int(cur.gated.sum())}. "
                 f"Median distribution days: {cur.dist_days.median():.0f}.")
        L.append("")

    # --- movers ------------------------------------------------------------
    if prev is not None:
        both = cur.index.intersection(prev.index)
        c, p = cur.loc[both], prev.loc[both]
        chg = pd.DataFrame({
            "ticker": c["ticker"], "name": c["name"].str.slice(0, 26),
            "score": c.score, "d_score": c.score - p.score,
            "ex_mom": c.get("ex_mom", pd.Series(index=c.index, dtype=float)),
            "class": c.classification,
        })

        newly = cur[cur.classification.isin(ACC_BANDS)
                    & ~cur.index.isin(prev[prev.classification.isin(ACC_BANDS)].index)]
        left = prev[prev.classification.isin(ACC_BANDS)
                    & ~prev.index.isin(cur[cur.classification.isin(ACC_BANDS)].index)]

        L.append(f"## Entered the accumulation bands ({len(newly)})")
        L.append("")
        L.append(_fmt(newly.sort_values("score", ascending=False),
                      ["ticker", "name", "score", "ud_ratio", "acc_streak",
                       "ad_slope", "dist_days"], 12))
        L.append(f"## Dropped out of the accumulation bands ({len(left)})")
        L.append("")
        L.append(_fmt(left.sort_values("score", ascending=False),
                      ["ticker", "name", "score"], 12))

        L.append("## Biggest score gains")
        L.append("")
        L.append(_fmt(chg.sort_values("d_score", ascending=False),
                      ["ticker", "name", "score", "d_score", "class"], 8))
        L.append("## Biggest score falls")
        L.append("")
        L.append(_fmt(chg.sort_values("d_score"),
                      ["ticker", "name", "score", "d_score", "class"], 8))

        gone = sorted(set(prev.index) - set(cur.index))
        added = sorted(set(cur.index) - set(prev.index))
        if gone or added:
            L.append("## Universe changes")
            L.append("")
            L.append(f"- left the scan: {', '.join(gone[:20]) or 'none'}")
            L.append(f"- new to the scan: {', '.join(added[:20]) or 'none'}")
            L.append("")

    # --- current leaders ---------------------------------------------------
    L.append("## Top 10 by composite score")
    L.append("")
    L.append(_fmt(cur.sort_values("score", ascending=False),
                  ["ticker", "name", "score", "ex_mom", "ud_ratio", "acc_streak",
                   "ad_slope", "dist_days"], 10))

    if "art_score" in cur.columns:
        L.append("## Top 10 on the article's own criteria")
        L.append("")
        L.append(_fmt(cur.sort_values("art_score", ascending=False),
                      ["ticker", "name", "art_score", "score", "ud_ratio",
                       "acc_streak"], 10))

    if "ex_mom" in cur.columns:
        clean = cur[(~cur.get("gated", False)) & (cur.ad_slope > 0)
                    & (cur.ud_ratio > 1.0)]
        L.append("## Top 10 ex-momentum, gate-clean")
        L.append("")
        L.append(_fmt(clean.sort_values("ex_mom", ascending=False),
                      ["ticker", "name", "ex_mom", "score", "ud_ratio",
                       "acc_streak", "pct_off_high"], 10))

    # --- concentration -----------------------------------------------------
    top50 = cur.sort_values("score", ascending=False).head(50)
    if "sub_industry" in cur.columns:
        cl = top50.sub_industry.value_counts()
        cl = cl[(cl >= 3) & (cl.index != "Unknown")]
        if len(cl):
            L.append("## Clusters in the top 50")
            L.append("")
            for sub, k in cl.items():
                names = ", ".join(top50[top50.sub_industry == sub].ticker[:6])
                L.append(f"- **{sub}** ({k}): {names}")
            L.append("")
    sec = top50.sector.value_counts()
    L.append("Top-50 sector mix: "
             + ", ".join(f"{s} {k}" for s, k in sec.head(5).items()) + ".")
    L.append("")

    text = "\n".join(L)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def main() -> int:
    os.makedirs(HIST, exist_ok=True)
    os.makedirs(LATEST, exist_ok=True)
    cur = "output/screen_results.csv"
    if not os.path.exists(cur):
        print("no fresh results to digest")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # never diff against a file written earlier the same day (a re-run), or the
    # digest would compare this scan with itself and report no change at all
    prior = [f for f in sorted(glob.glob(f"{HIST}/*_results.csv"))
             if os.path.basename(f)[:10] != stamp]
    prev = prior[-1] if prior else None

    text = build(cur, prev, f"{LATEST}/weekly_digest.md")
    pd.read_csv(cur).to_csv(f"{HIST}/{stamp}_results.csv", index=False)
    pd.read_csv(cur).to_csv(f"{LATEST}/screen_results.csv", index=False)

    # keep the history from growing without bound
    keep = sorted(glob.glob(f"{HIST}/*_results.csv"))[-26:]
    for f in sorted(glob.glob(f"{HIST}/*_results.csv")):
        if f not in keep:
            os.remove(f)

    print(text[:1500])
    print(f"\n[digest {len(text)} bytes -> {LATEST}/weekly_digest.md]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
