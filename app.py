"""Claude Usage Dashboard — IT Asset Management."""

from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Page config & theme
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Claude Usage Dashboard — IT Asset Management",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Palette (validated categorical order — see dataviz skill: fixed hue order,
# never cycled or reassigned per-filter). Dark-surface steps, blue swapped to
# the org's brand accent.
COLOR_SURFACE = "#0e1117"
COLOR_GRID = "#2c2c2a"
COLOR_TEXT_SECONDARY = "#c3c2b7"
COLOR_MUTED = "#898781"

BLUE = "#378ADD"
GREEN_GOOD = "#0ca30c"
RED_CRITICAL = "#e66767"
YELLOW_WARN = "#eda100"

CATEGORICAL = [
    "#378ADD",  # 1 blue (brand)
    "#199e70",  # 2 aqua
    "#c98500",  # 3 yellow
    "#008300",  # 4 green
    "#9085e9",  # 5 violet
    "#e66767",  # 6 red
    "#d55181",  # 7 magenta
    "#d95926",  # 8 orange
]

st.markdown(
    f"""
    <style>
    .kpi-card {{
        background: #161a23;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        height: 100%;
    }}
    .kpi-label {{
        font-size: 0.85rem;
        color: {COLOR_TEXT_SECONDARY};
        margin-bottom: 0.25rem;
    }}
    .kpi-value {{
        font-size: 1.7rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.2;
    }}
    .kpi-sub {{
        font-size: 0.78rem;
        color: {COLOR_MUTED};
        margin-top: 0.2rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = [
    "User",
    "Product",
    "Model(s)",
    "Requests",
    "Total Tokens",
    "Net Spend (USD)",
    "Period",
]

COLUMN_ALIASES = {
    "user": "User",
    "email": "User",
    "user email": "User",
    "product": "Product",
    "model(s)": "Model(s)",
    "models": "Model(s)",
    "model": "Model(s)",
    "requests": "Requests",
    "request count": "Requests",
    "total tokens": "Total Tokens",
    "tokens": "Total Tokens",
    "net spend (usd)": "Net Spend (USD)",
    "net spend": "Net Spend (USD)",
    "spend (usd)": "Net Spend (USD)",
    "cost (usd)": "Net Spend (USD)",
    "period": "Period",
}

DATE_ALIASES = {
    "date": "Date",
    "usage date": "Date",
    "billing date": "Date",
    "period start": "Date",
    "period start date": "Date",
    "month": "Date",
}

MONTH_NAMES = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|"
    "april|june|july|august|september|october|november|december"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def format_tokens(n: float) -> str:
    n = float(n or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K"
    return f"{sign}{n:.0f}"


def format_currency(n: float) -> str:
    return f"${n:,.2f}"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[key]
        elif key in DATE_ALIASES:
            rename_map[col] = DATE_ALIASES[key]
    return df.rename(columns=rename_map)


def guess_date_from_filename(filename: str) -> date | None:
    stem = filename.rsplit(".", 1)[0]
    m = re.search(r"(20\d{2})[-_](\d{1,2})", stem)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return date(year, month, 1)
    m = re.search(rf"({MONTH_NAMES})[a-z]*[\s_-]*?(20\d{{2}})", stem, re.IGNORECASE)
    if m:
        try:
            parsed = datetime.strptime(m.group(0).replace("_", " ").replace("-", " "), "%b %Y")
        except ValueError:
            try:
                parsed = datetime.strptime(m.group(0).replace("_", " ").replace("-", " "), "%B %Y")
            except ValueError:
                parsed = None
        if parsed:
            return parsed.date().replace(day=1)
    return None


@st.cache_data(show_spinner=False)
def read_excel_bytes(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")


def load_uploaded_file(uploaded_file) -> tuple[pd.DataFrame | None, str | None]:
    """Returns (dataframe, error_message)."""
    if not uploaded_file.name.lower().endswith(".xlsx"):
        return None, "Invalid file format. Please upload a .xlsx file exported from Claude Admin."
    try:
        raw = read_excel_bytes(uploaded_file.getvalue())
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not read '{uploaded_file.name}': {exc}"

    df = normalize_columns(raw)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, (
            f"'{uploaded_file.name}' is missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}."
        )

    df["Requests"] = pd.to_numeric(df["Requests"], errors="coerce").fillna(0)
    df["Total Tokens"] = pd.to_numeric(df["Total Tokens"], errors="coerce").fillna(0)
    df["Net Spend (USD)"] = pd.to_numeric(df["Net Spend (USD)"], errors="coerce").fillna(0)
    df["User"] = df["User"].astype(str).str.strip()
    df["Product"] = df["Product"].astype(str).str.strip()
    df["Model(s)"] = df["Model(s)"].astype(str).str.strip()
    df["Source File"] = uploaded_file.name

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    else:
        df["Date"] = pd.NaT

    return df, None


def explode_models(df: pd.DataFrame) -> pd.DataFrame:
    """One row per model listed in 'Model(s)', metrics split evenly across models
    named in that row so per-model totals stay consistent with row totals."""
    work = df.copy()
    work["_models"] = work["Model(s)"].apply(
        lambda s: [m.strip() for m in str(s).split(",") if m.strip()] or ["Unknown"]
    )
    work["_n"] = work["_models"].apply(len)
    exploded = work.explode("_models")
    for col in ["Requests", "Total Tokens", "Net Spend (USD)"]:
        exploded[col] = exploded[col] / exploded["_n"]
    exploded = exploded.rename(columns={"_models": "Model"}).drop(columns=["_n"])
    return exploded


def model_options(df: pd.DataFrame) -> list[str]:
    models = set()
    for s in df["Model(s)"].dropna().astype(str):
        for m in s.split(","):
            m = m.strip()
            if m:
                models.add(m)
    return sorted(models)


def filter_by_models(df: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
    if not selected:
        return df
    selected_set = set(selected)

    def row_matches(s):
        row_models = {m.strip() for m in str(s).split(",") if m.strip()}
        return bool(row_models & selected_set)

    return df[df["Model(s)"].apply(row_matches)]


def token_color(value: float, low_cut: float, high_cut: float) -> str:
    if value >= high_cut:
        return RED_CRITICAL
    if value <= low_cut:
        return GREEN_GOOD
    return YELLOW_WARN


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

if "raw_frames" not in st.session_state:
    st.session_state.raw_frames = {}  # filename -> dataframe
if "file_dates" not in st.session_state:
    st.session_state.file_dates = {}  # filename -> date
if "page" not in st.session_state:
    st.session_state.page = "Overview Dashboard"

FILTER_DEFAULTS = {
    "f_date_range": None,
    "f_models": [],
    "f_users": [],
    "f_products": [],
}
for k, v in FILTER_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_filters():
    for k, v in FILTER_DEFAULTS.items():
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — navigation + upload
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🤖 Claude Usage")
    st.session_state.page = st.radio(
        "Page", ["Overview Dashboard", "User Detail"], label_visibility="collapsed"
    )

    st.divider()
    st.subheader("📁 Upload Reports")
    uploaded_files = st.file_uploader(
        "Claude Admin monthly spend export(s) (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for f in uploaded_files:
            if f.name not in st.session_state.raw_frames:
                df, err = load_uploaded_file(f)
                if err:
                    st.error(err)
                    continue
                st.session_state.raw_frames[f.name] = df
                if f.name not in st.session_state.file_dates:
                    guessed = guess_date_from_filename(f.name)
                    if guessed is None and df["Date"].notna().any():
                        guessed = df["Date"].dropna().dt.date.min()
                    st.session_state.file_dates[f.name] = guessed
                st.success(f"Loaded '{f.name}' — {len(df):,} records.")

    needs_date_assignment = [
        name
        for name, df in st.session_state.raw_frames.items()
        if df["Date"].isna().all() and st.session_state.file_dates.get(name) is None
    ]
    if st.session_state.raw_frames:
        with st.expander("📅 Confirm report month per file", expanded=bool(needs_date_assignment)):
            existing_dates = [d for d in st.session_state.file_dates.values() if d]
            fallback = max(existing_dates) if existing_dates else date.today().replace(day=1)
            for i, name in enumerate(st.session_state.raw_frames):
                default = st.session_state.file_dates.get(name) or (
                    fallback - timedelta(days=30 * (len(st.session_state.raw_frames) - i - 1))
                ).replace(day=1)
                picked = st.date_input(name, value=default, key=f"date_pick_{name}")
                st.session_state.file_dates[name] = picked.replace(day=1)

        if st.button("🗑️ Clear all uploaded files", use_container_width=True):
            st.session_state.raw_frames = {}
            st.session_state.file_dates = {}
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Build combined dataset
# ─────────────────────────────────────────────────────────────────────────────

if not st.session_state.raw_frames:
    st.title("Claude Usage Dashboard — IT Asset Management")
    st.info("Please upload your Claude spend report Excel file to get started.")
    st.caption(f"Expected columns: {', '.join(REQUIRED_COLUMNS)}")
    st.stop()

frames = []
for name, df in st.session_state.raw_frames.items():
    d = df.copy()
    file_month = st.session_state.file_dates.get(name)
    if d["Date"].isna().any() and file_month:
        d["Date"] = d["Date"].fillna(pd.Timestamp(file_month))
    frames.append(d)

combined = pd.concat(frames, ignore_index=True)
combined["Date"] = pd.to_datetime(combined["Date"])

data_min_date = combined["Date"].min().date()
data_max_date = combined["Date"].max().date()

# Streamlit widgets keep their own state once initialized, so if a newly
# uploaded file expands the available date coverage, the date_input must be
# reset explicitly or it silently keeps filtering to the old, narrower range.
if st.session_state.get("_last_data_range") != (data_min_date, data_max_date):
    st.session_state.pop("date_range_widget", None)
    st.session_state.f_date_range = None
    st.session_state["_last_data_range"] = (data_min_date, data_max_date)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — filters
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.divider()
    st.subheader("🔎 Filters")

    date_range = st.date_input(
        "Date range",
        value=st.session_state.f_date_range or (data_min_date, data_max_date),
        min_value=data_min_date,
        max_value=data_max_date,
        key="date_range_widget",
    )
    st.session_state.f_date_range = date_range

    all_models = model_options(combined)
    st.session_state.f_models = st.multiselect(
        "Model", all_models, default=st.session_state.f_models
    )

    all_users = sorted(combined["User"].unique())
    st.session_state.f_users = st.multiselect(
        "User (search by email)", all_users, default=st.session_state.f_users
    )

    all_products = sorted(combined["Product"].unique())
    st.session_state.f_products = st.multiselect(
        "Product", all_products, default=st.session_state.f_products
    )

    if st.button("↺ Reset Filters", use_container_width=True):
        reset_filters()
        st.rerun()

    st.divider()
    st.caption(
        f"**Data loaded:** {len(combined):,} records\n\n"
        f"**Coverage:** {data_min_date:%b %d, %Y} → {data_max_date:%b %d, %Y}\n\n"
        f"**Files:** {len(st.session_state.raw_frames)}"
    )

# Apply filters
filtered = combined.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["Date"].dt.date >= start) & (filtered["Date"].dt.date <= end)
    ]
if st.session_state.f_models:
    filtered = filter_by_models(filtered, st.session_state.f_models)
if st.session_state.f_users:
    filtered = filtered[filtered["User"].isin(st.session_state.f_users)]
if st.session_state.f_products:
    filtered = filtered[filtered["Product"].isin(st.session_state.f_products)]

# ─────────────────────────────────────────────────────────────────────────────
# Shared KPI computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_kpis(df: pd.DataFrame) -> dict:
    total_spend = df["Net Spend (USD)"].sum()
    total_tokens = df["Total Tokens"].sum()
    total_requests = df["Requests"].sum()
    active_users = df.loc[df["Requests"] > 0, "User"].nunique()
    return {
        "total_spend": total_spend,
        "total_tokens": total_tokens,
        "total_requests": total_requests,
        "active_users": active_users,
    }


def render_kpi_cards(df: pd.DataFrame):
    k = compute_kpis(df)
    active_users = k["active_users"] or 1

    cards = [
        (
            "💰 Total Spend (Net USD)",
            format_currency(k["total_spend"]),
            f"{format_currency(k['total_spend'] / active_users)} / user avg",
        ),
        (
            "🎯 Total Tokens",
            format_tokens(k["total_tokens"]),
            f"{format_tokens(k['total_tokens'] / k['total_requests'] if k['total_requests'] else 0)} tokens/request avg",
        ),
        (
            "👥 Active Users",
            f"{k['active_users']:,}",
            f"{k['total_requests'] / active_users:,.0f} requests/user avg",
        ),
        (
            "📊 Total Requests",
            f"{k['total_requests']:,.0f}",
            f"{format_tokens(k['total_tokens'] / active_users)} tokens/user avg",
        ),
    ]

    cols = st.columns(4)
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    return k


PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color=COLOR_TEXT_SECONDARY,
    margin=dict(l=10, r=10, t=40, b=10),
)


# ─────────────────────────────────────────────────────────────────────────────
# Overview Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def render_overview(df: pd.DataFrame):
    st.title("Claude Usage Dashboard — IT Asset Management")
    st.caption("Organization-wide usage & spend overview")

    if df.empty:
        st.warning("No data found for the selected period.")
        return

    render_kpi_cards(df)
    st.divider()

    user_agg = (
        df.groupby("User", as_index=False)
        .agg(Total_Tokens=("Total Tokens", "sum"), Requests=("Requests", "sum"), Net_Spend=("Net Spend (USD)", "sum"))
        .rename(columns={"Total_Tokens": "Total Tokens", "Net_Spend": "Net Spend (USD)"})
    )

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Top 5 Users by Token Consumption")
        top5 = user_agg.sort_values("Total Tokens", ascending=False).head(5).sort_values("Total Tokens")
        if top5.empty:
            st.info("No usage data available.")
        else:
            fig = go.Figure(
                go.Bar(
                    x=top5["Total Tokens"],
                    y=top5["User"],
                    orientation="h",
                    marker_color=BLUE,
                    text=[format_tokens(v) for v in top5["Total Tokens"]],
                    textposition="outside",
                )
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=320, xaxis_title="Tokens", yaxis_title="")
            fig.update_xaxes(gridcolor=COLOR_GRID)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Least Active Users (Bottom 5)")
        bottom5 = user_agg.sort_values("Total Tokens", ascending=True).head(5).sort_values("Total Tokens", ascending=False)
        if bottom5.empty:
            st.info("No usage data available.")
        else:
            fig = go.Figure(
                go.Bar(
                    x=bottom5["Total Tokens"],
                    y=bottom5["User"],
                    orientation="h",
                    marker_color=GREEN_GOOD,
                    text=[format_tokens(v) for v in bottom5["Total Tokens"]],
                    textposition="outside",
                )
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=320, xaxis_title="Tokens", yaxis_title="")
            fig.update_xaxes(gridcolor=COLOR_GRID)
            st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        st.subheader("Token Usage by Model")
        model_df = explode_models(df)
        model_agg = model_df.groupby("Model", as_index=False)["Total Tokens"].sum().sort_values(
            "Total Tokens", ascending=False
        )
        if model_agg.empty or model_agg["Total Tokens"].sum() == 0:
            st.info("No model usage data available.")
        else:
            ordered_models = sorted(model_agg["Model"].unique())
            color_map = {m: CATEGORICAL[i % len(CATEGORICAL)] for i, m in enumerate(ordered_models)}
            fig = px.pie(
                model_agg,
                names="Model",
                values="Total Tokens",
                hole=0.45,
                color="Model",
                color_discrete_map=color_map,
            )
            fig.update_traces(textinfo="percent+label", textposition="inside")
            fig.update_layout(**PLOTLY_LAYOUT, height=340, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    with c4:
        st.subheader("Usage Trend")
        granularity = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True, index=2)
        freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "MS"}
        trend = (
            df.set_index("Date")
            .resample(freq_map[granularity])["Total Tokens"]
            .sum()
            .reset_index()
        )
        if trend.empty:
            st.info("No usage data available.")
        else:
            fig = go.Figure(
                go.Scatter(
                    x=trend["Date"],
                    y=trend["Total Tokens"],
                    mode="lines+markers",
                    line=dict(color=BLUE, shape="spline", width=2),
                    marker=dict(size=8, color=BLUE),
                )
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=340, xaxis_title="", yaxis_title="Tokens")
            fig.update_xaxes(gridcolor=COLOR_GRID)
            fig.update_yaxes(gridcolor=COLOR_GRID)
            st.plotly_chart(fig, use_container_width=True)
            if granularity in ("Daily", "Weekly") and df["Date"].dt.to_period("M").nunique() == len(df["Date"].unique()):
                st.caption(
                    "Note: uploaded reports carry one data point per billing month, "
                    "so Daily/Weekly views will show the same monthly points until "
                    "a source file with finer-grained dates is provided."
                )

    st.divider()
    st.subheader("Spend per User (Top 10)")
    top10_spend = user_agg.sort_values("Net Spend (USD)", ascending=False).head(10)
    if top10_spend.empty:
        st.info("No spend data available.")
    else:
        fig = go.Figure(
            go.Bar(
                x=top10_spend["User"],
                y=top10_spend["Net Spend (USD)"],
                marker_color=BLUE,
                text=[format_currency(v) for v in top10_spend["Net Spend (USD)"]],
                textposition="outside",
            )
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=380, xaxis_title="", yaxis_title="Net Spend (USD)")
        fig.update_xaxes(gridcolor=COLOR_GRID, tickangle=-30)
        fig.update_yaxes(gridcolor=COLOR_GRID)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Active vs Inactive Users")
    active_mask = user_agg["Requests"] > 0
    active_count = int(active_mask.sum())
    inactive_count = int((~active_mask).sum())

    ac1, ac2 = st.columns([1, 1])
    with ac1:
        fig = go.Figure(
            go.Pie(
                labels=["Active", "Inactive"],
                values=[active_count, inactive_count],
                hole=0.5,
                marker_colors=[GREEN_GOOD, RED_CRITICAL],
                textinfo="label+percent+value",
            )
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=300, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    with ac2:
        st.metric("Active Users", active_count)
        st.metric("Inactive Users (assigned, 0 requests)", inactive_count)
        with st.expander(f"View {inactive_count} inactive user(s)"):
            inactive_list = user_agg.loc[~active_mask, "User"].sort_values()
            if inactive_list.empty:
                st.caption("No inactive users in the current filter selection.")
            else:
                st.dataframe(inactive_list.to_frame(name="User"), use_container_width=True, hide_index=True)

    st.divider()
    render_full_table(df, user_agg)


def render_full_table(df: pd.DataFrame, user_agg: pd.DataFrame):
    st.subheader("Full User Table")

    search = st.text_input("🔍 Search by email", key="table_search")
    table_df = df[
        ["User", "Product", "Model(s)", "Requests", "Total Tokens", "Net Spend (USD)", "Period"]
    ].copy()
    if search:
        table_df = table_df[table_df["User"].str.contains(search, case=False, na=False)]

    if table_df.empty:
        st.info("No data found for the selected period.")
        return

    tokens = table_df["Total Tokens"]
    low_cut = tokens.quantile(0.20)
    high_cut = tokens.quantile(0.80)

    def highlight_tokens(col):
        return [
            f"background-color: {token_color(v, low_cut, high_cut)}22; color: {token_color(v, low_cut, high_cut)}; font-weight: 600;"
            for v in col
        ]

    total_rows = len(table_df)
    page_size = 20
    total_pages = max(1, (total_rows - 1) // page_size + 1)
    page_num = st.number_input(
        f"Page (1–{total_pages})", min_value=1, max_value=total_pages, value=1, step=1
    )
    start_idx = (page_num - 1) * page_size
    page_df = table_df.iloc[start_idx : start_idx + page_size]

    styled = page_df.style.apply(highlight_tokens, subset=["Total Tokens"]).format(
        {
            "Total Tokens": format_tokens,
            "Net Spend (USD)": format_currency,
            "Requests": "{:,.0f}",
        }
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.caption(f"Showing rows {start_idx + 1}-{min(start_idx + page_size, total_rows)} of {total_rows:,}")

    csv_bytes = table_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Export to CSV",
        data=csv_bytes,
        file_name="claude_usage_export.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# User Detail page
# ─────────────────────────────────────────────────────────────────────────────

def render_user_detail(df: pd.DataFrame):
    st.title("User Detail")
    st.caption("Drill-down view for individual user analysis")

    if df.empty:
        st.warning("No data found for the selected period.")
        return

    users = sorted(df["User"].unique())
    default_user = st.session_state.f_users[0] if st.session_state.f_users else users[0]
    selected_user = st.selectbox("Select a user", users, index=users.index(default_user) if default_user in users else 0)

    user_df = df[df["User"] == selected_user]
    if user_df.empty:
        st.info("No data found for the selected period.")
        return

    render_kpi_cards(user_df)
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Token Usage by Model")
        model_df = explode_models(user_df)
        model_agg = model_df.groupby("Model", as_index=False)["Total Tokens"].sum().sort_values(
            "Total Tokens", ascending=False
        )
        if model_agg.empty or model_agg["Total Tokens"].sum() == 0:
            st.info("No model usage data available.")
        else:
            ordered_models = sorted(model_agg["Model"].unique())
            color_map = {m: CATEGORICAL[i % len(CATEGORICAL)] for i, m in enumerate(ordered_models)}
            fig = px.pie(
                model_agg, names="Model", values="Total Tokens", hole=0.45,
                color="Model", color_discrete_map=color_map,
            )
            fig.update_traces(textinfo="percent+label", textposition="inside")
            fig.update_layout(**PLOTLY_LAYOUT, height=320)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Product Breakdown")
        product_agg = user_df.groupby("Product", as_index=False)["Total Tokens"].sum().sort_values(
            "Total Tokens", ascending=False
        )
        if product_agg.empty:
            st.info("No product usage data available.")
        else:
            ordered_products = sorted(product_agg["Product"].unique())
            color_map = {p: CATEGORICAL[i % len(CATEGORICAL)] for i, p in enumerate(ordered_products)}
            fig = px.pie(
                product_agg, names="Product", values="Total Tokens", hole=0.45,
                color="Product", color_discrete_map=color_map,
            )
            fig.update_traces(textinfo="percent+label", textposition="inside")
            fig.update_layout(**PLOTLY_LAYOUT, height=320)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader(f"Usage Trend — {selected_user}")
    granularity = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True, index=2, key="user_gran")
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "MS"}
    trend = user_df.set_index("Date").resample(freq_map[granularity])["Total Tokens"].sum().reset_index()
    if trend.empty:
        st.info("No usage data available.")
    else:
        fig = go.Figure(
            go.Scatter(
                x=trend["Date"], y=trend["Total Tokens"], mode="lines+markers",
                line=dict(color=BLUE, shape="spline", width=2), marker=dict(size=8, color=BLUE),
            )
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=340, xaxis_title="", yaxis_title="Tokens")
        fig.update_xaxes(gridcolor=COLOR_GRID)
        fig.update_yaxes(gridcolor=COLOR_GRID)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Raw Records")
    detail_cols = ["Date", "Product", "Model(s)", "Requests", "Total Tokens", "Net Spend (USD)", "Period", "Source File"]
    display_df = user_df[detail_cols].sort_values("Date", ascending=False).copy()
    display_df["Total Tokens"] = display_df["Total Tokens"].apply(format_tokens)
    display_df["Net Spend (USD)"] = display_df["Net Spend (USD)"].apply(format_currency)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv_bytes = user_df[detail_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Export to CSV",
        data=csv_bytes,
        file_name=f"{selected_user.replace('@', '_at_')}_usage_export.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

if filtered.empty and not (
    isinstance(date_range, tuple) and len(date_range) == 2 and date_range[0] > date_range[1]
):
    st.title("Claude Usage Dashboard — IT Asset Management")
    st.warning("No data found for the selected period.")
elif st.session_state.page == "Overview Dashboard":
    render_overview(filtered)
else:
    render_user_detail(filtered)
