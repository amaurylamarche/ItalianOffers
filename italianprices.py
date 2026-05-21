"""
Confronto Offerte Energia Elettrica - Mercato Libero Italiano
Compares fixed-price, monoraria, renewable residential offers from 9 major suppliers.
Data source: ARERA Portale Offerte (XML + CSV)
"""

import glob
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Confronto Offerte Luce",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
DATA_DIR = Path(r"C:\Users\HIA415\Sandbox\energy price")
NS = {"au": "http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01"}

COMPETITORS = {
    "01771990445": "Octopus",
    "06655971007": "Enel",
    "10879560968": "NeN",
    "03429130234": "E.ON",
    "06289781004": "ENGIE",
    "01812630224": "Dolomiti",
    "08526440154": "Edison",
    "02221101203": "Hera",
    "01178580997": "Iren",
}

COLORS = {
    "Octopus": "#EF4123",
    "Enel":    "#00B04B",
    "NeN":     "#F7A501",
    "E.ON":    "#E2001A",
    "ENGIE":   "#009FE3",
    "Dolomiti":"#005B99",
    "Edison":  "#E8792B",
    "Hera":    "#00A550",
    "Iren":    "#5B2D8E",
}

# F1/F2/F3 typical consumption weights for trioraria → effective monoraria price
F_WEIGHTS = {"01": 0.44, "02": 0.21, "03": 0.35}

# ── Data loading ──────────────────────────────────────────────────────────────
from datetime import date as _date, datetime as _dt

def _available_dates() -> list[_date]:
    """Return sorted list of dates for which an XML offer file exists."""
    dates = []
    for f in DATA_DIR.glob("PO_Offerte_E_MLIBERO_*.xml"):
        m = re.search(r"(\d{8})", f.stem)
        if m:
            try:
                dates.append(_dt.strptime(m.group(1), "%Y%m%d").date())
            except ValueError:
                pass
    return sorted(set(dates))


def _file_for_date(pattern_prefix: str, extension: str, target: _date) -> Path | None:
    """Find the file matching the target date, or the closest earlier one."""
    target_str = target.strftime("%Y%m%d")
    # Try exact match first (handles filenames with spaces like "... (1).xml")
    candidates = sorted(DATA_DIR.glob(f"{pattern_prefix}*{target_str}*{extension}"))
    if candidates:
        return candidates[0]
    # Fall back to latest file on or before the target date
    all_files = sorted(DATA_DIR.glob(f"{pattern_prefix}*.{extension.lstrip('.')}"))
    before = [f for f in all_files if re.search(r"\d{8}", f.stem) and
              re.search(r"\d{8}", f.stem).group() <= target_str]
    return before[-1] if before else (all_files[-1] if all_files else None)


@st.cache_data(show_spinner="Caricamento dati ARERA…")
def load_params(target_date: _date) -> dict:
    csv_path = _file_for_date("PO_Parametri_Mercato_Libero_E_", ".csv", target_date)
    if csv_path is None:
        return {}
    df = pd.read_csv(csv_path)
    return dict(zip(df["nome_parametro"], df["valore"]))


