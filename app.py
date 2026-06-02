"""
European Energy Market Price Spread Dashboard
Compares hourly Day-Ahead vs Imbalance prices for FR, BE, IT, RO, NL
Data source: ENTSO-E Transparency Platform (free API key required)
"""

import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from entsoe import EntsoePandasClient

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EU Imbalance vs Day-Ahead Prices",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Country configuration ────────────────────────────────────────────────────
START_DEFAULT = date(2026, 1, 1)

COUNTRIES: dict[str, dict] = {
    "France": {
        "da_code":  "10YFR-RTE------C",
        "imb_code": "10YFR-RTE------C",
        "color":    "#4C8ED9",   # blue
        "flag":     "🇫🇷",
    },
    "Belgium": {
        "da_code":  "10YBE----------2",
        "imb_code": "10YBE----------2",
        "color":    "#F4B41A",   # golden yellow
        "flag":     "🇧🇪",
    },
    "Italy": {
        # Day-ahead: IT-North bidding zone (largest zone, proxy for national)
        # Imbalance: Terna control area (national)
        "da_code":  "10Y1001A1001A73I",
        "imb_code": "10YIT-GRTN-----B",
        "color":    "#3DBE6C",   # green
        "flag":     "🇮🇹",
        "note":     "Day-ahead uses IT-North zone (proxy for national price)",
    },
    "Romania": {
        "da_code":  "10YRO-TEL------P",
        "imb_code": "10YRO-TEL------P",
        "color":    "#E05C5C",   # red
        "flag":     "🇷🇴",
    },
    "Netherlands": {
        "da_code":  "10YNL----------L",
        "imb_code": "10YNL----------L",
        "color":    "#FF8C42",   # orange
        "flag":     "🇳🇱",
    },
}

RESAMPLE_MAP = {"Hourly": "h", "Daily avg": "D", "Weekly avg": "W"}


# ── Data fetching (cached per API key + code + date range) ───────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_day_ahead(api_key: str, code: str, start_str: str, end_str: str) -> pd.Series | None:
    client = EntsoePandasClient(api_key=api_key)
    start = pd.Timestamp(start_str, tz="UTC")
    end   = pd.Timestamp(end_str,   tz="UTC")
    try:
        ts = client.query_day_ahead_prices(code, start=start, end=end)
        return ts.resample("h").mean()
    except Exception as exc:
        return exc


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_imbalance(api_key: str, code: str, start_str: str, end_str: str) -> pd.Series | None:
    client = EntsoePandasClient(api_key=api_key)
    start = pd.Timestamp(start_str, tz="UTC")
    end   = pd.Timestamp(end_str,   tz="UTC")
    try:
        result = client.query_imbalance_prices(code, start=start, end=end)
        if isinstance(result, pd.DataFrame):
            # ENTSO-E returns 'Long' (surplus → downward regulation price)
            # and 'Short' (deficit → upward regulation price).
            # Average the two as a single net imbalance reference price.
            numeric_cols = result.select_dtypes("number")
            series = numeric_cols.mean(axis=1)
        elif isinstance(result, pd.Series):
            series = result
        else:
            return None
        return series.resample("h").mean()
    except Exception as exc:
        return exc


