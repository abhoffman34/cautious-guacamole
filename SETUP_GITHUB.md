# Weekly automatic scan — one-time setup

This makes the screener run itself every Saturday morning on GitHub's servers,
free, with no computer of yours involved. It commits the results back to the repo,
where I can read them and write you the week-over-week changes.

Roughly ten minutes, once.

## Why the repo has to be public

I read the results over plain HTTPS with no credentials, so the file has to be
publicly readable. Nothing sensitive is in it — the code we wrote and public market
data. If you'd rather keep it private, the scan still runs and still emails you via
GitHub's own notifications, but I won't be able to fetch the digest automatically and
we'd fall back to you pasting the CSV in.

## Steps

**1. Create the repo.** At [github.com/new](https://github.com/new): name it
`institutional-screener`, set it to **Public**, tick "Add a README file", Create.

**2. Upload the four code files.** On the repo page, **Add file → Upload files**, drag
in:

- `institutional_screener.py`
- `report.py`
- `make_digest.py`
- `requirements.txt`

Commit them.

**3. Add the workflow.** This one needs a folder path, so use **Add file → Create new
file**. In the filename box type exactly:

```
.github/workflows/weekly-scan.yml
```

(typing the `/` characters creates the folders). Paste in the contents of
`weekly-scan.yml` from this bundle, and commit.

**4. Let the workflow write back.** **Settings → Actions → General**, scroll to
**Workflow permissions**, choose **Read and write permissions**, Save. Without this the
commit step fails.

**5. Test it now.** **Actions** tab → **Weekly institutional accumulation scan** → **Run
workflow** → Run. It takes 10–20 minutes. When it's green, check that
`latest/weekly_digest.md` exists in the repo.

**6. Send me the repo URL.** I'll wire up the weekly read and the assessment.

## What it produces

| path | what |
| --- | --- |
| `latest/weekly_digest.md` | the week-over-week summary I read |
| `latest/screen_results.csv` | the full scan |
| `latest/institutional_screener.html` | the interactive report — download and open |
| `history/YYYY-MM-DD_results.csv` | prior scans, last 26 weeks |

## Schedule

`cron: "0 12 * * 6"` — Saturday 12:00 UTC, which is 7am Chicago in summer and 6am in
winter. Friday's close is fully settled by then. Change the cron line in the workflow
if you want a different time; GitHub crons are always UTC.

## The failure mode to expect

Yahoo Finance throttles datacentre IP addresses, and GitHub's runners are datacentre
IPs. The workflow already uses smaller batches and retries the whole run once after a
two-minute wait, but a week will occasionally fail anyway. When that happens the repo
keeps last week's digest, and you'll get a failure email from GitHub. Re-running the
workflow by hand from the Actions tab usually clears it.

If it starts failing consistently, the fix is a real data API — Tiingo and EODHD both
have free tiers that don't throttle this way, and swapping the download function is a
small change.

## Cost

Nothing. Public repos get unlimited GitHub Actions minutes.
