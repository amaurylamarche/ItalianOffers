# ⚡ Confronto Offerte Energia Elettrica — Mercato Libero Italiano

A Streamlit dashboard that compares fixed-price electricity offers from major Italian suppliers (Octopus, Enel, NeN, E.ON, ENGIE, Dolomiti, Edison, Hera, Iren) using data published daily by ARERA on the [Portale Offerte](https://www.portaleofferte.it).

## Features

- **Bill estimator** — computes the full annual bill (energy + dispatch + transport + system charges + excise + VAT) for any consumption profile
- **Historical price tracking** — charts the cheapest offer per supplier across all available dates
- **Date selector** — pick any historical date to see the market snapshot for that day
- **Date range filter** — zoom into any sub-period in the history chart
- **Renewable filter** — toggle to show only green-energy offers (Garanzie di Origine)
- **Ranking + breakdown** — stacked bar chart showing the regulated vs. commercial bill components side by side

## Data Sources

| File pattern | Content |
|---|---|
| `PO_Offerte_E_MLIBERO_YYYYMMDD.xml` | Offer details (prices, fixed fees, conditions) |
| `PO_Parametri_Mercato_Libero_E_YYYYMMDD.csv` | Regulated tariff parameters (transport, system charges, VAT) |

Both files are published daily by ARERA / Acquirente Unico and stored in `energy price/`.

## Automation Reliability

The daily downloader workflow (`.github/workflows/download_daily.yml`) includes:

- concurrency control to avoid overlapping runs on the same branch;
- retry-safe git push logic (`fetch` + `pull --rebase` + retry);
- a GitHub Actions step summary reporting XML/CSV download status.

## Getting Started

### Prerequisites

- Python 3.11+
- Files in `energy price/` (XML + CSV from ARERA)

### Install & Run

```bash
pip install -r requirements.txt
streamlit run italianprices.py
```

The app opens at `http://localhost:8501`.

### Share with a Colleague (quick)

```bash
# Install ngrok once
winget install ngrok.ngrok

# In one terminal: run the app
streamlit run italianprices.py

# In another terminal: expose it
ngrok http 8501
```

Share the generated `https://*.ngrok-free.app` URL — no setup needed on the colleague's side.

## Production Deployment

### Option A — Streamlit Cloud (fastest)

1. Push this repo to GitHub.
2. In Streamlit Cloud, create a new app pointing to:
      - Repository: this project
      - Branch: `main`
      - Main file: `italianprices.py`
3. Add secrets in Streamlit Cloud (App settings → Secrets), for example:
      - `ANTHROPIC_API_KEY`
4. Deploy. Every push to `main` triggers an automatic redeploy.

### Option B — Container deployment (production-grade)

This repository now includes:

- `Dockerfile`
- `.dockerignore`
- `.streamlit/config.toml`
- `.github/workflows/deploy_container.yml`

The workflow builds and publishes the image to GHCR:

- `ghcr.io/<github_org_or_user>/italianoffers:latest`

Run locally with Docker:

```bash
docker build -t italianoffers:local .
docker run --rm -p 8501:8501 italianoffers:local
```

Then open `http://localhost:8501`.

You can deploy the same image to Azure Container Apps, AWS ECS/Fargate, GCP Cloud Run, or any Kubernetes cluster.

## Methodology

The annual bill estimate follows the ARERA methodology for domestic residential customers:

```
Total = Spesa Materia Energia
      + Spesa Trasporto e Gestione Contatore
      + Oneri di Sistema
      + Accisa
      + IVA (10%)
```

**Spesa Materia Energia** = supplier's quoted energy price × consumption  
+ fixed commercial fee  
+ CdispD variable (regulatory dispatch component)  
+ DISPbt fixed (regulatory dispatch, added unless supplier already bundled it)

For connections ≤ 3 kW (residential), excise is exempt on the first 1,800 kWh/year.

Regulated components (transport, system charges, excise, VAT rates) are read from the most recent CSV parameter file.

## Suppliers Tracked

| VAT number | Supplier |
|---|---|
| 01771990445 | Octopus Energy |
| 06655971007 | Enel |
| 10879560968 | NeN |
| 03429130234 | E.ON |
| 06289781004 | ENGIE |
| 01812630224 | Dolomiti Energia |
| 08526440154 | Edison |
| 02221101203 | Hera |
| 01178580997 | Iren |

## Project Structure

```
.
├── italianprices.py        # Main Streamlit app
├── requirements.txt        # Python dependencies
├── energy price/           # ARERA data files
│   ├── PO_Offerte_E_MLIBERO_*.xml
│   └── PO_Parametri_Mercato_Libero_E_*.csv
└── README.md
```
