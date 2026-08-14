# Public-Data Reporting & Air Quality Dashboard

**Public-Data Reporting & Air Quality Dashboard** is a production-ready, BCNF-normalized data engineering pipeline and interactive Streamlit web dashboard. It processes Central Pollution Control Board (CPCB) India daily air quality records combined with 2011 Census metadata, cleans sensor anomalies, and executes analytical queries for environmental policy reporting.

---

## 🌟 Key Features

- **BCNF Relational Architecture**: 8 normalized database tables (`dim_states`, `dim_locations`, `dim_cities`, `dim_city_anomalies`, `dim_stations`, `dim_agency_registry`, `fact_ingestion_logs`, `fact_readings`) linked on integer keys with zero orphan records.
- **Automated Multi-Agent Ingestion Engine**: Drop folder scanner (`agency_ingest.py`) with schema validation (`SchemaA` / `SchemaB`), date & numeric domain checking, database city anomaly resolution (`dim_city_anomalies`), timestamped post-processing file archiving (`data/agency_archive/`), and execution logging (`fact_ingestion_logs`).
- **Interactive Streamlit Dashboard (`app.py`)**:
  - **Overview & System Health**: Executive KPIs, data reliability rates, and historical time-series charts.
  - **Seasonal Swing Analytics**: Winter (Nov–Feb) vs. Summer (Apr–Jun) PM2.5 comparisons.
  - **Weighted State Rankings**: Population-weighted AQI state rankings.
  - **Threshold Exceedance Trends**: Interactive PM2.5 threshold slider with YoY trend status.
  - **Station Audit & Reliability**: Sensor anomaly detection (stuck values, physical impossibilities, out-of-scale AQI).
  - **Multi-Agency Ingestion & Agent Setup**: Live folder scanner trigger and dynamic agency setup registry.
  - **Interactive Database Explorer**: Live search filtering across all 8 BCNF database tables.

---

## 🚀 Quickstart Guide

### 1. Prerequisites & Installation

Clone the repository and install the dependencies:
```bash
git clone https://github.com/Shreyash1712/NAVIGA.git
cd NAVIGA
pip install -r requirements.txt
```

### 2. Database Ingestion & Verification

Build the BCNF SQLite database (`air_quality.db`) and run the test suite:
```bash
python ingest.py
python verify_ingest.py
```

### 3. Launch Dashboard Locally

Start the interactive Streamlit dashboard:
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🌐 Public Cloud Deployment (Streamlit Community Cloud)

1. Fork or push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io).
3. Connect your GitHub account and select repository `Shreyash1712/NAVIGA`.
4. Set Main file path to `app.py`.
5. Click **Deploy!**
