"""Assembles the Colab notebook from the tested source files, so the notebook
runs exactly the code that passed the test suite - no forked copy to drift."""

import json
import re

def code(src, hidden=False, form=False):
    meta = {}
    if hidden:
        meta["jupyter"] = {"source_hidden": True}
    if form:
        meta["cellView"] = "form"
    return {"cell_type": "code", "execution_count": None, "metadata": meta,
            "outputs": [], "source": src.splitlines(keepends=True)}

def md(src):
    return {"cell_type": "markdown", "metadata": {},
            "source": src.splitlines(keepends=True)}


report = open("report.py").read()
engine = open("institutional_screener.py").read()

# The notebook defines the engine in the notebook's own namespace, so the
# script's __main__ guard must not fire (Colab's __name__ is "__main__" too).
engine = engine.split('if __name__ == "__main__":')[0].rstrip() + "\n"
assert "argparse.ArgumentParser" in engine, "main() should still be defined"
assert "def run_screen" in engine

INTRO = """# Institutional Accumulation Screener

Finds stocks that institutions appear to be **accumulating** — or **distributing** —
using the price-range and volume signature described in *"Institutional Investors
Move Markets. Here's How to Read Their Signs."* (WSJ / IBD Insights, Sept. 7 2026).

---

### How to run this

1. **Runtime → Run all** (top menu), or press **Ctrl+F9** / **⌘+F9**.
2. If Colab warns the notebook wasn't authored by Google, click **Run anyway**.
3. Wait 5–10 minutes. Almost all of that is downloading price history.
4. The finished report appears at the bottom **and downloads to your computer** as
   `institutional_screener.html` — double-click it to open in any browser.

Nothing to install, no terminal, no Python on your machine. To narrow the scan,
change the settings in step 4 and re-run steps 4 and 5.

**Want a fast test first?** In step 4 set `limit` to `50`. That scans 50 names in
about a minute so you can see the whole thing work before committing to the full run.
"""

INSTALL = '''#@title Step 1 — install the data library  *(~20 seconds)* { display-mode: "form" }
!pip install -q yfinance
import yfinance, pandas, numpy
print(f"Ready. yfinance {yfinance.__version__}, pandas {pandas.__version__}")
'''

SETTINGS = '''#@title Step 4 — settings  *(the defaults are fine — skip this)* { display-mode: "form" }

#@markdown **Universe.** `broad` = S&P 500 + 400 + Nasdaq-100 (~1,000 names, 5-10 min).
#@markdown `wide` adds S&P 600 small caps (~1,600 names, 10-20 min) — where
#@markdown institutional footprints are easiest to see, because one fund buying
#@markdown actually moves the volume.
universe = "broad" #@param ["broad", "wide", "sp500", "sp400", "sp600", "ndx"]

#@markdown **Minimum share price** — drops anything cheaper.
min_price = 7 #@param {type:"number"}

#@markdown **Minimum average daily dollar volume, in millions** — drops thin names.
min_dollar_volume_millions = 5 #@param {type:"number"}

#@markdown **Cap the number of names** (0 = no cap). Set to 50 for a quick test run.
limit = 0 #@param {type:"integer"}

SETTINGS = dict(universe=universe,
                min_price=float(min_price),
                min_dollar_vol=float(min_dollar_volume_millions) * 1e6,
                limit=int(limit) or None,
                outdir="output")
print("Settings:", SETTINGS)
'''

RUN = '''#@title Step 5 — run the screen, preview it, and download it { display-mode: "form" }

import os, html as _html
import pandas as pd
from IPython.display import display, HTML

payload = run_screen(**SETTINGS)

path = "output/institutional_screener.html"

# --- the top of the ranking, inline ---
df = pd.read_csv("output/screen_results.csv")
cols = ["rank", "ticker", "name", "score", "art_score", "ex_mom", "classification",
        "ud_ratio", "acc_streak", "dist_days", "price"]
display(HTML("<h3>Top 20 by institutional accumulation score</h3>"))
display(df[[c for c in cols if c in df.columns]].head(20)
          .style.hide(axis="index")
          .format({"score": "{:.0f}", "art_score": "{:.0f}", "ex_mom": "{:+.1f}",
                   "ud_ratio": "{:.2f}", "price": "${:.2f}"}))

# --- the full interactive report, previewed in place ---
doc = open(path, encoding="utf-8").read()
display(HTML("<h3>Full report</h3>"))
display(HTML(f'<iframe srcdoc="{_html.escape(doc, quote=True)}" '
             f'style="width:100%;height:820px;border:1px solid #ddd;'
             f'border-radius:10px;background:#fff"></iframe>'))

# --- ...and downloaded to your computer ---
try:
    from google.colab import files
    files.download(path)
    files.download("output/screen_results.csv")
    print("\\nDownloading institutional_screener.html and screen_results.csv.")
    print("If the browser blocked it: folder icon in the left sidebar -> "
          "output -> right-click the file -> Download.")
except ImportError:
    print(f"\\nNot in Colab. Report is at {os.path.abspath(path)}")
'''

NOTE = """---

### What the score means

Six components, 100 points total:

| Component | Points | The idea |
| --- | --- | --- |
| Up/down volume ratio, 50 days | 30 | Up-day volume ÷ down-day volume. Above 2.0 is strong accumulation, 1.0 is churn, below 1.0 means heavier selling. |
| Weekly range + volume | 25 | Weeks closing in the top 35% of their range on heavy volume, with a bonus when they repeat consecutively — the repetition is the signal, not any one week. |
| A/D line slope, 25 days | 20 | The classic Accumulation/Distribution line, normalized by volume so different-sized stocks compare. |
| Pullback volume drying | 10 | Pulling back on *lighter* volume means institutions paused buying — not that they sold. |
| Volume expansion | 5 | 50-day vs 200-day average volume. No footprints, no institutions. |
| Trend / support | 10 | Price above its 50- and 200-day averages and near its 52-week high. |

**Distribution days** — sessions closing 0.2% or more lower on higher volume — are
counted for the S&P 500 and Nasdaq and shown at the top of the report. Read that
gauge first: a high-scoring stock in a market under distribution is a different
proposition than the same stock in a calm one.

In the report, **click any row** to see which components are carrying its score.
Two names at 72 can get there very differently.

### If something goes wrong

- **"No price data came back"** — Yahoo rate-limited the session. Wait a minute and
  re-run step 5, or set `limit` to a smaller number in step 4.
- **The download didn't happen** — click the folder icon in the left sidebar, open
  `output`, right-click `institutional_screener.html` → Download.
- **A name you expected is missing** — it was filtered out by `min_price` or
  `min_dollar_volume_millions`, or it has under a year of trading history.

*Educational tool, not investment advice. These signals describe what price and
volume have already done; they do not predict what a stock will do next.*
"""

nb = {
    "nbformat": 4, "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "cells": [
        md(INTRO),
        code(INSTALL, form=True),
        code("#@title Step 2 — the report builder  *(double-click to read the code)*\n"
             + report, form=True),
        code("#@title Step 3 — the screening engine  *(double-click to read the code)*\n"
             + engine, form=True),
        code(SETTINGS, form=True),
        code(RUN, form=True),
        md(NOTE),
    ],
}

out = "Institutional_Accumulation_Screener.ipynb"
with open(out, "w", encoding="utf-8") as fh:
    json.dump(nb, fh, indent=1)
print(f"wrote {out} ({len(nb['cells'])} cells)")
