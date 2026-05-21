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
DATA_DIR = Path(__file__).parent / "energy price"
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

# ── Translations ──────────────────────────────────────────────────────────────
TRANSLATIONS = {
    "it": {
        "lang_button":          "🇬🇧 English",
        "app_title":            "⚡ Confronto Offerte Energia Elettrica",
        "app_caption":          "Offerte a prezzo fisso · Monoraria · Mercato libero italiano — fonte: ARERA Portale Offerte",
        "sidebar_date_header":  "Data offerte",
        "sidebar_date_select":  "Seleziona data",
        "sidebar_params_header":"Parametri di consumo",
        "sidebar_kwh_slider":   "Consumo annuale (kWh)",
        "sidebar_kwh_help":     "Consumo domestico tipico: 1000–3000 kWh/anno",
        "sidebar_power_radio":  "Potenza contrattuale (kW)",
        "sidebar_filters":      "Filtri",
        "sidebar_renewable":    "Solo offerte rinnovabili ♻",
        "sidebar_limited":      "Includi offerte limitate",
        "sidebar_limited_help": "Offerte con condizioni di accesso restrittive",
        "err_no_offers":        "Nessuna offerta trovata. Verificare i file nella cartella 'energy price'.",
        "err_no_filter":        "Nessuna offerta corrisponde ai filtri selezionati.",
        "kpi_subheader":        "Bolletta annua stimata — {consumption:,} kWh/anno · {power} kW",
        "tab_ranking":          "Ranking",
        "tab_all":              "Dettaglio tutte le offerte",
        "tab_history":          "Evoluzione Prezzi",
        "comp_energy":          "Spesa energia",
        "comp_fixed":           "Quota fissa commerc.",
        "comp_dispbt":          "DISPbt fisso",
        "comp_cdispd":          "CdispD variabile",
        "comp_transport":       "Trasporto",
        "comp_system":          "Oneri sistema",
        "comp_accisa":          "Accisa",
        "comp_iva":             "IVA 10%",
        "chart1_title":         "Bolletta annua stimata (IVA inclusa)",
        "chart1_yaxis":         "€ / anno",
        "col_supplier":         "Fornitore",
        "col_offer":            "Offerta",
        "col_energy_price":     "Prezzo energia",
        "col_fixed_fee":        "Quota fissa",
        "col_bill":             "Bolletta annua",
        "col_renewable":        "Rinnovabile",
        "col_access":           "Accesso",
        "col_duration":         "Durata",
        "col_rinn":             "Rinn.",
        "col_acc":              "Acc.",
        "col_link":             "Link",
        "renewable_yes":        "♻ Sì",
        "renewable_no":         "❌ No",
        "access_limited":       "★ Limitata",
        "access_open":          "✓ Aperta",
        "duration_months":      "{n} mesi",
        "duration_unlimited":   "Indeterminato",
        "annual_suffix":        "/anno",
        "chart2_title":         "Tutte le offerte corrispondenti ai filtri",
        "hist_subheader":       "Evoluzione del Prezzo Energia nel Tempo",
        "hist_caption":         "Prezzo energia (c€/kWh) dell'offerta più conveniente per fornitore, su tutti i file disponibili. ♻ = offerta rinnovabile · ○ = non rinnovabile.",
        "hist_from":            "Dal",
        "hist_to":              "Al",
        "hist_metric_label":    "Metrica asse Y",
        "hist_metric_price":    "Prezzo energia (c€/kWh)",
        "hist_metric_bill":     "Bolletta stimata (€/anno, parametri sidebar)",
        "hist_ylabel_price":    "c€/kWh",
        "hist_ylabel_bill":     "€/anno (IVA incl.)",
        "hist_no_data":         "Nessun dato storico trovato nella cartella 'energy price'.",
        "hist_no_period":       "Nessun dato nel periodo selezionato.",
        "hist_latest_caption":  "Prezzi al {date}",
        "col_energy_price2":    "Prezzo energia",
        "col_fixed_fee2":       "Quota fissa",
        "col_renewable2":       "Rinnovabile",
        "col_access2":          "Accesso",
        "col_vs_week":          "vs 1 sett.",
        "col_vs_month":         "vs 1 mese",
        "price_up":             "↑",
        "price_down":           "↓",
        "price_flat":           "→",
        "no_ref_data":          "—",
        "footer": (
            "**Nota metodologica**: La bolletta stimata include spesa materia energia "
            "(prezzo offerta + dispacciamento CdispD), spesa trasporto e gestione contatore, "
            "oneri di sistema, accisa ed IVA al 10% (domestico residente). "
            "Per utenze ≤3 kW residenti, l'accisa è esente per i primi 1.800 kWh/anno. "
            "I dati regolati sono tratti dall'ultimo file CSV disponibile (Parametri Mercato Libero). "
            "Offerte marcate ★ hanno condizioni di accesso limitate. Stima non vincolante."
        ),
    },
    "en": {
        "lang_button":          "🇮🇹 Italiano",
        "app_title":            "⚡ Electricity Offer Comparison",
        "app_caption":          "Fixed-price offers · Single-rate · Italian free market — source: ARERA Portale Offerte",
        "sidebar_date_header":  "Offer date",
        "sidebar_date_select":  "Select date",
        "sidebar_params_header":"Consumption parameters",
        "sidebar_kwh_slider":   "Annual consumption (kWh)",
        "sidebar_kwh_help":     "Typical household: 1,000–3,000 kWh/year",
        "sidebar_power_radio":  "Contract power (kW)",
        "sidebar_filters":      "Filters",
        "sidebar_renewable":    "Renewable offers only ♻",
        "sidebar_limited":      "Include restricted offers",
        "sidebar_limited_help": "Offers with restrictive access conditions",
        "err_no_offers":        "No offers found. Check the files in the 'energy price' folder.",
        "err_no_filter":        "No offers match the selected filters.",
        "kpi_subheader":        "Estimated annual bill — {consumption:,} kWh/year · {power} kW",
        "tab_ranking":          "Ranking",
        "tab_all":              "All offer details",
        "tab_history":          "Price History",
        "comp_energy":          "Energy cost",
        "comp_fixed":           "Fixed commercial fee",
        "comp_dispbt":          "DISPbt fixed",
        "comp_cdispd":          "CdispD variable",
        "comp_transport":       "Transport",
        "comp_system":          "System charges",
        "comp_accisa":          "Excise duty",
        "comp_iva":             "VAT 10%",
        "chart1_title":         "Estimated annual bill (VAT included)",
        "chart1_yaxis":         "€ / year",
        "col_supplier":         "Supplier",
        "col_offer":            "Offer",
        "col_energy_price":     "Energy price",
        "col_fixed_fee":        "Fixed fee",
        "col_bill":             "Annual bill",
        "col_renewable":        "Renewable",
        "col_access":           "Access",
        "col_duration":         "Duration",
        "col_rinn":             "Ren.",
        "col_acc":              "Acc.",
        "col_link":             "Link",
        "renewable_yes":        "♻ Yes",
        "renewable_no":         "❌ No",
        "access_limited":       "★ Restricted",
        "access_open":          "✓ Open",
        "duration_months":      "{n} months",
        "duration_unlimited":   "Indefinite",
        "annual_suffix":        "/year",
        "chart2_title":         "All offers matching filters",
        "hist_subheader":       "Energy Price Evolution Over Time",
        "hist_caption":         "Energy price (c€/kWh) of the best offer per supplier, across all available dates. ♻ = renewable · ○ = non-renewable.",
        "hist_from":            "From",
        "hist_to":              "To",
        "hist_metric_label":    "Y-axis metric",
        "hist_metric_price":    "Energy price (c€/kWh)",
        "hist_metric_bill":     "Estimated bill (€/year, sidebar parameters)",
        "hist_ylabel_price":    "c€/kWh",
        "hist_ylabel_bill":     "€/year (VAT incl.)",
        "hist_no_data":         "No historical data found in the 'energy price' folder.",
        "hist_no_period":       "No data in the selected period.",
        "hist_latest_caption":  "Prices as of {date}",
        "col_energy_price2":    "Energy price",
        "col_fixed_fee2":       "Fixed fee",
        "col_renewable2":       "Renewable",
        "col_access2":          "Access",
        "col_vs_week":          "vs 1W",
        "col_vs_month":         "vs 1M",
        "price_up":             "↑",
        "price_down":           "↓",
        "price_flat":           "→",
        "no_ref_data":          "—",
        "footer": (
            "**Methodology**: The estimated bill includes energy costs (offer price + CdispD dispatch), "
            "transport and metering charges, system charges, excise duty and 10% VAT (domestic residential). "
            "For connections ≤3 kW, excise is exempt on the first 1,800 kWh/year. "
            "Regulated components are from the most recent CSV parameter file. "
            "Offers marked ★ have restricted access conditions. Non-binding estimate."
        ),
    },
}