@st.cache_data(show_spinner="Parsing offerte…")
def load_offers(target_date: _date) -> list[dict]:
    xml_path = _file_for_date("PO_Offerte_E_MLIBERO_", ".xml", target_date)
    if xml_path is None:
        return []

    tree = ET.parse(xml_path)
    root = tree.getroot()
    offers = []

    for offerta in root.findall("au:offerta", NS):
        piva = offerta.findtext("au:IdentificativiOfferta/au:PIVA_UTENTE", namespaces=NS)
        if piva not in COMPETITORS:
            continue

        tipo_offerta  = offerta.findtext("au:DettaglioOfferta/au:TIPO_OFFERTA",  namespaces=NS)
        tipo_cliente  = offerta.findtext("au:DettaglioOfferta/au:TIPO_CLIENTE",  namespaces=NS)
        fasce         = offerta.findtext("au:TipoPrezzo/au:TIPOLOGIA_FASCE",     namespaces=NS)
        limitante     = offerta.findtext("au:CondizioniContrattuali/au:LIMITANTE", namespaces=NS) or "02"
        disp_type     = offerta.findtext("au:Dispacciamento/au:TIPO_DISPACCIAMENTO", namespaces=NS) or ""
        nome          = offerta.findtext("au:DettaglioOfferta/au:NOME_OFFERTA",  namespaces=NS) or ""
        desc          = offerta.findtext("au:DettaglioOfferta/au:DESCRIZIONE",   namespaces=NS) or ""
        url_offerta   = offerta.findtext("au:DettaglioOfferta/au:Contatti/au:URL_OFFERTA", namespaces=NS) or ""
        durata        = offerta.findtext("au:DettaglioOfferta/au:DURATA",        namespaces=NS) or "-1"

        # Filters: fixed price (01) + domestic (01)
        if tipo_offerta != "01" or tipo_cliente != "01":
            continue
        # Monoraria = TIPOLOGIA_FASCE 01
        if fasce not in ("01", "03"):
            continue

        # Renewable: explicit renewable-energy keywords only (avoid false positives)
        desc_lower = desc.lower()
        name_lower = nome.lower()
        renewable = (
            "rinnovab" in desc_lower           # rinnovabile / rinnovabili
            or "garanzie di origine" in desc_lower
            or "garanzia di origine" in desc_lower
            or "certificati go" in desc_lower  # certificati GO (Garanzie Origine)
            or "verde" in name_lower           # e.g. LuceVerde
            or "green" in name_lower
        )

        # Parse ComponenteImpresa
        energy_price = 0.0   # €/kWh (seller's energy component)
        fixed_annual = 0.0   # €/year (seller's fixed fee)
        is_mono = True       # all fascia prices equal?
        fixed_includes_dispbt = False  # True if seller bundled DISPbt Fisso in fixed fee

        for comp in offerta.findall("au:ComponenteImpresa", NS):
            tipologia = comp.findtext("au:TIPOLOGIA", namespaces=NS)
            if tipologia != "01":  # skip discounts
                continue
            macroarea  = comp.findtext("au:MACROAREA",    namespaces=NS) or ""
            comp_nome  = (comp.findtext("au:NOME",        namespaces=NS) or "").lower()
            comp_desc  = (comp.findtext("au:DESCRIZIONE", namespaces=NS) or "").lower()
            intervals  = comp.findall("au:IntervalloPrezzi", NS)

            if macroarea in ("04", "06"):  # energy variable component
                prices_by_fascia = {}
                for iv in intervals:
                    fascia = iv.findtext("au:FASCIA_COMPONENTE", namespaces=NS) or "00"
                    prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                    unita  = iv.findtext("au:UNITA_MISURA",  namespaces=NS) or "03"
                    if unita == "03":  # €/kWh
                        prices_by_fascia[fascia] = prezzo

                if "04" in prices_by_fascia:          # explicit F0 (monoraria)
                    energy_price = prices_by_fascia["04"]
                elif prices_by_fascia:
                    vals = list(prices_by_fascia.values())
                    if len(set(round(v, 6) for v in vals)) == 1:
                        energy_price = vals[0]         # all equal → true monoraria
                    else:
                        is_mono = False
                        # Weighted average F1/F2/F3
                        energy_price = sum(
                            prices_by_fascia.get(f, 0) * w
                            for f, w in F_WEIGHTS.items()
                        )

            elif macroarea == "01":  # fixed annual fee
                for iv in intervals:
                    prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                    unita  = iv.findtext("au:UNITA_MISURA",  namespaces=NS) or "01"
                    if unita == "01":    # €/year
                        fixed_annual += prezzo
                    elif unita == "02":  # €/month → annualise
                        fixed_annual += prezzo * 12
                # Detect if seller explicitly bundled DISPbt Fisso in this fixed component
                if "dispbt" in comp_nome or "dispbt" in comp_desc or "dispacciament" in comp_desc:
                    fixed_includes_dispbt = True

        if energy_price == 0.0:
            continue  # skip incomplete offers

        offers.append({
            "competitor": COMPETITORS[piva],
            "nome": nome,
            "desc": desc,
            "url": url_offerta,
            "durata": int(durata) if durata.lstrip("-").isdigit() else -1,
            "energy_price": energy_price,
            "fixed_annual": fixed_annual,
            "fixed_includes_dispbt": fixed_includes_dispbt,
            "fasce": fasce,
            "is_mono": is_mono,
            "renewable": renewable,
            "limitante": limitante,
            "disp_type": disp_type,
        })

    return offers


