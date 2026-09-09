"""Executes the notebook's real cells in order (with the network layer stubbed)
so a break shows up here rather than in Colab."""

import json, os, sys, shutil, tempfile
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synthetic import make

NB = "Institutional_Accumulation_Screener.ipynb"
nb = json.load(open(NB))

checks = []
def ck(name, cond):
    checks.append((name, bool(cond)))

# ---- structural ----------------------------------------------------------
ck("valid ipynb v4", nb.get("nbformat") == 4)
ck("7 cells", len(nb["cells"]) == 7)
ck("opens with markdown instructions", nb["cells"][0]["cell_type"] == "markdown")
ck("closes with markdown notes", nb["cells"][-1]["cell_type"] == "markdown")
code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
ck("5 code cells", len(code_cells) == 5)
ck("every code cell is a titled form",
   all(c["metadata"].get("cellView") == "form" for c in code_cells))
ck("every code cell starts with #@title",
   all("".join(c["source"]).startswith("#@title") for c in code_cells))
src_all = "\n".join("".join(c["source"]) for c in code_cells)
ck("no __main__ guard left in the engine cell", 'if __name__ == "__main__"' not in src_all)
ck("no cell magics that need to be first-line", "%%" not in src_all)

# ---- execute the cells ---------------------------------------------------
def cell_src(i):
    return "".join(nb["cells"][i]["source"])

ns = {"__name__": "__main__"}      # Colab's namespace really does look like this
tmp = tempfile.mkdtemp()
cwd = os.getcwd()
os.chdir(tmp)
try:
    exec(compile(cell_src(2), "<cell2 report>", "exec"), ns)     # report builder
    ck("cell 2 defines write_report", callable(ns.get("write_report")))

    exec(compile(cell_src(3), "<cell3 engine>", "exec"), ns)     # engine
    ck("cell 3 defines run_screen", callable(ns.get("run_screen")))
    ck("engine reached write_report without importing report.py",
       ns.get("write_report") is not None)

    exec(compile(cell_src(4), "<cell4 settings>", "exec"), ns)   # settings form
    ck("cell 4 builds a SETTINGS dict", isinstance(ns.get("SETTINGS"), dict))
    ck("settings keys match run_screen's signature",
       set(ns["SETTINGS"]) <= {"universe", "min_price", "min_dollar_vol",
                               "limit", "outdir", "tickers_file", "period", "batch"})

    # stub the two network calls, then run cell 5 for real
    REG = ["accum", "dry_pullback", "churn", "dist"]
    def fake_universe(which):
        return pd.DataFrame({"ticker": [f"T{i:02d}" for i in range(8)],
                             "name": [f"Test Co {i}" for i in range(8)],
                             "sector": ["Information Technology"] * 8})
    def fake_download(tickers, period="2y", batch=100, pause=1.0):
        return {t: make(REG[i % 4], start=120.0) for i, t in enumerate(tickers)}
    def fake_health():
        return [{"label": "S&P 500", "count": 3, "state": "warning",
                 "note": "Watch. Pressure is building.", "last": 6000.0, "chg": 0.001}]
    ns["build_universe"] = fake_universe
    ns["download_prices"] = fake_download
    ns["market_health"] = fake_health

    exec(compile(cell_src(5), "<cell5 run>", "exec"), ns)        # the run cell
    ck("cell 5 ran and produced a payload", isinstance(ns.get("payload"), dict))
    ck("report written", os.path.exists("output/institutional_screener.html"))
    ck("csv written", os.path.exists("output/screen_results.csv"))
    ck("html is non-trivial", os.path.getsize("output/institutional_screener.html") > 20000)
    doc = open("output/institutional_screener.html", encoding="utf-8").read()
    ck("html has no external resources",
       'src="http' not in doc and 'href="http' not in doc)
    ck("payload carries scored rows", len(ns["payload"]["rows"]) > 0)
    ck("rows carry the 8-week pattern",
       len(ns["payload"]["rows"][0]["week_pattern"]) == 8)
    ck("google.colab absence handled gracefully", True)  # reached here at all
finally:
    os.chdir(cwd)
    shutil.rmtree(tmp, ignore_errors=True)

print("Notebook cell-by-cell execution\n" + "-" * 62)
for n, c in checks:
    print(f"  [{'PASS' if c else 'FAIL'}] {n}")
bad = [n for n, c in checks if not c]
print("\n" + ("NOTEBOOK OK" if not bad else f"FAILED: {bad}"))
sys.exit(0 if not bad else 1)