def t(key: str) -> str:
    return TRANSLATIONS[st.session_state.get("lang", "it")][key]


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
    candidates = sorted(DATA_DIR.glob(f"{pattern_prefix}*{target_str}*{extension}"))
    if candidates:
        return candidates[0]
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
        is_mono = True
        fixed_includes_dispbt = False

        for comp in offerta.findall("au:ComponenteImpresa", NS):
            tipologia = comp.findtext("au:TIPOLOGIA", namespaces=NS)
            if tipologia != "01":
                continue
            macroarea  = comp.findtext("au:MACROAREA",    namespaces=NS) or ""
            comp_nome  = (comp.findtext("au:NOME",        namespaces=NS) or "").lower()
            comp_desc  = (comp.findtext("au:DESCRIZIONE", namespaces=NS) or "").lower()
            intervals  = comp.findall("au:IntervalloPrezzi", NS)

            if macroarea in ("04", "06"):
                prices_by_fascia = {}
                for iv in intervals:
                    fascia = iv.findtext("au:FASCIA_COMPONENTE", namespaces=NS) or "00"
                    prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                    unita  = iv.findtext("au:UNITA_MISURA",  namespaces=NS) or "03"
                    if unita == "03":
                        prices_by_fascia[fascia] = prezzo

                if "04" in prices_by_fascia:
                    energy_price = prices_by_fascia["04"]
                elif prices_by_fascia:
                    vals = list(prices_by_fascia.values())
                    if len(set(round(v, 6) for v in vals)) == 1:
                        energy_price = vals[0]
                    else:
                        is_mono = False
                        energy_price = sum(
                            prices_by_fascia.get(f, 0) * w
                            for f, w in F_WEIGHTS.items()
                        )

            elif macroarea == "01":
                for iv in intervals:
                    prezzo = float(iv.findtext("au:PREZZO", namespaces=NS) or 0)
                    unita  = iv.findtext("au:UNITA_MISURA",  namespaces=NS) or "01"
                    if unita == "01":
                        fixed_annual += prezzo
                    elif unita == "02":
                        fixed_annual += prezzo * 12
                if "dispbt" in comp_nome or "dispbt" in comp_desc or "dispacciament" in comp_desc:
                    fixed_includes_dispbt = True

        if energy_price == 0.0:
            continue

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
    p = params

    energy_cost   = offer["energy_price"] * consumption
    fixed_cost    = offer["fixed_annual"]
    cdispd_var    = float(p.get("cdispd", 0.016988)) * consumption

    if not offer.get("fixed_includes_dispbt", False):
        dispbt_fixed = float(p.get("dispbt_d", 1.2311)) * power * 12
    else:
        dispbt_fixed = 0.0

    seller_total  = energy_cost + fixed_cost + cdispd_var + dispbt_fixed

    sigma1 = float(p.get("sigma1",  23.04))
    sigma2 = float(p.get("sigma2",  23.52))
    sigma3 = float(p.get("sigma3",  0.0119))
    tras   = float(p.get("tras",    0.0119))
    mis    = float(p.get("mis",     21.847))
    transport = (sigma3 + tras) * consumption + sigma1 * power + sigma2 + mis

    asos   = float(p.get("asos_dr",  0.028657))
    arim   = float(p.get("arim_dr",  0.001638))
    uc3    = float(p.get("uc3",      0.002760))
    uc6p   = float(p.get("uc6p_d",   0.000070))
    uc6s   = float(p.get("uc6s_d",   0.1988))
    cpstgd = float(p.get("cpstgd",   0.000560))
    csed   = float(p.get("csed",     0.000560))
    rst    = float(p.get("rst",      0.000572))
    system = (asos + arim + uc3 + uc6p + cpstgd + csed + rst) * consumption + uc6s * power

    if power <= 3.0:
        taxable = max(0.0, consumption - 1800.0)
        accisa = taxable * float(p.get("acc_c_r_l", 0.0227))
    else:
        accisa = consumption * float(p.get("acc_c_r_h", 0.0227))

    subtotal = seller_total + transport + system + accisa
    iva_rate = float(p.get("iva_c", 0.10))
    iva      = subtotal * iva_rate
    total    = subtotal + iva

    return {
        "total":         total,
        "energy_net":    energy_cost,
        "fixed_net":     fixed_cost,
        "dispbt_net":    dispbt_fixed,
        "cdispd_net":    cdispd_var,
        "transport_net": transport,
        "system_net":    system,
        "accisa":        accisa,
        "iva":           iva,
    }


