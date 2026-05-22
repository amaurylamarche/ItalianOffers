"""
One-shot script: parse all XML files in 'energy price/' and write a compact
price_history_precomputed.csv so the Streamlit app doesn't need the raw XMLs
for historical dates.

Run locally after a backfill. Push the resulting CSV to GitHub.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime as _dt
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "energy price"
OUT_FILE = DATA_DIR / "price_history_precomputed.csv"

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
F_WEIGHTS = {"01": 0.44, "02": 0.21, "03": 0.35}


def parse_xml(xml_path: Path, dt) -> list[dict]:
    records = []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return records

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
            "date":                  dt.strftime("%Y-%m-%d"),
            "competitor":            COMPETITORS[piva],
            "nome":                  nome,
            "energy_price":          round(energy_price, 6),
            "fixed_annual":          round(fixed_annual, 4),
            "fixed_includes_dispbt": fixed_includes_dispbt,
            "renewable":             renewable,
            "limitante":             limitante,
            "fasce":                 fasce,
        })
    return records


all_records = []
xml_files = sorted(DATA_DIR.glob("PO_Offerte_E_MLIBERO_*.xml"))
print(f"Found {len(xml_files)} XML files to process...")

for i, xml_path in enumerate(xml_files, 1):
    m = re.search(r"(\d{8})", xml_path.stem)
    if not m:
        continue
    try:
        dt = _dt.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        continue
    records = parse_xml(xml_path, dt)
    all_records.extend(records)
    if i % 50 == 0:
        print(f"  {i}/{len(xml_files)} processed ({len(all_records)} records so far)")

df = pd.DataFrame(all_records)
df.to_csv(OUT_FILE, index=False)
print(f"\nDone. {len(df)} records written to {OUT_FILE}")
print(f"File size: {OUT_FILE.stat().st_size / 1024:.1f} KB")