def load_country_data(
    api_key: str,
    countries: list[str],
    start_str: str,
    end_str: str,
) -> dict[str, dict[str, pd.Series | Exception | None]]:
    data: dict[str, dict] = {}
    total = len(countries) * 2
    bar   = st.progress(0, text="Loading…")

    for i, name in enumerate(countries):
        cfg = COUNTRIES[name]
        bar.progress(i * 2 / total, text=f"{cfg['flag']} {name} — day-ahead…")
        da = _fetch_day_ahead(api_key, cfg["da_code"], start_str, end_str)

        bar.progress((i * 2 + 1) / total, text=f"{cfg['flag']} {name} — imbalance…")
        imb = _fetch_imbalance(api_key, cfg["imb_code"], start_str, end_str)

        data[name] = {"da": da, "imb": imb}

    bar.empty()
    return data


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ Energy Spreads")

    api_key = st.text_input(
        "ENTSO-E API Key",
        type="password",
        value=os.environ.get("ENTSOE_API_KEY", ""),
        help="Free registration at transparency.entsoe.eu → My Account → Web API",
    )

    st.divider()
    st.subheader("Date range")
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("From", value=START_DEFAULT, min_value=START_DEFAULT)
    with c2:
        end_date = st.date_input("To", value=date.today(), min_value=START_DEFAULT)

    st.divider()
    st.subheader("Countries")
    selected_countries = {
        name: st.checkbox(
            f"{cfg['flag']} {name}",
            value=True,
            key=f"chk_{name}",
        )
        for name, cfg in COUNTRIES.items()
    }

    st.divider()
    st.subheader("Series")
    show_da     = st.checkbox("Day-Ahead",        value=False, key="show_da")
    show_imb    = st.checkbox("Imbalance",         value=False, key="show_imb")
    show_spread = st.checkbox("Spread (Imb − DA)", value=True,  key="show_spread")

    st.divider()
    granularity = st.selectbox("Granularity", list(RESAMPLE_MAP), index=1)

    if st.button("🔄 Clear cache & reload"):
        st.cache_data.clear()
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("EU Imbalance vs Day-Ahead Price Comparison")
st.caption("Source: ENTSO-E Transparency Platform · Prices in €/MWh · Since 1 Jan 2026")

# Guard: API key
if not api_key:
    st.info(
        "**No API key provided.** Enter your ENTSO-E key in the sidebar.  \n"
        "Get one for free at [transparency.entsoe.eu](https://transparency.entsoe.eu) "
        "→ My Account → Web API Security Token."
    )
    st.stop()

# Guard: selections
active_countries = [n for n, sel in selected_countries.items() if sel]
if not active_countries:
    st.warning("Select at least one country in the sidebar.")
    st.stop()
if not (show_da or show_imb or show_spread):
    st.warning("Select at least one series (Day-Ahead, Imbalance, or Spread).")
    st.stop()

# Date strings for cache key
start_str = pd.Timestamp(start_date).isoformat()
end_str   = pd.Timestamp(end_date + pd.Timedelta(days=1)).isoformat()
resample  = RESAMPLE_MAP[granularity]

# Fetch
data = load_country_data(api_key, active_countries, start_str, end_str)

# ── Build chart ───────────────────────────────────────────────────────────────
fig    = go.Figure()
errors = []

for name in active_countries:
    cfg   = COUNTRIES[name]
    color = cfg["color"]
    raw_da, raw_imb = data[name]["da"], data[name]["imb"]

    # Normalise results (Exception → None + error message)
    da = imb = None
    if isinstance(raw_da, Exception):
        errors.append(f"**{name}** day-ahead: {raw_da}")
    elif isinstance(raw_da, pd.Series) and not raw_da.empty:
        da = raw_da.resample(resample).mean()

    if isinstance(raw_imb, Exception):
        errors.append(f"**{name}** imbalance: {raw_imb}")
    elif isinstance(raw_imb, pd.Series) and not raw_imb.empty:
        imb = raw_imb.resample(resample).mean()

    label = f"{cfg['flag']} {name}"

    if show_da:
        if da is not None:
            fig.add_trace(go.Scatter(
                x=da.index, y=da.values,
                name=f"{label} · DA",
                legendgroup=name,
                line=dict(color=color, dash="solid", width=1.5),
                hovertemplate="%{y:.1f} €/MWh<extra>" + f"{name} Day-Ahead</extra>",
            ))
        else:
            errors.append(f"**{name}**: day-ahead data unavailable for selected range")

    if show_imb:
        if imb is not None:
            fig.add_trace(go.Scatter(
                x=imb.index, y=imb.values,
                name=f"{label} · Imb",
                legendgroup=name,
                line=dict(color=color, dash="dash", width=1.5),
                hovertemplate="%{y:.1f} €/MWh<extra>" + f"{name} Imbalance</extra>",
            ))
        else:
            errors.append(f"**{name}**: imbalance data unavailable for selected range")

    if show_spread:
        if da is not None and imb is not None:
            # Align on common timestamps then compute spread
            combined = pd.DataFrame({"da": da, "imb": imb}).dropna()
            spread   = combined["imb"] - combined["da"]
            fig.add_trace(go.Scatter(
                x=spread.index, y=spread.values,
                name=f"{label} · Spread",
                legendgroup=name,
                line=dict(color=color, dash="dot", width=2),
                fill="tozeroy",
                fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)" if color.startswith("#") else None,
                hovertemplate="%{y:.1f} €/MWh<extra>" + f"{name} Spread</extra>",
            ))
        else:
            missing = []
            if da  is None: missing.append("day-ahead")
            if imb is None: missing.append("imbalance")
            errors.append(f"**{name}** spread: missing {' & '.join(missing)}")