# ── Price history (all dates) ─────────────────────────────────────────────────
@st.cache_data(show_spinner="Caricamento storico prezzi…")
def load_price_history() -> pd.DataFrame:
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
                "date":                  dt,
                "competitor":            COMPETITORS[piva],
                "nome":                  nome,
                "energy_price":          energy_price,
                "fixed_annual":          fixed_annual,
                "fixed_includes_dispbt": fixed_includes_dispbt,
                "renewable":             renewable,
                "limitante":             limitante,
                "fasce":                 fasce,
            })

    return pd.DataFrame(records) if records else pd.DataFrame()


def _ref_prices(hist_df: pd.DataFrame, ref_date, show_limited: bool, prefer_renewable: bool) -> dict:
    """Return {competitor: energy_price} for the closest available date <= ref_date."""
    if hist_df.empty:
        return {}
    subset = hist_df[hist_df["date"] <= ref_date]
    if subset.empty:
        return {}
    closest = subset["date"].max()
    h = subset[subset["date"] == closest].copy()
    if not show_limited:
        non_lim = h[h["limitante"] != "01"][["competitor"]].drop_duplicates()
        non_lim["_nl"] = True
        h = h.merge(non_lim, on="competitor", how="left")
        h = h[(h["limitante"] != "01") | h["_nl"].isna()].drop(columns=["_nl"])
    h_sorted = h.sort_values(["competitor", "renewable", "energy_price"],
                              ascending=[True, False, True])
    best = h_sorted.groupby("competitor", as_index=False).first()
    return dict(zip(best["competitor"], best["energy_price"]))


