# Technical Stack & Architecture Justification

This document details the selected technical stack for the **Public-Data Reporting Dashboard** and explains the engineering rationale behind each technology choice.

---

## 🚀 The Core Stack

| Component | Selected Technology | Purpose |
| :--- | :--- | :--- |
| **Programming Language** | **Python (3.11+)** | Core scripting, pipeline orchestration, and UI development. |
| **Data Ingestion & Wrangling** | **Pandas & NumPy** | Fast, vectorized cleaning, string formatting, and anomaly detection. |
| **Database ORM & Agility** | **SQLAlchemy (1.4)** | Database-agnostic schema generation and bulk chunk inserts. |
| **Relational Database** | **SQLite** (Dev/Local) <br> **PostgreSQL (Supabase)** (Prod) | Local offline zero-setup database and highly-available production host. |
| **Dashboard UI Framework** | **Streamlit** | Interactive front-end dashboard and time-series visualization. |
| **Deployment Platform** | **Streamlit Community Cloud** | Serverless hosting for the web application dashboard. |



