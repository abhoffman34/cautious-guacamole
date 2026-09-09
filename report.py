"""Renders the screener payload into one self-contained HTML file."""

from __future__ import annotations

import json

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Institutional Accumulation Screener</title>
<style>
  :root {
    color-scheme: light;
    --plane:#f9f9f7; --surface:#fcfcfb; --raised:#ffffff;
    --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
    --rule:#e1e0d9; --ring:rgba(11,11,11,.10);
    --acc:#2a78d6; --acc-soft:#cde2fb; --acc-mid:#86b6ef;
    --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b;
    --good-ink:#006300; --crit-ink:#a32222;
    --wash:rgba(11,11,11,.04);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --plane:#0d0d0d; --surface:#1a1a19; --raised:#222221;
      --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
      --rule:#2c2c2a; --ring:rgba(255,255,255,.10);
      --acc:#3987e5; --acc-soft:#184f95; --acc-mid:#256abf;
      --good-ink:#0ca30c; --crit-ink:#e66767;
      --wash:rgba(255,255,255,.05);
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --plane:#0d0d0d; --surface:#1a1a19; --raised:#222221;
    --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
    --rule:#2c2c2a; --ring:rgba(255,255,255,.10);
    --acc:#3987e5; --acc-soft:#184f95; --acc-mid:#256abf;
    --good-ink:#0ca30c; --crit-ink:#e66767;
    --wash:rgba(255,255,255,.05);
  }

  * { box-sizing: border-box; }
  body {
    margin:0; background:var(--plane); color:var(--ink);
    font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:1280px; margin:0 auto; padding:28px 20px 80px; }

  header.top { display:flex; justify-content:space-between; align-items:flex-start;
    gap:20px; flex-wrap:wrap; margin-bottom:22px; }
  h1 { font-size:22px; letter-spacing:-.01em; margin:0 0 4px; font-weight:650; }
  .sub { color:var(--ink-2); font-size:13px; margin:0; }
  .sub b { color:var(--ink); font-weight:600; }
  .themebtn { background:var(--surface); border:1px solid var(--rule); color:var(--ink-2);
    border-radius:8px; padding:7px 12px; font:inherit; font-size:12.5px; cursor:pointer; }
  .themebtn:hover { background:var(--wash); }

  /* ---- market health ---- */
  .health { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
    gap:12px; margin-bottom:14px; }
  .tile { background:var(--surface); border:1px solid var(--rule); border-radius:12px;
    padding:14px 16px; display:flex; gap:14px; align-items:center; }
  .dot { width:10px; height:10px; border-radius:50%; flex:0 0 auto; }
  .tile .big { font-size:26px; font-weight:650; line-height:1.1; }
  .tile .lbl { font-size:12px; color:var(--ink-3); text-transform:uppercase;
    letter-spacing:.05em; }
  .tile .note { font-size:12.5px; color:var(--ink-2); }
  .s-good{color:var(--good-ink)} .s-warn{color:var(--serious)} .s-crit{color:var(--crit-ink)}
  .bg-good{background:var(--good)} .bg-warn{background:var(--warn)} .bg-crit{background:var(--crit)}

  .warn { background:var(--surface); border:1px solid var(--rule);
    border-left:3px solid var(--warn); border-radius:12px; padding:13px 16px;
    margin-bottom:14px; font-size:12.5px; color:var(--ink-2); line-height:1.55; }
  .warn b { color:var(--ink); }
  details.about { background:var(--surface); border:1px solid var(--rule);
    border-radius:12px; padding:0 16px; margin-bottom:18px; }
  details.about summary { cursor:pointer; padding:13px 0; font-weight:600; font-size:13.5px;
    list-style:none; display:flex; align-items:center; gap:8px; }
  details.about summary::-webkit-details-marker { display:none; }
  details.about summary::before { content:"›"; display:inline-block; transition:transform .15s;
    color:var(--ink-3); font-size:17px; }
  details.about[open] summary::before { transform:rotate(90deg); }
  .about-body { padding:2px 0 16px; color:var(--ink-2); font-size:13px; max-width:78ch; }
  .about-body dt { font-weight:600; color:var(--ink); margin-top:11px; }
  .about-body dd { margin:2px 0 0; }
  .about-body dl { margin:0; }

  /* ---- controls ---- */
  .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center;
    margin-bottom:14px; }
  input[type=search], select {
    background:var(--surface); border:1px solid var(--rule); color:var(--ink);
    border-radius:8px; padding:8px 10px; font:inherit; font-size:13px; }
  input[type=search] { min-width:190px; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { background:var(--surface); border:1px solid var(--rule); color:var(--ink-2);
    border-radius:999px; padding:7px 13px; font-size:12.5px; cursor:pointer;
    white-space:nowrap; }
  .chip[aria-pressed="true"] { background:var(--acc); border-color:var(--acc);
    color:#fff; font-weight:600; }
  .count { margin-left:auto; color:var(--ink-3); font-size:12.5px;
    font-variant-numeric:tabular-nums; }

  /* ---- table ---- */
  .tablecard { background:var(--surface); border:1px solid var(--rule);
    border-radius:12px; overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
  thead th { position:sticky; top:0; background:var(--surface); z-index:2;
    text-align:right; font-size:11px; letter-spacing:.05em; text-transform:uppercase;
    color:var(--ink-3); font-weight:600; padding:11px 10px; white-space:nowrap;
    border-bottom:1px solid var(--rule); cursor:pointer; user-select:none; }
  thead th:first-child, thead th.l { text-align:left; }
  thead th:hover { color:var(--ink); }
  thead th .arw { opacity:.45; font-size:9px; }
  tbody td { padding:9px 10px; text-align:right; border-bottom:1px solid var(--rule);
    white-space:nowrap; }
  tbody td.l { text-align:left; }
  tbody tr.row { cursor:pointer; }
  tbody tr.row:hover { background:var(--wash); }
  .tk { font-weight:650; letter-spacing:-.01em; }
  .nm { color:var(--ink-3); font-size:12px; max-width:220px; overflow:hidden;
    text-overflow:ellipsis; display:block; }
  .scorecell { display:flex; align-items:center; gap:9px; justify-content:flex-end; }
  .bar { width:58px; height:7px; background:var(--wash); border-radius:4px;
    overflow:hidden; flex:0 0 auto; }
  .bar > i { display:block; height:100%; background:var(--acc); border-radius:4px; }
  .scoreval { font-weight:650; min-width:34px; text-align:right; }
  .strip { display:inline-flex; gap:2px; }
  .cell { width:15px; height:17px; border-radius:3px; background:var(--wash);
    color:var(--ink-3); font-size:9.5px; font-weight:700; line-height:17px;
    text-align:center; }
  .cell.a { background:var(--good); color:#fff; }
  .cell.d { background:var(--crit); color:#fff; }
  .pill { font-size:11px; padding:3px 8px; border-radius:999px; font-weight:600;
    border:1px solid var(--ring); }
  .pos { color:var(--good-ink); } .neg { color:var(--crit-ink); }

  /* ---- detail ---- */
  tr.detail > td { padding:0; border-bottom:1px solid var(--rule); }
  .panel { padding:18px 20px 22px; background:var(--plane); display:grid;
    grid-template-columns:minmax(300px,1.1fr) minmax(300px,1fr); gap:26px 40px;
    text-align:left; align-items:start; white-space:normal; }
  .panel h4 { margin:0 0 12px; font-size:11px; letter-spacing:.06em;
    text-transform:uppercase; color:var(--ink-3); font-weight:600; }
  .comp { display:grid; grid-template-columns:1fr auto; gap:5px 12px;
    align-items:baseline; font-size:12.5px; }
  .comp .lab { color:var(--ink-2); text-align:left; }
  .comp .track { grid-column:1/-1; height:6px; background:var(--wash);
    border-radius:3px; margin:-2px 0 7px; overflow:hidden; }
  .comp .track > i { display:block; height:100%; background:var(--acc-mid);
    border-radius:3px; }
  .comp .val { font-weight:600; font-variant-numeric:tabular-nums; }
  .wk { display:flex; gap:4px; align-items:flex-end; height:78px;
    padding-bottom:2px; }
  .wk .col { flex:1; display:flex; flex-direction:column; align-items:center;
    gap:4px; justify-content:flex-end; }
  .wk .mark { width:100%; border-radius:3px 3px 0 0; background:var(--acc-mid);
    min-height:3px; }
  .wk .mark.a { background:var(--good); } .wk .mark.d { background:var(--crit); }
  .tick { font-size:10.5px; color:var(--ink-3); line-height:1.45; }
  .wk .tick { font-size:9.5px; }
  .verdict { margin-top:14px; font-size:13px; color:var(--ink-2);
    border-left:2px solid var(--acc); padding-left:11px; }
  .kv { display:grid; grid-template-columns:1fr auto; gap:5px 20px; font-size:12.5px;
    margin:16px 0 0; }
  .kv dt { color:var(--ink-2); }
  .kv dd { margin:0; font-variant-numeric:tabular-nums; font-weight:600;
    text-align:right; }
  .kv dt, .kv dd { padding-bottom:5px; border-bottom:1px solid var(--rule); }
  footer { margin-top:22px; color:var(--ink-3); font-size:12px; max-width:80ch; }
  .empty { padding:44px; text-align:center; color:var(--ink-3); }
  @media (max-width:820px) { .panel { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <div>
    <h1>Institutional Accumulation Screener</h1>
    <p class="sub">Reading price range and volume for institutional footprints &middot;
      <b id="uni"></b> &middot; generated <b id="gen"></b></p>
  </div>
  <button class="themebtn" id="theme">Toggle theme</button>
</header>

<section class="health" id="health"></section>

<details class="about">
  <summary>How the score is built</summary>
  <div class="about-body">
    <p style="margin-top:0">Institutions are too big to hide. Their buying and selling
    leaves a signature in a stock's <b>trading range</b> and <b>volume</b>. Six components,
    100 points total:</p>
    <dl>
      <dt>Up/down volume ratio, 50 days &mdash; 30 pts</dt>
      <dd>Volume on up days divided by volume on down days. Above 2.0 is strong
      accumulation, 1.0 is churn, below 1.0 points to heavier selling.</dd>
      <dt>Weekly range + volume &mdash; 25 pts</dt>
      <dd>Every one of the last eight weeks contributes where it closed in its own
      range, weighted by how heavy its volume was (the <b>weekly pressure</b> figure,
      running &minus;2 to +2). Weeks clearing the thresholds outright are marked
      <b>A</b> or <b>D</b> in the table, and consecutive A weeks earn a bonus &mdash;
      the pattern repeating is the signal, not any single week.</dd>
      <dt>A/D line slope, 25 days &mdash; 20 pts</dt>
      <dd>The classic Accumulation/Distribution line, its slope normalized by average
      volume so stocks of different size compare.</dd>
      <dt>Pullback volume drying &mdash; 10 pts</dt>
      <dd>When a stock pulls back on <i>lighter</i> volume, institutions are taking a
      break from buying rather than selling. Scored against the field's own spread, so
      the median name lands mid-scale.</dd>
      <dt>Volume expansion &mdash; 5 pts</dt>
      <dd>50-day average volume against the 200-day. No footprints, no institutions.</dd>
      <dt>Trend / support &mdash; 10 pts</dt>
      <dd>How far price sits above its 50- and 200-day averages and below its 52-week
      high &mdash; measured continuously, not as pass/fail. Accumulation only counts if
      the support floor is holding, but a stock 0.1% above its 50-day has not earned what
      one 20% above has.</dd>
    </dl>
    <p><b>Distribution days</b> (the market tiles above, and the DD column) count sessions
    closing lower on higher volume than the day before. The indexes use the article's
    literal 0.2%; individual stocks use the same rule expressed in their own volatility
    (0.22 sigma), because a 0.2% down day is a real event for an index and noise for a
    single stock. A few is noise; many in a short period is an early warning that
    institutions are stepping back.</p>

    <h4 style="margin:18px 0 6px;font-size:13.5px">Two things worth understanding before you sort by score</h4>

    <p><b>Bands are relative to this scan, not absolute.</b> "Strong Accumulation" means
    the top 5% of what was screened; Accumulation the next 15%; the middle 40% Neutral;
    then 25% Distribution and the bottom 15% Heavy Distribution. Fixed score cutoffs
    sound more objective and are in practice worse &mdash; the first version of this tool
    used them and labelled the median stock "Distribution" in a market where two thirds
    of names were above their 200-day average.</p>

    <p><b>Ex-momentum is the column to read second.</b> The composite score correlates
    heavily with recent price performance, partly by construction: a stock that rose
    necessarily had more up days, and up days carry the volume. Ex-momentum is what is
    left after the 63-day return is regressed out of the score &mdash; a positive figure
    means more institutional footprint than this stock's own price action would predict.
    Sorting by score finds what has already worked. Sorting by ex-momentum finds what
    may not have shown up in the price yet, which is the harder and more useful question.</p>

    <p><b>Sect %ile ranks a name inside its own sector.</b> A single ranking of the whole
    market hands you whichever sector the macro currently favours &mdash; four refiners in
    the top fourteen is one bet on crack spreads, not four independent institutional
    decisions. Sorting by Sect %ile, or capping the list with <b>Best N per sector</b>,
    answers the more useful question: is money moving into this name relative to the
    other places it could sit within the same sector? The cap applies after sorting, so
    it works on the ex-momentum ordering too.</p>

    <p><b>The Article column is a second, independent ranking.</b> It scores each name
    using only the tests the article itself names &mdash; up/down volume ratio, consecutive
    heavy-volume closes high in the weekly range, pullbacks on lighter volume, a holding
    support floor, few distribution days &mdash; with none of this tool's own additions.
    It also rewards a stock that has <i>already run</i>, because the article's worked
    example was up 500% on the year and still being accumulated. Where the two columns
    agree, the case is strong on both readings. Where they disagree, the disagreement is
    the interesting part: a high Article score with a low composite usually means an
    A/D line that is not confirming, and the reverse usually means a beaten-down name
    that the article's momentum-continuation framing would never have picked.</p>

    <p>A dot beside a signal means the name was <b>capped by the A/D gate</b>: it scored
    into an accumulation band while its Accumulation/Distribution line was falling, or
    with up/down volume below 1.0. Those two conditions contradict the label, so it is
    downgraded to Neutral rather than presented as a buy candidate.</p>
  </div>
</details>

<div class="controls">
  <input type="search" id="q" placeholder="Ticker or company" aria-label="Search">
  <div class="chips" id="chips"></div>
  <select id="sector" aria-label="Sector"></select>
  <select id="persector" aria-label="Limit per sector">
    <option value="0">All names</option>
    <option value="1">Best 1 per sector</option>
    <option value="2">Best 2 per sector</option>
    <option value="3">Best 3 per sector</option>
    <option value="5">Best 5 per sector</option>
  </select>
  <select id="persub" aria-label="Limit per sub-industry">
    <option value="0">All sub-industries</option>
    <option value="1">Best 1 per sub-industry</option>
    <option value="2">Best 2 per sub-industry</option>
  </select>
  <span class="count" id="count"></span>
</div>

<div class="tablecard">
  <table id="tbl">
    <thead><tr>
      <th class="l" data-k="rank">#<span class="arw"></span></th>
      <th class="l" data-k="ticker">Stock<span class="arw"></span></th>
      <th data-k="score">Score<span class="arw"></span></th>
      <th data-k="classification">Signal<span class="arw"></span></th>
      <th data-k="ex_mom" title="Score minus what the 63-day return alone predicts">Ex-mom<span class="arw"></span></th>
      <th data-k="art_score" title="Scored only on the tests the article itself names">Article<span class="arw"></span></th>
      <th data-k="ud_ratio">U/D vol<span class="arw"></span></th>
      <th class="l" data-k="acc_weeks">8-week pattern<span class="arw"></span></th>
      <th data-k="ad_slope">A/D slope<span class="arw"></span></th>
      <th data-k="dist_days">DD<span class="arw"></span></th>
      <th data-k="price">Price<span class="arw"></span></th>
      <th data-k="pct_off_high">Off high<span class="arw"></span></th>
      <th data-k="sector_pctile" title="Percentile within its own sector">Sect %ile<span class="arw"></span></th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>
  <div class="empty" id="empty" hidden>Nothing matches those filters.</div>
</div>

<footer>
  Educational tool, not investment advice. Signals describe what price and volume have
  already done; they do not predict what a stock will do next. Sort order is the composite
  score &mdash; always read the component breakdown before acting on a rank.
</footer>
</div>

<script>
const DATA = __PAYLOAD__;
const $ = s => document.querySelector(s);
const fmtM = v => v>=1e9 ? (v/1e9).toFixed(1)+"B" : v>=1e6 ? (v/1e6).toFixed(0)+"M" : (v/1e3).toFixed(0)+"K";
const pct = v => (v==null||!isFinite(v)) ? "&mdash;" : (v*100).toFixed(1)+"%";
const num = (v,d=2) => (v==null||!isFinite(v)) ? "&mdash;" : v.toFixed(d);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

$("#gen").textContent = DATA.generated;
$("#uni").textContent = DATA.count + " of " + DATA.scanned + " scanned";
if (DATA.fit && DATA.fit.r2 != null) {
  const n = document.createElement("p");
  n.className = "sub";
  n.style.marginTop = "4px";
  n.innerHTML = `Score explained by 63-day price momentum alone: <b>R&sup2; ${DATA.fit.r2.toFixed(2)}</b>`
    + (DATA.gated ? ` &middot; <b>${DATA.gated}</b> name${DATA.gated===1?"":"s"} capped by the A/D gate` : "")
    + ` &middot; sort by <b>Ex-mom</b> for the part the price hasn't already told you.`;
  $("#uni").closest("p").after(n);
}

/* sub-industry clusters — the sharpest form of the concentration problem */
const SUBC = (DATA.sectors && DATA.sectors.sub_concentration) || [];
if (SUBC.length) {
  const box = document.createElement("div");
  box.className = "warn";
  box.innerHTML = "<b>Clusters in the top " + DATA.sectors.top_n + ".</b> "
    + SUBC.map(c => `<b>${esc(c.sub_industry)}</b>: ${c.tickers.slice(0,6).map(esc).join(", ")}`
        + `${c.tickers.length>6?" …":""} (${c.got} names, ${c.expected} expected)`).join(" · ")
    + ". Same-sub-industry names move on the same driver — count them as one "
    + "position, not several. <b>Best N per sub-industry</b> collapses them.";
  $("#health").after(box);
}

/* concentration warning — one macro bet wearing several tickers */
const CONC = (DATA.sectors && DATA.sectors.concentration) || [];
if (CONC.length) {
  const box = document.createElement("div");
  box.className = "warn";
  box.innerHTML = "<b>Sector concentration in the top " + DATA.sectors.top_n + ".</b> "
    + CONC.map(c => `<b>${esc(c.sector)}</b> holds ${c.got} places against ${c.expected} expected `
        + `(${c.ratio}&times;) — ${c.tickers.slice(0,6).map(esc).join(", ")}`
        + `${c.tickers.length>6?" …":""}`).join(" · ")
    + ". Names clustered like this usually reflect one macro move rather than several "
    + "independent institutional decisions. Use <b>Best N per sector</b>, or sort by "
    + "<b>Sect %ile</b>, to see the list without that tilt.";
  $("#health").after(box);
}

/* market health tiles */
$("#health").innerHTML = DATA.health.map(h => `
  <div class="tile">
    <span class="dot bg-${h.state==='good'?'good':h.state==='warning'?'warn':'crit'}"></span>
    <div>
      <div class="lbl">${esc(h.label)} &middot; distribution days</div>
      <div class="big s-${h.state==='good'?'good':h.state==='warning'?'warn':'crit'}">${h.count}
        <span style="font-size:13px;font-weight:400;color:var(--ink-3)">of last ${DATA.params.dist_day_window}</span></div>
      <div class="note">${esc(h.note)}</div>
    </div>
  </div>`).join("") || '<div class="tile"><div class="note">Index data unavailable.</div></div>';

/* filters */
const BANDS = ["All","Strong Accumulation","Accumulation","Neutral / Churn","Distribution","Heavy Distribution"];
let band = "All", sector = "All", query = "", sortKey = "score", sortDir = -1,
    perSector = 0, perSub = 0;

$("#chips").innerHTML = BANDS.map(b =>
  `<button class="chip" data-b="${esc(b)}" aria-pressed="${b===band}">${esc(b)}</button>`).join("");
$("#chips").onclick = e => {
  const b = e.target.closest(".chip"); if(!b) return;
  band = b.dataset.b;
  [...$("#chips").children].forEach(c => c.setAttribute("aria-pressed", c.dataset.b===band));
  render();
};
const sectors = ["All", ...new Set(DATA.rows.map(r => r.sector).filter(s => s && s!=="Unknown"))].sort((a,b)=>a==="All"?-1:b==="All"?1:a.localeCompare(b));
$("#sector").innerHTML = sectors.map(s => `<option>${esc(s)}</option>`).join("");
$("#sector").onchange = e => { sector = e.target.value; render(); };
$("#persector").onchange = e => { perSector = +e.target.value; render(); };
$("#persub").onchange = e => { perSub = +e.target.value; render(); };
$("#q").oninput = e => { query = e.target.value.trim().toLowerCase(); render(); };

document.querySelectorAll("thead th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if (k === sortKey) sortDir *= -1;
  else { sortKey = k; sortDir = (k==="rank"||k==="ticker"||k==="pct_off_high") ? 1 : -1; }
  render();
});

function strip(p){
  return '<span class="strip">' + (p||[]).map(w =>
    `<span class="cell ${w.kind==='A'?'a':w.kind==='D'?'d':''}" title="${esc(w.week)} — closed ${(w.pos*100).toFixed(0)}% up its range">${w.kind==='-'?'':w.kind}</span>`).join("") + '</span>';
}

function verdict(r){
  let base;
  if (r.gated) base = "Ranked high on the composite, but its A/D line is falling and the label was capped — the components that scored well outvoted the one that most directly measures accumulation. Treat it as unresolved, not as a buy signal.";
  else if (r.churn_flag) base = "Heavy volume with no price progress — churn. Big money is trading it, but neither side is winning. Wait for the range to break.";
  else if (/Strong Accum/.test(r.classification)) base = "Textbook accumulation: up-volume dominant, repeated heavy-volume closes high in the weekly range, support holding.";
  else if (/Accumulation/.test(r.classification)) base = "Accumulation showing, but not on every component. Check which pieces are carrying the score.";
  else if (/Neutral/.test(r.classification)) base = "Mixed. Institutional footprints are inconclusive here.";
  else if (/Heavy Distribution/.test(r.classification)) base = "Heavy distribution. Down-day volume dominates and the range closes are weak.";
  else base = "Distribution signs: supply is being fed into demand on heavy volume.";

  if (isFinite(r.ex_mom)) {
    if (r.ex_mom >= 8) base += " Its footprint is well ahead of what the price has done — the kind of setup this screen exists to find.";
    else if (r.ex_mom <= -8) base += " Most of the score here is the price move itself; the volume evidence is thinner than the rank suggests.";
  }
  return base;
}

function panel(r){
  const max = {"Up/down volume (50d)":30,"Weekly range + volume":25,"A/D line slope (25d)":20,
               "Pullback volume drying":10,"Volume expansion":5,"Trend / support":10};
  const comps = Object.entries(r.components).map(([k,v]) => `
    <div class="lab">${esc(k)}</div><div class="val">${v.toFixed(1)} <span style="color:var(--ink-3);font-weight:400">/ ${max[k]??''}</span></div>
    <div class="track"><i style="width:${Math.max(0,Math.min(100,100*v/(max[k]||1)))}%"></i></div>`).join("");
  const wk = (r.week_pattern||[]).map(w => `
    <div class="col">
      <div class="mark ${w.kind==='A'?'a':w.kind==='D'?'d':''}" style="height:${Math.max(4,w.pos*62)}px"
           title="closed ${(w.pos*100).toFixed(0)}% up its range"></div>
      <div class="tick">${esc(w.week.split(" ")[1])}</div>
    </div>`).join("");
  return `<div class="panel">
    <div>
      <h4>Score components</h4>
      <div class="comp">${comps}</div>
      <div class="verdict">${esc(verdict(r))}</div>
    </div>
    <div>
      <h4>Where it closed in its weekly range &mdash; last ${(r.week_pattern||[]).length} weeks</h4>
      <div class="wk">${wk}</div>
      <div class="tick" style="margin-top:6px">Bar height = where the week closed in its
        range. <b style="color:var(--good-ink)">Green</b> = accumulation week (high close,
        heavy volume) &middot; <b style="color:var(--crit-ink)">red</b> = distribution week
        &middot; blue = ordinary volume.</div>
      <dl class="kv">
        <dt>Article-only score</dt><dd>${isFinite(r.art_score)?r.art_score.toFixed(1)+(r.art_rank?" (rank "+r.art_rank+")":""):"&mdash;"}</dd>
        <dt>Rank within this scan</dt><dd>${isFinite(r.pctile)?r.pctile.toFixed(0)+"th percentile":"&mdash;"}</dd>
        <dt>Rank within ${esc(r.sub_industry&&r.sub_industry!=="Unknown"?r.sub_industry:"its sub-industry")}</dt><dd>${isFinite(r.sub_pctile)?r.sub_pctile.toFixed(0)+"th percentile":"&mdash;"}</dd>
        <dt>Rank within ${esc(r.sector||"its sector")}</dt><dd>${isFinite(r.sector_pctile)?r.sector_pctile.toFixed(0)+"th percentile":"&mdash;"}${isFinite(r.sector_delta)?` (${r.sector_delta>0?"+":""}${r.sector_delta.toFixed(1)} vs sector median)`:""}</dd>
        <dt>Avg daily dollar volume</dt><dd>$${fmtM(r.avg_dollar_vol)}</dd>
        <dt>Ex-momentum (score vs price action)</dt><dd class="${r.ex_mom>0?'pos':r.ex_mom<0?'neg':''}">${isFinite(r.ex_mom)?(r.ex_mom>0?"+":"")+r.ex_mom.toFixed(1)+" pts":"&mdash;"}</dd>
        <dt>Weekly pressure (&minus;2 to +2)</dt><dd>${num(r.week_pressure)}</dd>
        <dt>Up/down volume (50d)</dt><dd>${num(r.ud_ratio)}</dd>
        <dt>Accumulation weeks</dt><dd>${r.acc_weeks} (longest run ${r.acc_streak})</dd>
        <dt>Distribution weeks</dt><dd>${r.dist_weeks}</dd>
        <dt>Pullback volume vs 50d avg</dt><dd>${num(r.pullback_dryness)}&times;</dd>
        <dt>Volume expansion (50d/200d)</dt><dd>${num(r.vol_expansion)}&times;</dd>
        <dt>vs 50-day avg</dt><dd>${pct(r.pct_vs_50dma)}</dd>
        <dt>vs 200-day avg</dt><dd>${pct(r.pct_vs_200dma)}</dd>
        <dt>63-day return</dt><dd>${pct(r.ret_63d)}</dd>
      </dl>
    </div>
  </div>`;
}

function render(){
  let rows = DATA.rows.filter(r =>
    (band==="All" || r.classification===band) &&
    (sector==="All" || r.sector===sector) &&
    (!query || r.ticker.toLowerCase().includes(query) || (r.name||"").toLowerCase().includes(query))
  ).sort((a,b) => {
    const x=a[sortKey], y=b[sortKey];
    if (typeof x === "string") return sortDir * x.localeCompare(y);
    const xv = (x==null||!isFinite(x)) ? -1e18 : x, yv = (y==null||!isFinite(y)) ? -1e18 : y;
    return sortDir * (xv - yv);
  });

  // Cap per sector AFTER sorting, so "best 2 per sector" means best by whatever
  // column is currently sorted — score, ex-momentum, or anything else.
  if (perSector > 0) {
    const seen = {};
    rows = rows.filter(r => {
      const s = r.sector || "Unknown";
      seen[s] = (seen[s] || 0) + 1;
      return seen[s] <= perSector;
    });
  }
  if (perSub > 0) {
    const seen = {};
    rows = rows.filter(r => {
      const s = r.sub_industry || "Unknown";
      if (s === "Unknown") return true;
      seen[s] = (seen[s] || 0) + 1;
      return seen[s] <= perSub;
    });
  }

  $("#count").textContent = rows.length + " stocks"
    + (perSector ? ` · best ${perSector} per sector` : "");
  $("#empty").hidden = rows.length > 0;
  document.querySelectorAll("thead th").forEach(th => {
    th.querySelector(".arw").textContent = th.dataset.k===sortKey ? (sortDir>0?" ▲":" ▼") : "";
  });

  $("#tb").innerHTML = rows.map(r => `
    <tr class="row" data-t="${esc(r.ticker)}">
      <td class="l" style="color:var(--ink-3)">${r.rank}</td>
      <td class="l"><span class="tk">${esc(r.ticker)}</span><span class="nm">${esc(r.name||"")}</span></td>
      <td><div class="scorecell"><div class="bar"><i style="width:${Math.max(2,r.score)}%"></i></div>
          <span class="scoreval">${r.score.toFixed(0)}</span></div></td>
      <td><span class="pill ${/Accum/.test(r.classification)?'pos':/Distrib/.test(r.classification)?'neg':''}"
          title="${r.gated?'Capped by the A/D gate — labelled accumulation while its A/D line was falling':''}">${r.churn_flag?'Churn':esc(r.classification.replace(' / Churn',''))}${r.gated?' •':''}</span></td>
      <td class="${r.ex_mom>0?'pos':r.ex_mom<0?'neg':''}">${r.ex_mom==null||!isFinite(r.ex_mom)?"&mdash;":(r.ex_mom>0?"+":"")+r.ex_mom.toFixed(1)}</td>
      <td title="${r.art_rank?'article rank '+r.art_rank:''}">${isFinite(r.art_score)?r.art_score.toFixed(0):"&mdash;"}</td>
      <td>${num(r.ud_ratio)}</td>
      <td class="l">${strip(r.week_pattern)}</td>
      <td>${num(r.ad_slope)}</td>
      <td>${r.dist_days}</td>
      <td>$${num(r.price)}</td>
      <td>${pct(r.pct_off_high)}</td>
      <td>${isFinite(r.sector_pctile)?r.sector_pctile.toFixed(0):"&mdash;"}</td>
    </tr>`).join("");
}

$("#tb").onclick = e => {
  const tr = e.target.closest("tr.row"); if(!tr) return;
  const nxt = tr.nextElementSibling;
  if (nxt && nxt.classList.contains("detail")) { nxt.remove(); return; }
  document.querySelectorAll("tr.detail").forEach(d => d.remove());
  const r = DATA.rows.find(x => x.ticker === tr.dataset.t);
  const d = document.createElement("tr");
  d.className = "detail";
  d.innerHTML = `<td colspan="13">${panel(r)}</td>`;
  tr.after(d);
};

$("#theme").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const dark = cur ? cur === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
};

render();
</script>
</body>
</html>
"""


def write_report(payload: dict, path: str) -> str:
    html = TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, default=float))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path