def _fmt_change(current_ep: float, ref: dict, comp: str) -> str:
    """Format a price change badge relative to a reference price dict."""
    ref_ep = ref.get(comp)
    if ref_ep is None:
        return t("no_ref_data")
    delta = (current_ep - ref_ep) * 100   # c€/kWh
    if abs(delta) < 0.001:
        return t("price_flat")
    arrow = t("price_up") if delta > 0 else t("price_down")
    return f"{arrow} {abs(delta):.2f}c"


# ── Language state ────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state.lang = "it"

# ── Streamlit UI ──────────────────────────────────────────────────────────────
st.title(t("app_title"))
st.caption(t("app_caption"))

# ── Sidebar ───────────────────────────────────────────────────────────────────
all_dates = _available_dates()

with st.sidebar:
    # Language toggle — always at the top
    if st.button(t("lang_button"), use_container_width=True):
        st.session_state.lang = "en" if st.session_state.lang == "it" else "it"
        st.rerun()

    st.divider()
    st.header(t("sidebar_date_header"))
    selected_date = st.selectbox(
        t("sidebar_date_select"),
        options=all_dates,
        index=len(all_dates) - 1,
        format_func=lambda d: d.strftime("%d/%m/%Y"),
    )

    st.divider()
    st.header(t("sidebar_params_header"))

    consumption = st.slider(
        t("sidebar_kwh_slider"),
        min_value=500,
        max_value=5000,
        value=2000,
        step=100,
        help=t("sidebar_kwh_help"),
    )

    power = st.radio(
        t("sidebar_power_radio"),
        options=[3, 6, 9],
        index=0,
        horizontal=True,
    )

    st.divider()
    st.header(t("sidebar_filters"))

    renewable_filter = st.toggle(t("sidebar_renewable"), value=True)
    show_limited = st.toggle(t("sidebar_limited"), value=False,
                             help=t("sidebar_limited_help"))

    st.divider()
    xml_used = _file_for_date("PO_Offerte_E_MLIBERO_", ".xml", selected_date)
    st.caption(f"File: {xml_used.name if xml_used else 'N/A'}")

