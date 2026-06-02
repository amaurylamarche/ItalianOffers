import sys, xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

DATA_DIR = Path(r'C:\Users\HIA415\Sandbox\energy price')
NS = {'au': 'http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01'}

xml_path = sorted(DATA_DIR.glob('PO_Offerte_E_MLIBERO_*.xml'))[-1]
root = ET.parse(xml_path).getroot()

piva_urls = {}
for offerta in root.findall('au:offerta', NS):
    piva = offerta.findtext('au:IdentificativiOfferta/au:PIVA_UTENTE', namespaces=NS)
    url  = (offerta.findtext('au:DettaglioOfferta/au:Contatti/au:URL_SITO_VENDITORE', namespaces=NS) or '').lower()
    nome = (offerta.findtext('au:DettaglioOfferta/au:NOME_OFFERTA', namespaces=NS) or '').lower()
    desc = (offerta.findtext('au:DettaglioOfferta/au:DESCRIZIONE', namespaces=NS) or '').lower()
    if piva not in piva_urls:
        piva_urls[piva] = {'url': url, 'nome': nome, 'desc': desc}

keywords = {
    'dolomiti': ['dolomit'],
    'edison':   ['edison'],
    'hera':     ['hera'],
    'iren':     ['iren'],
}

for label, kws in keywords.items():
    print(f'\n=== {label.upper()} ===')
    found = set()
    for piva, d in piva_urls.items():
        combined = d['url'] + ' ' + d['nome'] + ' ' + d['desc']
        if any(k in combined for k in kws):
            if piva not in found:
                found.add(piva)
                print(f'  PIVA: {piva}  URL: {d["url"][:60]}')