# ── Bill calculation ──────────────────────────────────────────────────────────
def calculate_bill(offer: dict, consumption: float, power: float, params: dict) -> dict:
    """
    Annual bill estimate following ARERA methodology.
    Regulated charges are identical for all suppliers (fair comparison).
    """
    p = params

    # ── Seller's spesa materia energia ────────────────────────────────────────
    energy_cost   = offer["energy_price"] * consumption
    fixed_cost    = offer["fixed_annual"]

    # CdispD variable component (regulatory, always added)
    cdispd_var    = float(p.get("cdispd", 0.016988)) * consumption

    # DISPbt fixed component: add only if seller has NOT already bundled it in their fixed fee.
    # Sellers like E.ON explicitly include "DISPbt Fisso" in their quoted fixed fee;
    # others (Octopus, NeN, ENGIE…) declare only their commercial fee → we must add DISPbt.
    if not offer.get("fixed_includes_dispbt", False):
        dispbt_fixed = float(p.get("dispbt_d", 1.2311)) * power * 12
    else:
        dispbt_fixed = 0.0

    seller_total  = energy_cost + fixed_cost + cdispd_var + dispbt_fixed

    # ── Regulated: trasporto e misura ─────────────────────────────────────────
    sigma1 = float(p.get("sigma1",  23.04))    # €/kW/year  (distribuzione)
    sigma2 = float(p.get("sigma2",  23.52))    # €/year     (trasmissione fissa)
    sigma3 = float(p.get("sigma3",  0.0119))   # €/kWh      (misura var)
    tras   = float(p.get("tras",    0.0119))   # €/kWh      (trasmissione var)
    mis    = float(p.get("mis",     21.847))   # €/year     (misura fissa)

    transport = (sigma3 + tras) * consumption + sigma1 * power + sigma2 + mis

    # ── Regulated: oneri di sistema ──────────────────────────────────────────
    asos   = float(p.get("asos_dr",  0.028657))
    arim   = float(p.get("arim_dr",  0.001638))
    uc3    = float(p.get("uc3",      0.002760))
    uc6p   = float(p.get("uc6p_d",   0.000070))
    uc6s   = float(p.get("uc6s_d",   0.1988))   # €/kW/year
    cpstgd = float(p.get("cpstgd",   0.000560))
    csed   = float(p.get("csed",     0.000560))
    rst    = float(p.get("rst",      0.000572))

    system = (asos + arim + uc3 + uc6p + cpstgd + csed + rst) * consumption + uc6s * power

    # ── Accisa ────────────────────────────────────────────────────────────────
    if power <= 3.0:
        # Residente ≤3 kW: exempt for first 150 kWh/month (1800 kWh/year)
        taxable = max(0.0, consumption - 1800.0)
        accisa = taxable * float(p.get("acc_c_r_l", 0.0227))
    else:
        accisa = consumption * float(p.get("acc_c_r_h", 0.0227))

    subtotal = seller_total + transport + system + accisa

    # ── IVA 10% domestic ─────────────────────────────────────────────────────
    iva_rate = float(p.get("iva_c", 0.10))
    iva      = subtotal * iva_rate
    total    = subtotal + iva

    return {
        "total":         total,
        # Net (pre-IVA) breakdown — sum of all + iva = total
        "energy_net":    energy_cost,
        "fixed_net":     fixed_cost,
        "dispbt_net":    dispbt_fixed,   # 0 if already in fixed_cost
        "cdispd_net":    cdispd_var,
        "transport_net": transport,
        "system_net":    system,
        "accisa":        accisa,
        "iva":           iva,
    }


