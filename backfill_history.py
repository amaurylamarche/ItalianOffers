"""
One-shot backfill: download ARERA power+gas XML/CSV files from 13/03/2025 to today.
Files already present in the energy price/ folder are skipped.
"""
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "energy price"
BASE     = "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata"

start = date(2025, 3, 13)
end   = date.today()

downloaded, skipped, missing = 0, 0, 0
current = start

while current <= end:
    y     = current.year
    m     = current.month    # no leading zero
    d_str = current.strftime("%Y%m%d")

    files = [
        (
            f"{BASE}/csv/offerteML/{y}_{m}/PO_Offerte_E_MLIBERO_{d_str}.xml",
            DATA_DIR / f"PO_Offerte_E_MLIBERO_{d_str}.xml",
        ),
        (
            f"{BASE}/csv/parametriML/{y}_{m}/PO_Parametri_Mercato_Libero_E_{d_str}.csv",
            DATA_DIR / f"PO_Parametri_Mercato_Libero_E_{d_str}.csv",
        ),
        (
            f"{BASE}/csv/offerteML/{y}_{m}/PO_Offerte_G_MLIBERO_{d_str}.xml",
            DATA_DIR / f"PO_Offerte_G_MLIBERO_{d_str}.xml",
        ),
        (
            f"{BASE}/csv/parametriML/{y}_{m}/PO_Parametri_Mercato_Libero_G_{d_str}.csv",
            DATA_DIR / f"PO_Parametri_Mercato_Libero_G_{d_str}.csv",
        ),
    ]

    for url, path in files:
        if path.exists():
            skipped += 1
            continue
        try:
            urllib.request.urlretrieve(url, path)
            downloaded += 1
            print(f"  OK  {path.name}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                missing += 1   # portal simply didn't publish that day
            else:
                print(f"  ERR {e.code}  {url}")
                missing += 1
        except Exception as e:
            print(f"  ERR {e}  {url}")
            missing += 1

        time.sleep(0.15)   # be respectful to the server

    current += timedelta(days=1)

print(f"\nDone. Downloaded: {downloaded}  |  Skipped (exist): {skipped}  |  Not published: {missing}")
