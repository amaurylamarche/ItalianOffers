import sys, xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

DATA_DIR = Path(r'C:\Users\HIA415\Sandbox\energy price')
NS = {'au': 'http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01'}

NEW = {
    '01812630224': 'Dolomiti',
    '08526440154': 'Edison',
    '02221101203': 'Hera',
    '01178580997': 'Iren',
}
F_WEIGHTS = {'01': 0.44, '02': 0.21, '03': 0.35}

xml_path = sorted(DATA_DIR.glob('PO_Offerte_E_MLIBERO_*.xml'))[-1]
root = ET.parse(xml_path).getroot()

for offerta in root.findall('au:offerta', NS):
    piva = offerta.findtext('au:IdentificativiOfferta/au:PIVA_UTENTE', namespaces=NS)
    if piva not in NEW:
        continue
    tipo_offerta = offerta.findtext('au:DettaglioOfferta/au:TIPO_OFFERTA', namespaces=NS)
    tipo_cliente = offerta.findtext('au:DettaglioOfferta/au:TIPO_CLIENTE', namespaces=NS)
    fasce        = offerta.findtext('au:TipoPrezzo/au:TIPOLOGIA_FASCE', namespaces=NS)
    limitante    = offerta.findtext('au:CondizioniContrattuali/au:LIMITANTE', namespaces=NS) or '02'
    nome         = offerta.findtext('au:DettaglioOfferta/au:NOME_OFFERTA', namespaces=NS) or ''
    desc         = (offerta.findtext('au:DettaglioOfferta/au:DESCRIZIONE', namespaces=NS) or '').lower()

    if tipo_offerta != '01' or tipo_cliente != '01':
        continue
    if fasce not in ('01', '03'):
        continue

    renew = 'rinnovab' in desc or 'garanzie di origine' in desc or 'verde' in nome.lower()
    lim = 'LIM' if limitante == '01' else ''

    energy_price = 0.0
    fixed_annual = 0.0
    inc_dispbt = False

    for comp in offerta.findall('au:ComponenteImpresa', NS):
        if comp.findtext('au:TIPOLOGIA', namespaces=NS) != '01':
            continue
        ma = comp.findtext('au:MACROAREA', namespaces=NS) or ''
        cn = (comp.findtext('au:NOME', namespaces=NS) or '').lower()
        cd = (comp.findtext('au:DESCRIZIONE', namespaces=NS) or '').lower()
        ivs = comp.findall('au:IntervalloPrezzi', NS)
        if ma in ('04', '06'):
            pf = {}
            for iv in ivs:
                f = iv.findtext('au:FASCIA_COMPONENTE', namespaces=NS) or '00'
                p = float(iv.findtext('au:PREZZO', namespaces=NS) or 0)
                u = iv.findtext('au:UNITA_MISURA', namespaces=NS) or '03'
                if u == '03': pf[f] = p
            if '04' in pf:
                energy_price = pf['04']
            elif pf:
                vals = list(pf.values())
                energy_price = vals[0] if len(set(round(v,6) for v in vals))==1 else sum(pf.get(f,0)*w for f,w in F_WEIGHTS.items())
        elif ma == '01':
            for iv in ivs:
                p = float(iv.findtext('au:PREZZO', namespaces=NS) or 0)
                u = iv.findtext('au:UNITA_MISURA', namespaces=NS) or '01'
                fixed_annual += p if u=='01' else (p*12 if u=='02' else 0)
            if 'dispbt' in cn or 'dispbt' in cd or 'dispacciament' in cd:
                inc_dispbt = True

    if energy_price == 0:
        continue

    renbadge = '♻' if renew else '  '
    print(f"{renbadge} [{fasce}] {NEW[piva]:10} {nome[:40]:40} ep={energy_price*100:.3f}c€ fix={fixed_annual:.0f}€ dispbt={'IN' if inc_dispbt else 'OUT'} {lim}")