# ── Price history (all dates) ─────────────────────────────────────────────────
@st.cache_data(show_spinner="Caricamento storico prezzi…")
def load_price_history() -> pd.DataFrame:
    """Parse all available XML files and return one row per (date, competitor, offer)."""
    records = []
    for xml_path in sorted(DATA_DIR.glob("PO_Offerte_E_MLIBERO_*.xml")):
        m = re.search(r"(\d{8})", xml_path.stem)
        if not m:
            continue
        try:
            dt = _dt.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            continue

        for offerta in root.findall("au:offerta", NS):
            piva = offerta.findtext("au:IdentificativiOfferta/au:PIVA_UTENTE", namespaces=NS)
            if piva not in COMPETITORS:
                continue
            tipo_offerta = offerta.findtext("au:DettaglioOfferta/au:TIPO_OFFERTA", namespaces=NS)
            tipo_cliente = offerta.findtext("au:DettaglioOfferta/au:TIPO_CLIENTE", namespaces=NS)
            fasce        = offerta.findtext("au:TipoPrezzo/au:TIPOLOGIA_FASCE", namespaces=NS)
            limitante    = offerta.findtext("au:CondizioniContrattuali/au:LIMITANTE", namespaces=NS) or "02"
            nome         = offerta.findtext("au:DettaglioOfferta/au:NOME_OFFERTA", namespaces=NS) or ""
            desc         = offerta.findtext("au:DettaglioOfferta/au:DESCRIZIONE", namespaces=NS) or ""

            if tipo_offerta != "01" or tipo_cliente != "01":
                continue
            if fasce not in ("01", "03"):
                continue

            desc_lower = desc.lower()
            name_lower = nome.lower()
            renewable = (
                "rinnovab" in desc_lower
                or "garanzie di origine" in desc_lower
                or "garanzia di origine" in desc_lower
                or "certificati go" in desc_lower
                or "verde" in name_lower
                or "green" in name_lower
            )

            energy_price = 0.0
            fixed_annual = 0.0
            fixed_includes_dispbt = False

            for comp in offerta.findall("au:ComponenteImpresa", NS):
                if comp.findtext("au:TIPOLOGIA", namespaces=NS) != "01":
                    continue
                macroarea = comp.findtext("au:MACROAREA", namespaces=NS) or ""
                comp_nome = (comp.findtext("au:NOME", namespaces=NS) or "").lower()
                comp_desc = (comp.findtext("au:DESCRIZIONE", namespaces=NS) or "").lower()
                intervals = comp.findall("au:IntervalloPrezzi", NS)

                if macroarea in ("04", "06"):
                    pfas = {}
                    for iv in intervals:
                        fascia = iv.findtext("au:FASCIA_COMPONENTE", namespaces=NS) or "00"
                        prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                        unita  = iv.findtext("au:UNITA_MISURA", namespaces=NS) or "03"
                        if unita == "03":
                            pfas[fascia] = prezzo
                    if "04" in pfas:
                        energy_price = pfas["04"]
                    elif pfas:
                        vals = list(pfas.values())
                        if len(set(round(v, 6) for v in vals)) == 1:
                            energy_price = vals[0]
                        else:
                            energy_price = sum(pfas.get(f, 0) * w for f, w in F_WEIGHTS.items())

                elif macroarea == "01":
                    for iv in intervals:
                        prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                        unita  = iv.findtext("au:UNITA_MISURA", namespaces=NS) or "01"
                        if unita == "01":
                            fixed_annual += prezzo
                        elif unita == "02":
                            fixed_annual += prezzo * 12
                    if "dispbt" in comp_nome or "dispbt" in comp_desc or "dispacciament" in comp_desc:
                        fixed_includes_dispbt = True

            if energy_price == 0.0:
                continue

            records.append({
                "date":                 dt,
                "competitor":           COMPETITORS[piva],
                "nome":                 nome,
                "energy_price":         energy_price,
                "fixed_annual":         fixed_annual,
                "fixed_includes_dispbt": fixed_includes_dispbt,
                "renewable":            renewable,
                "limitante":            limitante,
                "fasce":                fasce,
            })

    return pd.DataFrame(records) if records else pd.DataFrame()