# ── Load data ─────────────────────────────────────────────────────────────────
params = load_params(selected_date)
all_offers = load_offers(selected_date)

if not all_offers:
    st.error(t("err_no_offers"))
    st.stop()

# ── Filter offers ─────────────────────────────────────────────────────────────
filtered = all_offers.copy()

if renewable_filter:
    renewable_offers = [o for o in filtered if o["renewable"]]
    covered = {o["competitor"] for o in renewable_offers}
    fallback = [o for o in filtered if o["competitor"] not in covered]
    filtered = renewable_offers + fallback

if not show_limited:
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
    st.warning(t("err_no_filter"))
    st.stop()

df_best = (
    df.sort_values("total")
    .groupby("competitor", as_index=False)
    .first()
    .sort_values("total")
)

# ── KPI cards ─────────────────────────────────────────────────────────────────
st.subheader(t("kpi_subheader").format(consumption=consumption, power=power))

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

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([t("tab_ranking"), t("tab_all"), t("tab_history")])

with tab1:
    fig = go.Figure()

    breakdown_components = [
        ("energy_net",    t("comp_energy"),    "#4C9BE8"),
        ("fixed_net",     t("comp_fixed"),     "#F4A261"),
        ("dispbt_net",    t("comp_dispbt"),    "#E76F51"),
        ("cdispd_net",    t("comp_cdispd"),    "#D62828"),
        ("transport_net", t("comp_transport"), "#2A9D8F"),
        ("system_net",    t("comp_system"),    "#E9C46A"),
        ("accisa",        t("comp_accisa"),    "#C9ADA1"),
        ("iva",           t("comp_iva"),       "#D0D0D0"),
    ]

    for comp_key, comp_label, comp_color in breakdown_components:
        fig.add_trace(go.Bar(
            name=comp_label,
            x=df_best["competitor"],
            y=df_best[comp_key],
            marker_color=comp_color,
            text=[f"€{v:.0f}" if v > 20 else "" for v in df_best[comp_key]],
            textposition="inside",
            textfont=dict(size=11, color="white"),
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(text=t("chart1_title"), font_size=15),
        yaxis_title=t("chart1_yaxis"),
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        height=430,
        margin=dict(t=80, b=20),
    )
    fig.update_yaxes(gridcolor="#EEE", tickprefix="€")
    st.plotly_chart(fig, width="stretch")

    display_df = df_best[
        ["competitor", "nome", "energy_price", "fixed_annual", "total", "renewable", "limitante", "durata"]
    ].copy()

    # Price change vs last week / last month
    from datetime import timedelta
    _hist = load_price_history()
    _week_ref  = _ref_prices(_hist, selected_date - timedelta(days=7),  show_limited, renewable_filter)
    _month_ref = _ref_prices(_hist, selected_date - timedelta(days=30), show_limited, renewable_filter)
    display_df["vs_week"]  = display_df.apply(lambda r: _fmt_change(r["energy_price"], _week_ref,  r["competitor"]), axis=1)
    display_df["vs_month"] = display_df.apply(lambda r: _fmt_change(r["energy_price"], _month_ref, r["competitor"]), axis=1)

    ann = t("annual_suffix")
    display_df["energy_price"] = display_df["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
    display_df["fixed_annual"]  = display_df["fixed_annual"].map(lambda x: f"€{x:.0f}{ann}")
    display_df["total"]         = display_df["total"].map(lambda x: f"€{x:.0f}")
    display_df["renewable"]     = display_df["renewable"].map(lambda x: t("renewable_yes") if x else t("renewable_no"))
    display_df["limitante"]     = display_df["limitante"].map(lambda x: t("access_limited") if x == "01" else t("access_open"))
    display_df["durata"]        = display_df["durata"].map(
        lambda x: t("duration_months").format(n=x) if x > 0 else t("duration_unlimited")
    )
    display_df.columns = [
        t("col_supplier"), t("col_offer"), t("col_energy_price"), t("col_fixed_fee"),
        t("col_bill"), t("col_renewable"), t("col_access"), t("col_duration"),
        t("col_vs_week"), t("col_vs_month"),
    ]
    st.dataframe(display_df.set_index(t("col_supplier")), width="stretch")

with tab2:
    df_all = df.sort_values("total").copy()
    df_all["label"] = df_all["competitor"] + " · " + df_all["nome"].str[:40]

    fig2 = go.Figure()
    for comp in df_all["competitor"].unique():
        sub = df_all[df_all["competitor"] == comp]
        color = COLORS.get(comp, "#888")
        fig2.add_trace(go.Bar(
            name=comp,
            x=sub["label"],
            y=sub["total"],
            marker_color=color,
            text=sub["total"].map(lambda x: f"€{x:.0f}"),
            textposition="outside",
        ))

    fig2.update_layout(
        barmode="group",
        title=t("chart2_title"),
        yaxis_title=t("chart1_yaxis"),
        xaxis_tickangle=-35,
        showlegend=True,
        height=520,
        plot_bgcolor="white",
        margin=dict(b=160),
    )
    fig2.update_yaxes(gridcolor="#EEE", tickprefix="€")
    st.plotly_chart(fig2, width="stretch")

    ann = t("annual_suffix")
    df_all_disp = df_all[
        ["competitor", "nome", "energy_price", "fixed_annual", "total", "renewable", "limitante", "durata", "url"]
    ].copy()
    df_all_disp["energy_price"] = df_all_disp["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
    df_all_disp["fixed_annual"]  = df_all_disp["fixed_annual"].map(lambda x: f"€{x:.0f}{ann}")
    df_all_disp["total"]         = df_all_disp["total"].map(lambda x: f"€{x:.0f}")
    df_all_disp["renewable"]     = df_all_disp["renewable"].map(lambda x: "♻" if x else "❌")
    df_all_disp["limitante"]     = df_all_disp["limitante"].map(lambda x: "★" if x == "01" else "✓")
    df_all_disp["durata"]        = df_all_disp["durata"].map(lambda x: f"{x}m" if x > 0 else "∞")
    df_all_disp.columns = [
        t("col_supplier"), t("col_offer"), t("col_energy_price"), t("col_fixed_fee"),
        t("col_bill"), t("col_rinn"), t("col_acc"), t("col_duration"), t("col_link"),
    ]
    st.dataframe(df_all_disp.set_index(t("col_supplier")), width="stretch")

with tab3:
    st.subheader(t("hist_subheader"))
    st.caption(t("hist_caption"))

    if all_dates:
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            hist_start = st.date_input(
                t("hist_from"),
                value=all_dates[0],
                min_value=all_dates[0],
                max_value=all_dates[-1],
                key="hist_start",
            )
        with col_h2:
            hist_end = st.date_input(
                t("hist_to"),
                value=all_dates[-1],
                min_value=all_dates[0],
                max_value=all_dates[-1],
                key="hist_end",
            )

    hist_raw = load_price_history()

    if hist_raw.empty:
        st.info(t("hist_no_data"))
    else:
        h = hist_raw.copy()

        if all_dates:
            h = h[(h["date"] >= hist_start) & (h["date"] <= hist_end)]

        if h.empty:
            st.warning(t("hist_no_period"))
        else:
            if not show_limited:
                non_lim = h[h["limitante"] != "01"][["date", "competitor"]].drop_duplicates()
                non_lim["_has_nl"] = True
                h = h.merge(non_lim, on=["date", "competitor"], how="left")
                h = h[(h["limitante"] != "01") | h["_has_nl"].isna()]
                h = h.drop(columns=["_has_nl"])

            h_sorted = h.sort_values(
                ["date", "competitor", "renewable", "energy_price"],
                ascending=[True, True, False, True],
            )
            best_hist = h_sorted.groupby(["date", "competitor"], as_index=False).first()

            metric_opts = [t("hist_metric_price"), t("hist_metric_bill")]
            metric_choice = st.radio(
                t("hist_metric_label"),
                metric_opts,
                horizontal=True,
            )
            use_bill = metric_choice == t("hist_metric_bill")

            fig3 = go.Figure()

            for comp in sorted(COMPETITORS.values()):
                sub = best_hist[best_hist["competitor"] == comp].sort_values("date")
                if sub.empty:
                    continue
                color = COLORS.get(comp, "#888")

                if use_bill:
                    y_vals = []
                    for _, r in sub.iterrows():
                        offer_dict = {
                            "energy_price":          r["energy_price"],
                            "fixed_annual":          r["fixed_annual"],
                            "fixed_includes_dispbt": r["fixed_includes_dispbt"],
                        }
                        b = calculate_bill(offer_dict, float(consumption), float(power), params)
                        y_vals.append(b["total"])
                    y_label = t("hist_ylabel_bill")
                    y_fmt   = ".0f"
                    y_unit  = "€"
                else:
                    y_vals  = (sub["energy_price"] * 100).tolist()
                    y_label = t("hist_ylabel_price")
                    y_fmt   = ".3f"
                    y_unit  = " c€/kWh"

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
                        "<b>%{x|%d/%m/%Y}</b><br>"
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

            latest_date = best_hist["date"].max()
            latest = best_hist[best_hist["date"] == latest_date].copy()
            ann = t("annual_suffix")
            latest[t("col_energy_price2")] = latest["energy_price"].map(lambda x: f"{x*100:.3f} c€/kWh")
            latest[t("col_fixed_fee2")]    = latest["fixed_annual"].map(lambda x: f"€{x:.0f}{ann}")
            latest[t("col_renewable2")]    = latest["renewable"].map(lambda x: "♻" if x else "○")
            latest[t("col_access2")]       = latest["limitante"].map(
                lambda x: t("access_limited") if x == "01" else t("access_open")
            )
            st.caption(t("hist_latest_caption").format(date=latest_date.strftime("%d/%m/%Y")))
            st.dataframe(
                latest[["competitor", t("col_energy_price2"), t("col_fixed_fee2"), t("col_renewable2"), t("col_access2")]]
                .rename(columns={"competitor": t("col_supplier")})
                .set_index(t("col_supplier"))
                .sort_values(t("col_energy_price2")),
                width="stretch",
            )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(t("footer"))
