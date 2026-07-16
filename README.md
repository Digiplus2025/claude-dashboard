# Claude Usage Dashboard — IT Asset Management

A Streamlit dashboard for visualizing Claude AI usage and spend, built from
monthly Excel exports out of the Claude Admin dashboard.

## Features

- Upload one or more monthly `.xlsx` spend reports; the app combines them for
  cross-month analysis.
- Sidebar filters (date range, model, user, product) that drive every chart
  and table on the page in real time, plus a Reset Filters button.
- KPI cards: Total Spend, Total Tokens, Active Users, Total Requests.
- Charts: Top 5 / Bottom 5 users by tokens, Token Usage by Model (donut),
  Daily/Weekly/Monthly usage trend, Spend per User (Top 10), Active vs
  Inactive Users.
- Full, searchable, paginated user table with token color-coding (red/yellow/
  green by quantile) and CSV export.
- A **User Detail** page for drilling into a single user's usage.

## Expected Excel columns

| Column | Description |
|---|---|
| User | User email address |
| Product | Claude Code, Chat, Claude in Chrome, Cowork, etc. |
| Model(s) | Model(s) used (comma-separated if more than one) |
| Requests | Number of requests |
| Total Tokens | Total tokens consumed |
| Net Spend (USD) | Cost in USD |
| Period | Billing period number |

The source files don't include a per-row calendar date, so on upload the app
tries to infer the report month from the filename (e.g. `..._2026-06.xlsx`,
`June 2026 report.xlsx`); if it can't, use the **"Confirm report month per
file"** panel in the sidebar to set it manually. This month is what powers the
date-range filter and the usage-trend chart.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Deploy to Streamlit Community Cloud (free, shareable public URL)

1. **Push this project to a GitHub repository** (public or private) — it
   needs at least `app.py` and `requirements.txt` at the repo root (or a
   known subfolder).
   ```bash
   git init
   git add app.py requirements.txt README.md .streamlit .gitignore
   git commit -m "Claude Usage Dashboard"
   git remote add origin https://github.com/<your-org>/<your-repo>.git
   git push -u origin main
   ```
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in
   with your GitHub account.
3. Click **"New app"**.
4. Select the repository, branch (e.g. `main`), and set the main file path
   to `app.py`.
5. (Optional) Under **"Advanced settings"** you can pin the Python version
   (3.10+) to match what this app was built for.
6. Click **"Deploy"**. Streamlit Cloud installs `requirements.txt` and starts
   the app — this takes a minute or two on first deploy.
7. Once live, you'll get a public URL like
   `https://<your-app-name>.streamlit.app` that you can share with your team.
8. To update the live app later, just push new commits to the same branch —
   Streamlit Cloud redeploys automatically.

### Notes on data privacy

Uploaded spend reports are only held in the app's in-memory session — they
are not written to disk or persisted between sessions. If your spend data is
sensitive, deploy the app as a **private** app on Streamlit Community Cloud
(viewer allow-list) rather than public, or self-host it behind your
organization's VPN/SSO.
