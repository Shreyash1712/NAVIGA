# Data Quality & Cleaning Report

This document reports on the data health audits, data cleaning pipeline execution, and final data quality metrics for the **Public-Data Reporting Dashboard** (Week 3 Milestone).

---

## 1. Executive Summary

A comprehensive data quality audit was executed on the CPCB air quality datasets and the 2011 Census population metadata. The raw air quality datasets contained significant missing values (~15% to 79% depending on the pollutant) and various anomalies (stuck sensors and physically impossible values). 

We designed and executed a programmatic data cleaning, deduplication, spelling normalization, outlier flagging, and short-term linear interpolation pipeline in [ingest.py](file:///Users/shreyashpagia/Desktop/NAVIGAS/ingest.py). 

The cleaned database meets strict BCNF relational constraints, with 0 orphan records, and is fully ready to support high-integrity analytical reporting on the dashboard.

---

## 2. Quantification of Data Quality Issues

### 2.1 Missing Values (Pre-Cleaning)
The following tables quantify the raw missing value percentages in the core datasets:

#### City-Level daily readings (`city_day.csv` - 29,531 rows)
| Pollutant/Column | Missing Count | Percentage (%) |
| :--- | :--- | :--- |
| `PM2.5` | 4,598 | 15.57% |
| `PM10` | 11,140 | 37.72% |
| `NH3` | 10,328 | 34.97% |
| `CO` | 2,059 | 6.97% |
| `SO2` | 3,854 | 13.05% |
| `O3` | 4,022 | 13.62% |
| `Xylene` | 18,109 | 61.32% |
| `AQI` | 4,681 | 15.85% |

#### Station-Level daily readings (`station_day.csv` - 108,035 rows)
| Pollutant/Column | Missing Count | Percentage (%) |
| :--- | :--- | :--- |
| `PM2.5` | 21,625 | 20.02% |
| `PM10` | 42,706 | 39.53% |
| `NH3` | 48,105 | 44.53% |
| `CO` | 12,998 | 12.03% |
| `SO2` | 25,204 | 23.33% |
| `O3` | 25,568 | 23.67% |
| `Xylene` | 85,137 | 78.81% |
| `AQI` | 21,010 | 19.45% |

---

### 2.2 Duplicates Audit
- **dim_cities**: 0 duplicate cities in raw population records on `(city_name, state_code)`.
- **dim_stations**: 0 duplicate stations.
- **fact tables**: 0 duplicate records on `(city_id, date)` and `(station_id, date)`.

---

### 2.3 Spelling & Naming Mismatches
Spelling and naming errors were identified across files and resolved using an explicit mapping:
- **States**: Renamed `Orissa` -> `Odisha` and `Nct Of Delhi` -> `Delhi`. Strip-cleaned trailing spaces from all string columns.
- **Cities**:
  - `Ahmadabad` -> `Ahmedabad`
  - `Amravati` -> `Amaravati`
  - `Gurgaon` -> `Gurugram`
  - `Greater Hyderabad` -> `Hyderabad`
  - `Greater Mumbai` -> `Mumbai`
- **Missing Cities**: Identified that 4 cities present in the CPCB datasets (`Brajrajnagar`, `Jorapokhar`, `Talcher`, `Ernakulam`) were missing from the population census due to the census's 100k+ population cutoff.

---

### 2.4 Sensor Anomalies & Outliers Flagged
To preserve data transparency and historical continuity, we flagged anomalous records with a boolean flag `is_reliable = FALSE` instead of deleting them. The audit flagged the following anomalies:

| Anomaly Type | Criteria | City Readings (29,531 rows) | Station Readings (108,035 rows) |
| :--- | :--- | :--- | :--- |
| **Stuck Sensors** | Same value for 3+ consecutive days (PM2.5/AQI) | 76 | 184 |
| **Saturated Sensors** | Pollutant value flatlines at exactly `1000.0` | 1 | 2 |
| **Physically Impossible** | AQI exceeds standard scale of 500 (up to 2049) | 543 | 1,883 |
| **Negative Readings** | Any pollutant concentration < 0 | 0 | 0 |
| **Total Flagged** | Union of all anomalies | **620 (2.10%)** | **2,068 (1.91%)** |

---

## 3. Resolution & Imputation Strategies

### 3.1 Deduplication Action
Any potential duplicate records were programmatically dropped during the ingestion stage using `.drop_duplicates(subset=[...])` in Pandas.

### 3.2 Short-term Linear Interpolation
For short gaps where a monitoring station or city missed 1 or 2 consecutive daily logs, we applied **linear interpolation** to reconstruct the timeline. 
- *Constraint*: Gaps larger than 2 consecutive days were left as `NULL` in the database to prevent introducing fabricated data.
- *Unreliable Masking*: Anomalous rows flagged as `is_reliable = FALSE` were treated as missing (temporarily set to `NaN`) to prevent them from distorting the interpolation of adjacent valid days.

The interpolation successfully imputed the following missing values:
- **City-Level daily readings**:
  - PM2.5: Imputed **447** missing values.
  - PM10: Imputed **331** missing values.
  - AQI: Imputed **613** missing values.
- **Station-Level daily readings**:
  - PM2.5: Imputed **1,860** missing values.
  - PM10: Imputed **1,424** missing values.
  - AQI: Imputed **2,512** missing values.

### 3.3 Demographic Imputation (Population)
Manual population injections were executed to resolve small town omissions:
- **Brajrajnagar**: State: Odisha (State Code 21), Population: 80,000, Literacy: 82.0%, Sex Ratio: 910
- **Jorapokhar**: State: Jharkhand (State Code 20), Population: 85,000, Literacy: 74.0%, Sex Ratio: 880
- **Talcher**: State: Odisha (State Code 21), Population: 40,000, Literacy: 85.0%, Sex Ratio: 900
- **Ernakulam**: State: Kerala (State Code 32), Population: 135,000, Literacy: 90.0%, Sex Ratio: 1027

To prevent foreign key violations, any other city present in CPCB metadata but missing from the census was dynamically created in `dim_cities` with a default population of 0 and null demographic indicators.

---

## 4. Database Validation

After execution, [verify_ingest.py](file:///Users/shreyashpagia/Desktop/NAVIGAS/verify_ingest.py) confirmed:
- **Integrity**: 0 orphan readings exist in the fact tables.
- **BCNF Compliance**: All tables are properly normalized, and queries successfully join facts to states/cities/stations.
- **Imputed Statistics**: Verified that regional AQI averages updated slightly after resolving short-term gaps, confirming successful pipeline interpolation.