# Zero line + layout
fig.add_hline(y=0, line_dash="dot", line_color="rgba(180,180,180,0.5)", line_width=1)

legend_items = []
if show_da:     legend_items.append("solid = Day-Ahead")
if show_imb:    legend_items.append("dashed = Imbalance")
if show_spread: legend_items.append("dotted = Spread")

fig.update_layout(
    template="plotly_dark",
    hovermode="x unified",
    height=620,
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.01,
        xanchor="left",   x=0,
        font=dict(size=11),
    ),
    yaxis_title="€/MWh",
    xaxis_title="",
    margin=dict(l=60, r=20, t=90, b=40),
    annotations=[dict(
        text="  ".join(legend_items),
        xref="paper", yref="paper",
        x=0, y=1.09,
        showarrow=False,
        font=dict(size=10, color="rgba(200,200,200,0.7)"),
    )] if legend_items else [],
)

st.plotly_chart(fig, use_container_width=True)

# ── Error panel ───────────────────────────────────────────────────────────────
if errors:
    with st.expander("⚠️ Data issues", expanded=True):
        for e in errors:
            st.warning(e)

# ── Data notes ────────────────────────────────────────────────────────────────
notes = [cfg.get("note") for cfg in COUNTRIES.values() if cfg.get("note") and
         any(n == name for name in active_countries for cfg2 in [COUNTRIES[n]] if cfg2.get("note") == cfg.get("note"))]
if "Italy" in active_countries and COUNTRIES["Italy"].get("note"):
    st.caption(f"🇮🇹 Italy: {COUNTRIES['Italy']['note']}")
st.caption(
    "Imbalance price = average of Long (downward regulation) and Short (upward regulation) prices "
    "as reported by each TSO to ENTSO-E. Spread = Imbalance − Day-Ahead."
)

# ── Statistics table ──────────────────────────────────────────────────────────
if show_spread and any(
    isinstance(data[n]["da"], pd.Series) and isinstance(data[n]["imb"], pd.Series)
    for n in active_countries
):
    st.divider()
    st.subheader("Spread statistics — full period (€/MWh, hourly)")

    rows = []
    for name in active_countries:
        raw_da, raw_imb = data[name]["da"], data[name]["imb"]
        if isinstance(raw_da, pd.Series) and isinstance(raw_imb, pd.Series):
            combined = pd.DataFrame({"da": raw_da, "imb": raw_imb}).dropna()
            if combined.empty:
                continue
            spread = combined["imb"] - combined["da"]
            rows.append({
                "Country":    f"{COUNTRIES[name]['flag']} {name}",
                "Mean":       round(spread.mean(), 1),
                "Median":     round(spread.median(), 1),
                "Std dev":    round(spread.std(), 1),
                "Min":        round(spread.min(), 1),
                "Max":        round(spread.max(), 1),
                "% positive": f"{(spread > 0).mean() * 100:.0f}%",
                "Hours":      len(spread),
            })

    if rows:
        st.dataframe(
            pd.DataFrame(rows).set_index("Country"),
            use_container_width=True,
        )