# ── Streamlit UI ──────────────────────────────────────────────────────────────
st.title("⚡ Confronto Offerte Energia Elettrica")
st.caption("Offerte a prezzo fisso · Monoraria · Mercato libero italiano — fonte: ARERA Portale Offerte")

# ── Sidebar ───────────────────────────────────────────────────────────────────
all_dates = _available_dates()

with st.sidebar:
    st.header("Data offerte")
    selected_date = st.selectbox(
        "Seleziona data",
        options=all_dates,
        index=len(all_dates) - 1,           # default: latest available date
        format_func=lambda d: d.strftime("%d %B %Y"),
    )

    st.divider()
    st.header("Parametri di consumo")

    consumption = st.slider(
        "Consumo annuale (kWh)",
        min_value=500,
        max_value=5000,
        value=2000,
        step=100,
        help="Consumo domestico tipico: 1000–3000 kWh/anno",
    )

    power = st.radio(
        "Potenza contrattuale (kW)",
        options=[3, 6, 9],
        index=0,
        horizontal=True,
    )

    st.divider()
    st.header("Filtri")

    renewable_filter = st.toggle("Solo offerte rinnovabili ♻", value=True)
    show_limited = st.toggle("Includi offerte limitate", value=False,
                              help="Offerte con condizioni di accesso restrittive")

    st.divider()
    xml_used = _file_for_date("PO_Offerte_E_MLIBERO_", ".xml", selected_date)
    st.caption(f"File: {xml_used.name if xml_used else 'N/A'}")

# Load data for the selected date
params = load_params(selected_date)
all_offers = load_offers(selected_date)

if not all_offers:
    st.error("Nessuna offerta trovata. Verificare i file nella cartella 'energy price'.")
    st.stop()

# ── Filter offers ─────────────────────────────────────────────────────────────
filtered = all_offers.copy()

if renewable_filter:
    renewable_offers = [o for o in filtered if o["renewable"]]
    # For competitors with no renewable offer, fall back to their best offer
    covered = {o["competitor"] for o in renewable_offers}
    fallback = [
        o for o in filtered
        if o["competitor"] not in covered
    ]
    filtered = renewable_offers + fallback

if not show_limited:
    # Prefer non-limited; keep limited only if that competitor has no other choice
    non_limited = [o for o in filtered if o["limitante"] != "01"]
    covered_nl = {o["competitor"] for o in non_limited}
    limited_fallback = [
        o for o in filtered
        if o["limitante"] == "01" and o["competitor"] not in covered_nl
    ]
    filtered = non_limited + limited_fallback

# ── Compute bills ─────────────────────────────────────────────────────────────
rows = []
for offer in filtered:
    bill = calculate_bill(offer, float(consumption), float(power), params)
    rows.append({**offer, **bill})

df = pd.DataFrame(rows)
if df.empty:
    st.warning("Nessuna offerta corrisponde ai filtri selezionati.")
    st.stop()

# Best (cheapest) offer per competitor
df_best = (
    df.sort_values("total")
    .groupby("competitor", as_index=False)
    .first()
    .sort_values("total")
)

# ── KPI cards ─────────────────────────────────────────────────────────────────
st.subheader(f"Bolletta annua stimata — {consumption:,} kWh/anno · {power} kW")

