
# GeBIZ Daily Listings to Excel – Web App

A small Flask web application that fetches daily GeBIZ business opportunities via **RSS feeds** (preferred, compliant) and an optional **HTML fallback** for the "Today's Opportunities" page, then normalizes and exports them into an Excel workbook compatible with your internal "Tender Comb" format.

## Key Features
- Pulls opportunities from GeBIZ RSS feeds by procurement category.
- Optional HTML fallback for Today's Opportunities (use responsibly; see Terms of Use).
- Keyword/agency/category filters to keep only relevant items (e.g., healthcare, rehabilitation, lab equipment).
- Exports to `output/gebiz_daily.xlsx` and (optionally) appends to an existing Tender Comb workbook.
- Simple web UI: trigger a fetch, preview results, download the Excel.
- Scheduler (APScheduler) to auto-run daily at 08:00 SGT.

## Important Compliance Notes
- Prefer **RSS**: GeBIZ provides RSS feeds for business opportunities. See: https://www.gebiz.gov.sg/business-alerts.html
- Follow GeBIZ **Terms of Use** and **RSS Terms of Use**: https://www.gebiz.gov.sg/terms-of-use.html and https://www.gebiz.gov.sg/rss-terms-of-use.html
- Do **not** copy or redistribute tender contents beyond internal bidding preparation. Respect any restrictions displayed on opportunity pages.

## Quick Start
1. **Prerequisites**: Python 3.10+, Google Chrome or Chromium (only if you enable HTML fallback with Playwright/Selenium), and `pip`.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure feeds and filters** in `config/feeds.yaml` and `config/filters.yaml`.
4. **Run the app**:
   ```bash
   FLASK_APP=app.py flask run --port 8000
   ```
   Then open http://localhost:8000 and click **Fetch Today**.
5. **Enable scheduler** (optional): set `ENABLE_SCHEDULER=true` in `.env` and start the app; it will fetch daily at 08:00 SGT.

## Structure
- `app.py` – Flask routes, scheduler, and UI.
- `collector/rss_client.py` – RSS ingestion.
- `collector/html_fallback.py` – Optional HTML fallback.
- `processor/normalize.py` – Parse & normalize items into uniform schema.
- `exporter/excel.py` – Write Excel compatible with Tender Comb.
- `config/feeds.yaml` – RSS feed URLs.
- `config/filters.yaml` – Keywords, agencies, categories to include/exclude.
- `.env.example` – Runtime options.

## Tender Comb Mapping (Suggested)
| Export Column | Description |
|---|---|
| Portal | Always `GeBIZ` |
| Tender Ref | Document/Tender No (e.g., HDB000ETT25000296) |
| Customer | Agency (e.g., Housing and Development Board) |
| Tender Description | Title (first 200 chars) |
| Date Detected | Date fetched (SGT) |
| Closing Date | Closing date/time from item |
| Closing Time | Extracted time if available |
| Status | `OPEN` (or as per item) |
| Deal ID | (leave blank to be filled later) |
| Remarks | Source link |

## Note on Playwright/Selenium
- Many GeBIZ pages render fine with static HTML; some parts may be dynamic.
- If you enable HTML fallback, ensure you comply with site terms and rate limits.
- RSS remains the recommended, low-risk method.

## Docker (optional)
You can run with Docker if you prefer a containerized setup. See `Dockerfile`.
