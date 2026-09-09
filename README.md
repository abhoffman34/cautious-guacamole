# Institutional Accumulation Screener

A stock screener built from the strategy in *"Institutional Investors Move Markets.
Here's How to Read Their Signs."* (WSJ / IBD Insights, Sept. 7 2026).

The premise: institutions are too big to hide. Their buying and selling leaves a
signature in a stock's **trading range** and **volume**. The screener measures that
signature across a universe of stocks, scores each name 0–100, and writes an
interactive HTML report you open in a browser.

## Easiest way to run it: Google Colab (no install)

Use `Institutional_Accumulation_Screener.ipynb`. Nothing to install, no terminal,
no Python on your machine.

1. Go to **[colab.research.google.com](https://colab.research.google.com)** and sign
   in with any Google account.
2. **File → Upload notebook**, and pick `Institutional_Accumulation_Screener.ipynb`.
3. **Runtime → Run all** (Ctrl+F9). Click **Run anyway** if it warns about the
   notebook's author.
4. Wait 5–10 minutes. The report appears at the bottom of the notebook and
   downloads to your computer as `institutional_screener.html`.

Set `limit` to `50` in the settings cell for a one-minute test run first.

The notebook is generated from the files below by `build_notebook.py`, so it runs
exactly the code the test suite covers. If you change the engine, re-run that script
to refresh the notebook.

## Running it locally instead

```
pip install yfinance pandas numpy lxml requests
```

Python 3.10+.

```
python institutional_screener.py
```

That scans S&P 500 + S&P 400 + Nasdaq-100 (~1,000 names, roughly 5–10 minutes,
almost all of it downloading). It writes into `./output/`:

| file | what it is |
| --- | --- |
| `institutional_screener.html` | **open this** — the interactive report |
| `screen_results.csv` | every name and metric, for Excel |
| `screen_results.json` | same, structured |

Useful flags:

```
--universe broad|wide|sp500|sp400|sp600|ndx
                                   broad = S&P 500+400+NDX (~1,000, default)
                                   wide  = adds S&P 600 small caps (~1,600)
--tickers-file watchlist.txt       your own list, one ticker per line
--min-price 10                     drop anything cheaper
--min-dollar-vol 10e6              drop anything thinner than $10M/day
--limit 50                         quick test on the first 50 names
--outdir results/                  where to write
```

## What it measures

Six components, 100 points. Every threshold is a constant at the top of
`institutional_screener.py` — change them there.

| Component | Points | What the article says |
| --- | --- | --- |
| Up/down volume ratio, 50 days | 30 | Up-day volume ÷ down-day volume. "2.0 means twice as much up volume… a ratio below 1.0 points to heavier volume on down days." |
| Weekly range + volume | 25 | Each of the last eight weeks contributes where it closed in its own range, weighted by its volume (**weekly pressure**, −2 to +2). Consecutive threshold-clearing weeks score a bonus — "this pattern was repeated for several consecutive weeks." |
| A/D line slope, 25 days | 20 | The Accumulation/Distribution line, normalized by average volume so different-sized stocks compare. |
| Pullback volume drying | 10 | "The stock pulled back… but that was accompanied by lower volume, indicating that institutions were taking a break from buying, and not necessarily selling." Bounds sit at the field's p10/p90 so the median name lands mid-scale. |
| Volume expansion | 5 | 50-day vs 200-day average volume. No footprints, no institutions. |
| Trend / support | 10 | How far price sits above its 50- and 200-day averages and below its 52-week high — continuous, not pass/fail. As two binary tests it had only **four distinct values** and put 358 of 899 names in one tie block. |

**Distribution days** are counted separately, for the indexes and for each stock:
sessions closing lower on higher volume than the day before. Indexes use the article's
literal 0.2%; individual stocks use the same rule expressed in their own volatility
(0.22 σ, which reproduces 0.2% at index-like volatility). A flat 0.2% threshold applied
to single stocks — three to five times as volatile — counts noise as evidence, and put
the median stock at five distribution days in the first live run. That gauge sits at
the top of the report; read it before the rankings, because a good-looking accumulation
name in a market under distribution is a different proposition.

**Churn** — heavy volume, no price progress, up/down ratio pinned near 1.0 — is flagged
on its own rather than scored as a positive.

## Four things that make the ranking honest

These exist because the first live run of 899 names exposed three ways the raw
composite misleads.

**Bands are percentiles of the scan, not absolute scores.** "Strong Accumulation" is the
top 5% of what was screened, Accumulation the next 15%, then 40% Neutral, 25%
Distribution, 15% Heavy Distribution. Absolute cutoffs sound more objective and behave
worse: the first version labelled the median stock "Distribution" in a market where two
thirds of names sat above their 200-day average. Below 20 names the code falls back to
absolute bands, since a percentile of twelve stocks means nothing.

**The A/D gate.** A name cannot carry an accumulation label while its
Accumulation/Distribution line is falling, or with up/down volume below 1.0. In the
first run, seven of the top twenty had a flat or negative A/D slope — the other five
components had outvoted the one that most directly answers the question. Gated names
are downgraded to Neutral and marked with a dot.

**Sector-neutral ranking.** A single ranking of the whole market hands you whichever
sector the macro currently favours: in the live run eight of the top fifty were Energy
against 2.1 expected, four of them refiners inside the top fourteen — one bet on crack
spreads wearing four tickers. The `sector_pctile` column ranks each name inside its own
sector (needs 8+ names in that sector), the report flags over-represented sectors above
the table, and **Best N per sector** caps the list. The cap applies after sorting, so it
works on the ex-momentum ordering too.

**Ex-momentum — the column to read second.** The composite correlates ~0.7 with the
trailing 63-day return, partly by construction: a stock that rose necessarily had more
up days, and up days carry volume. Ex-momentum is the score with the return regressed
out, so a positive figure means more institutional footprint than the stock's own price
action predicts. Sorting by score finds what has already worked; sorting by ex-momentum
finds what may not be in the price yet. The regression runs on the *rank* of the return
rather than the raw figure — one name up 207% dragged the least-squares line far enough
to hand quiet stocks residuals of −73 on a scale that only spans 100.

## The Article column — a second, independent ranking

`art_score` scores each name using **only** the tests the article itself names: the
up/down volume ratio, consecutive heavy-volume closes high in the weekly range,
pullbacks on lighter volume, a holding support floor, and few distribution days. It
contains none of this tool's own additions — no A/D component, no momentum residual,
no sector neutrality.

It also rewards a stock that has **already run**, because the article's worked example
was up 500% on the year and still being accumulated. That makes it a
momentum-continuation framework, and scoring it faithfully means saying so — the
composite's ex-momentum column pulls in the opposite direction by design.

The two rankings correlate about +0.9. The disagreements are where the information is:
a high Article score with a low composite usually means an A/D line that is not
confirming; the reverse usually means a beaten-down name the article would never have
picked.

## Sub-industry clustering

Sector was too coarse. Four oil refiners are one bet on crack spreads, but GICS files
them under "Energy" alongside pipelines and drillers. The Wikipedia index tables carry
**GICS Sub-Industry**, so the screener now pulls it and uses it for `sub_pctile`, a
cluster warning above the table, and a **Best N per sub-industry** cap.

## Reading the report

- **Market health tiles** — distribution-day counts for the S&P 500 and Nasdaq.
- **Table** — sortable on any column, filterable by signal band, sector, and search.
  The 8-week strip shows each of the last eight weeks as **A** (accumulation),
  **D** (distribution), or blank.
- **Click any row** — the component breakdown, so you can see *which* part of the
  score is carrying it, plus where the stock closed in its weekly range each week.

A score is a starting point for a chart, not a signal to trade. Two names at 72 can
get there very differently — one on volume, one on trend — which is why the breakdown
is one click away.

## Tests

```
python test_metrics.py    # deterministic unit tests + synthetic-regime behaviour
python smoke_test.py      # end-to-end: universe → score → filter → CSV/JSON/HTML
python test_notebook.py   # executes the notebook's own cells with the network stubbed
python make_sample.py     # writes sample_report.html from synthetic data
```

`test_metrics.py` checks each metric against hand-built bars with known answers (a
5-day window with exactly two qualifying distribution days, a series closing at its
high every day, and so on), then confirms the composite score ranks four synthetic
regimes — accumulation, dry pullback, churn, distribution — in the right order.

## Limits worth knowing

- Yahoo Finance data is free and occasionally wrong. Spot-check anything surprising.
- Index membership comes from Wikipedia at runtime; if that fetch fails the script
  falls back to a bundled large-cap list, which will be stale.
- Volume is a noisy proxy for institutional activity. The article says so itself:
  ETFs and high-frequency traders move a lot of volume without taking a position.
  The range-position and consecutive-week components exist to filter that noise, but
  they do not eliminate it.
- Everything here is descriptive. It tells you what price and volume have already
  done. Educational tool, not investment advice.