cols = st.columns(len(df_best))
for col, (_, row) in zip(cols, df_best.iterrows()):
    with col:
        color = COLORS.get(row["competitor"], "#888")
        renbadge = "♻" if row["renewable"] else "⚠️"
        lim_badge = " ★" if row["limitante"] == "01" else ""
        st.markdown(
            f"""
            <div style="border-left:4px solid {color};padding:8px 12px;border-radius:4px;background:#fafafa">
                <div style="font-size:0.8rem;color:#666;font-weight:600">{row['competitor']}</div>
                <div style="font-size:1.6rem;font-weight:700;color:{color}">€{row['total']:.0f}</div>
                <div style="font-size:0.7rem;color:#888">{renbadge} {row['nome'][:32]}{lim_badge}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

# ── Ranking bar chart ─────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Ranking", "Dettaglio tutte le offerte", "Evoluzione Prezzi"])

with tab1:
    fig = go.Figure()

    breakdown_components = [
        ("energy_net",    "Spesa energia",          "#4C9BE8"),
        ("fixed_net",     "Quota fissa commerc.",   "#F4A261"),
        ("dispbt_net",    "DISPbt fisso",           "#E76F51"),
        ("cdispd_net",    "CdispD variabile",       "#D62828"),
        ("transport_net", "Trasporto",              "#2A9D8F"),
        ("system_net",    "Oneri sistema",          "#E9C46A"),
        ("accisa",        "Accisa",                 "#C9ADA1"),
        ("iva",           "IVA 10%",                "#D0D0D0"),
    ]

    for comp_key, comp_label, comp_color in breakdown_components:
        fig.add_trace(
            go.Bar(
                name=comp_label,
                x=df_best["competitor"],
                y=df_best[comp_key],
                marker_color=comp_color,
                text=[f"€{v:.0f}" if v > 20 else "" for v in df_best[comp_key]],
                textposition="inside",
                textfont=dict(size=11, color="white"),
            )
        )

    # Overlay competitor color bar top annotation
    for _, row in df_best.iterrows():
        color = COLORS.get(row["competitor"], "#888")

    fig.update_layout(
        barmode="stack",
        title=dict(text="Bolletta annua stimata (IVA inclusa)", font_size=15),
        yaxis_title="€ / anno",
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        height=430,
        margin=dict(t=80, b=20),
    )
    fig.update_yaxes(gridcolor="#EEE", tickprefix="€")

    st.plotly_chart(fig, width="stretch")

    # Summary table
    display_df = df_best[
        ["competitor", "nome", "energy_price", "fixed_annual", "total", "renewable", "limitante", "durata"]
    ].copy()
    display_df["energy_price"] = display_df["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
    display_df["fixed_annual"]  = display_df["fixed_annual"].map(lambda x: f"€{x:.0f}/anno")
    display_df["total"]         = display_df["total"].map(lambda x: f"€{x:.0f}")
    display_df["renewable"]     = display_df["renewable"].map(lambda x: "♻ Sì" if x else "❌ No")
    display_df["limitante"]     = display_df["limitante"].map(lambda x: "★ Limitata" if x == "01" else "✓ Aperta")
    display_df["durata"]        = display_df["durata"].map(lambda x: f"{x} mesi" if x > 0 else "Indeterminato")

    display_df.columns = [
        "Fornitore", "Offerta", "Prezzo energia", "Quota fissa", "Bolletta annua", "Rinnovabile", "Accesso", "Durata"
    ]
    st.dataframe(display_df.set_index("Fornitore"), width="stretch")

with tab2:
    # All matching offers, ranked
    df_all = df.sort_values("total").copy()
    df_all["label"] = df_all["competitor"] + " · " + df_all["nome"].str[:40]

    fig2 = go.Figure()
    for comp in df_all["competitor"].unique():
        sub = df_all[df_all["competitor"] == comp]
        color = COLORS.get(comp, "#888")
        fig2.add_trace(
            go.Bar(
                name=comp,
                x=sub["label"],
                y=sub["total"],
                marker_color=color,
                text=sub["total"].map(lambda x: f"€{x:.0f}"),
                textposition="outside",
            )
        )

    fig2.update_layout(
        barmode="group",
        title="Tutte le offerte corrispondenti ai filtri",
        yaxis_title="€ / anno",
        xaxis_tickangle=-35,
        showlegend=True,
        height=520,
        plot_bgcolor="white",
        margin=dict(b=160),
    )
    fig2.update_yaxes(gridcolor="#EEE", tickprefix="€")
    st.plotly_chart(fig2, width="stretch")

    # Full table
    df_all_disp = df_all[
        ["competitor", "nome", "energy_price", "fixed_annual", "total", "renewable", "limitante", "durata", "url"]
    ].copy()
    df_all_disp["energy_price"] = df_all_disp["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
    df_all_disp["fixed_annual"]  = df_all_disp["fixed_annual"].map(lambda x: f"€{x:.0f}/anno")
    df_all_disp["total"]         = df_all_disp["total"].map(lambda x: f"€{x:.0f}")
    df_all_disp["renewable"]     = df_all_disp["renewable"].map(lambda x: "♻" if x else "❌")
    df_all_disp["limitante"]     = df_all_disp["limitante"].map(lambda x: "★" if x == "01" else "✓")
    df_all_disp["durata"]        = df_all_disp["durata"].map(lambda x: f"{x}m" if x > 0 else "∞")
    df_all_disp.columns = [
        "Fornitore", "Offerta", "Prezzo energia", "Quota fissa", "Bolletta annua", "Rinn.", "Acc.", "Durata", "Link"
    ]
    st.dataframe(df_all_disp.set_index("Fornitore"), width="stretch")

with tab3:
    st.subheader("Evoluzione del Prezzo Energia nel Tempo")
    st.caption(
        "Prezzo energia (c€/kWh) dell'offerta più conveniente per fornitore, su tutti i file disponibili. "
        "♻ = offerta rinnovabile · ○ = non rinnovabile."
    )

    if all_dates:
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hist_start = st.date_input(
                "Dal",
                value=all_dates[0],
                min_value=all_dates[0],
                max_value=all_dates[-1],
                key="hist_start",
            )
        with col_h2:
            hist_end = st.date_input(
                "Al",
                value=all_dates[-1],
                min_value=all_dates[0],
                max_value=all_dates[-1],
                key="hist_end",
            )

    hist_raw = load_price_history()

    if hist_raw.empty:
        st.info("Nessun dato storico trovato nella cartella 'energy price'.")
    else:
        h = hist_raw.copy()

        # Apply date range filter
        if all_dates:
            h = h[(h["date"] >= hist_start) & (h["date"] <= hist_end)]

        if h.empty:
            st.warning("Nessun dato nel periodo selezionato.")
        else:
            # Apply limitante filter (same as sidebar): if no non-limited offer exists for a
            # (date, competitor), keep the limited one as fallback.
            if not show_limited:
                non_lim = h[h["limitante"] != "01"][["date", "competitor"]].drop_duplicates()
                non_lim["_has_nl"] = True
                h = h.merge(non_lim, on=["date", "competitor"], how="left")
                h = h[(h["limitante"] != "01") | h["_has_nl"].isna()]
                h = h.drop(columns=["_has_nl"])

            # Prefer renewable when available; sort so renewable=True comes first,
            # then ascending energy_price — groupby.first() picks the best renewable offer,
            # or the cheapest non-renewable if no renewable exists for that (date, competitor).
            h_sorted = h.sort_values(
                ["date", "competitor", "renewable", "energy_price"],
                ascending=[True, True, False, True],
            )
            best_hist = h_sorted.groupby(["date", "competitor"], as_index=False).first()

            metric_choice = st.radio(
                "Metrica asse Y",
                ["Prezzo energia (c€/kWh)", "Bolletta stimata (€/anno, parametri sidebar)"],
                horizontal=True,
            )

            fig3 = go.Figure()

            for comp in sorted(COMPETITORS.values()):
                sub = best_hist[best_hist["competitor"] == comp].sort_values("date")
                if sub.empty:
                    continue
                color = COLORS.get(comp, "#888")

                if metric_choice.startswith("Bolletta"):
                    y_vals = []
                    for _, r in sub.iterrows():
                        offer_dict = {
                            "energy_price":          r["energy_price"],
                            "fixed_annual":          r["fixed_annual"],
                            "fixed_includes_dispbt": r["fixed_includes_dispbt"],
                        }
                        b = calculate_bill(offer_dict, float(consumption), float(power), params)
                        y_vals.append(b["total"])
                    y_label = "€/anno (IVA incl.)"
                    y_fmt   = ".0f"
                    y_unit  = "€"
                else:
                    y_vals  = (sub["energy_price"] * 100).tolist()
                    y_label = "c€/kWh"
                    y_fmt   = ".3f"
                    y_unit  = " c€/kWh"

                # Symbol: filled circle = renewable, open circle = non-renewable
                symbols = ["circle" if r else "circle-open" for r in sub["renewable"]]
                names   = sub["nome"].str[:40].tolist()

                fig3.add_trace(go.Scatter(
                    x=sub["date"],
                    y=y_vals,
                    name=comp,
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=7, color=color, symbol=symbols),
                    customdata=list(zip(names, ["♻" if r else "○" for r in sub["renewable"]])),
                    hovertemplate=(
                        "<b>%{x|%d %b %Y}</b><br>"
                        "%{y:" + y_fmt + "}" + y_unit + "<br>"
                        "%{customdata[1]} %{customdata[0]}"
                        "<extra>" + comp + "</extra>"
                    ),
                ))

            fig3.add_hline(y=0, line_color="rgba(0,0,0,0)", line_width=0)
            fig3.update_layout(
                yaxis_title=y_label,
                xaxis_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                height=480,
                plot_bgcolor="white",
                hovermode="x unified",
                margin=dict(t=80, b=20),
            )
            fig3.update_yaxes(gridcolor="#EEE")
            fig3.update_xaxes(gridcolor="#EEE")
            st.plotly_chart(fig3, width="stretch")

            # Small summary table: latest price per company
            latest_date = best_hist["date"].max()
            latest = best_hist[best_hist["date"] == latest_date].copy()
            latest["Prezzo energia"] = latest["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
            latest["Quota fissa"]    = latest["fixed_annual"].map(lambda x: f"€{x:.0f}/anno")
            latest["Rinnovabile"]    = latest["renewable"].map(lambda x: "♻" if x else "○")
            latest["Accesso"]        = latest["limitante"].map(lambda x: "★ Limitata" if x == "01" else "✓ Aperta")
            st.caption(f"Prezzi al {latest_date.strftime('%d %B %Y')}")
            st.dataframe(
                latest[["competitor", "Prezzo energia", "Quota fissa", "Rinnovabile", "Accesso"]]
                .rename(columns={"competitor": "Fornitore"})
                .set_index("Fornitore")
                .sort_values("Prezzo energia"),
                width="stretch",
            )

# ── Footer note ───────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "**Nota metodologica**: La bolletta stimata include spesa materia energia (prezzo offerta + dispacciamento CdispD), "
    "spesa trasporto e gestione contatore, oneri di sistema, accisa ed IVA al 10% (domestico residente). "
    "Per utenze ≤3 kW residenti, l'accisa è esente per i primi 1.800 kWh/anno. "
    "I dati regolati sono tratti dall'ultimo file CSV disponibile (Parametri Mercato Libero). "
    "Offerte marcate ★ hanno condizioni di accesso limitate. Stima non vincolante."
)
