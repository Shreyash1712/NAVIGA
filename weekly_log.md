# Weekly Log of Decisions & Blockers

This document tracks key engineering decisions and blockers encountered throughout the implementation of the Public-Data Reporting Dashboard.

---

## 📅 Week 1: Exploration & Design Doc

### Decisions Made
- **Dataset Strategy**: Combined CPCB daily air quality records (`city_day.csv` and `station_day.csv`) with the 2011 Census city population metadata (`cities_population.csv`) to enable population-weighted state-level aggregations.
- **Database Choice**: Chose SQLite for local development to ensure 100% self-contained, reproducible, zero-configuration runs. Chose SQLAlchemy ORM to remain database-agnostic, allowing easy migration to production PostgreSQL (via Supabase or Neon) by swapping the environment connection string.
- **Relational Schema**: Implemented a **Star Schema** with two dimension tables (`dim_cities`, `dim_stations`) and two fact tables (`fact_city_readings`, `fact_station_readings`) to enable clean foreign key relationships and fast, indexed queries.
- **Data Quality Approach**: Rather than dropping records with missing pollutant measurements (which would break historical timelines), we decided to keep them as `NULL` and handle them dynamically in SQL. For sensor anomalies (stuck values, AQI exceeding the 500 scale limit), we chose to keep the data but flag it with an `is_reliable = FALSE` column to preserve transparency.
- **City & Population Mapping**: Created a translation dictionary to resolve name discrepancies (e.g., `Ahmedabad` -> `Ahmadabad`, `Gurugram` -> `Gurgaon`). Imputed populations manually for small industrial towns (Brajrajnagar, Jorapokhar, Talcher) which were missing from the census dataset (population < 100,000).

### Blockers Hit & Resolutions
- **Blocker: Git LFS Pointer Download**: The raw GitHub URLs in the initial download script returned 130-byte Git LFS pointer files rather than the actual CSV datasets. Git LFS was also not installed on the system shell.
  - *Resolution*: Wrote a python script (`download_lfs.py`) that queries the GitHub Git LFS batch API endpoint using the objects' SHA-256 hashes (OIDs) and sizes to get the direct download links from the media servers.
- **Blocker: Formatting & Trailing Spaces in Census Data**: When checking linkages, nearly all cities failed to match exactly because the population dataset had trailing whitespaces in its city names.
  - *Resolution*: Stripped all string fields programmatically in Pandas and verified exact spelling matches.

---

## 📅 Week 2: Ingestion & Schema Setup

### Decisions Made
- **Dimension Spelling Synchronization**: Decided to update mismatched city names directly in the `dim_cities` table during database ingestion (e.g., renaming the census record of `Ahmadabad` to `Ahmedabad` and `Gurgaon` to `Gurugram`). This guarantees that `fact_city_readings.city_name` matches `dim_cities.city_name` natively without requiring translation joins at query time.
- **Independent Dimension Tables**: Kept `dim_stations` decoupled from `dim_cities` (no foreign key check on station city names) to prevent import failures for small town stations, while keeping `fact_city_readings` safely constrained.
- **Chunked Insertion**: Configured SQLAlchemy bulk inserts in chunks of 5000 rows to ensure rapid loading of the 130,000+ total rows while maintaining low memory consumption.

### Blockers Hit & Resolutions
- **Blocker: Column Name KeyErrors**: Encountered a `KeyError: 'city_name'` when running `ingest.py`. The stations dataset used `City` and `State` as headers which, after column normalization, became `city` and `state`, leading to mismatches with target database columns.
  - *Resolution*: Updated the pandas mapping to look up `city` and `state` columns first, applying the spelling translation dictionary before renaming them to `city_name` and `state_name` for insertion.

---

## 📅 Week 3: Database Normalization (1NF, 2NF, 3NF, BCNF)

### Decisions Made
- **BCNF Decompositions**: Normalised the database schema by separating `dim_states` from `dim_cities` to eliminate the transitive dependency `state_code -> state_name` (**3NF**). Removed `city_name` and `state_name` from `dim_stations` so it only references `city_id` (**3NF/BCNF**).
- **Composite City Constraint**: Implemented a composite unique constraint `UNIQUE(city_name, state_code)` on `dim_cities` to handle identical city names located in different states (e.g. `Bilaspur` in HP and Chhattisgarh).
- **Removing Derived Fact Columns**: Removed `aqi_bucket` from `fact_city_readings` and `fact_station_readings` since `aqi -> aqi_bucket` represents a transitive dependency (`reading_id -> aqi -> aqi_bucket`), which violated 3NF. AQI bucket classification is now calculated dynamically during query executions.
- **Dynamic City Creation**: Programmed `ingest.py` to check for any city in `stations.csv` that is missing from the 100k+ census list and dynamically add a default city record in `dim_cities`, guaranteeing no foreign key constraint violations occur.

### Blockers Hit & Resolutions
- **Blocker: KeyError on population column**: A `KeyError: "['population'] not in index"` occurred during the normalized run of `ingest.py` because the rename function renamed the census columns but left `population_total` un-mapped when generating dictionaries.
  - *Resolution*: Added `'population_total': 'population'` to the pandas column rename dictionary in `ingest.py`.
- **Blocker: Dynamic Telangana state mapping**: Telangana state (code 36) was not in the 2011 census dataset but was in the CPCB stations metadata, causing foreign key failures when creating city records.
  - *Resolution*: Updated `ingest.py` to dynamically check and append new states like Telangana to `dim_states` if they are detected in stations or other source files.

---

## 📅 Week 4: Schema Redesign Part 2 & Analytical Queries

### Decisions Made
- **Class Table Inheritance (Supertype/Subtype)**: Created `dim_locations` as a parent table registering all unique cities and stations. This allows us to merge city and station readings into a unified `fact_readings` table while preserving strict foreign key constraints.
- **Temporal Population Columns**: Added `start_date` and `end_date` directly to `dim_cities` to manage non-constant population records over time (SCD Type 2), keeping population history grouped within the city table.
- **Merged Readings Fact Table**: Dropped `fact_city_readings` and `fact_station_readings` and merged them into `fact_readings` with `geographic_id` and `type` columns to consolidate daily logs and prevent reading contradictions.
- **SQL Join Date Range Filtering**: Updated all queries to filter joins dynamically: `r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')` to retrieve the active population version.

### Blockers Hit & Resolutions
- **Blocker: Population-Weighted AQI Denominator skewing**: Cities without active reporting in a given month skewed the population weight denominator since `SUM(population)` included them while `SUM(aqi * population)` ignored them.
  - *Resolution*: Filtered the CTE for `r.aqi IS NOT NULL`, ensuring only cities with active readings have their populations included in the denominator.
- **Blocker: Stable sorting ties on weighted averages**: Tied weighted averages (e.g. Delhi and Odisha both at 101.0 in July 2020) caused minor sorting order mismatch between raw SQL and Pandas.
  - *Resolution*: Applied an alphabetical state name secondary sorting criteria `ORDER BY weighted_aqi DESC, s.state_name ASC` to guarantee stable, deterministic outputs.

---

## 📅 Week 5 & 6: Schema Redesign Part 3 (ID-Based Joins) & Streamlit Integration

### Decisions Made
- **Integer Key Normalization**: Refactored the database schema to eliminate string name joins. Replaced string references in `dim_cities`, `dim_stations`, and `fact_readings` with auto-incrementing integer `location_id` foreign keys to enforce strict BCNF integrity.
- **In-Memory ID Mapping**: Updated `ingest.py` to flush `dim_locations` and resolve all integer `location_id` mappings dynamically before inserting cities, stations, and daily fact readings.
- **Streamlit App Query Refactoring**: Updated all SQL analytical queries in `app.py` to execute table joins on integer `location_id` columns, including search filtering in the Interactive Database Explorer.

### Blockers Hit & Resolutions
- **Blocker: Leftover sqlite tables**: Dropping and recreating tables using `Base.metadata.create_all` left legacy tables (`fact_city_readings`, `fact_station_readings`) in `air_quality.db`.
  - *Resolution*: Ran explicit `DROP TABLE IF EXISTS` operations to clean out obsolete tables, ensuring the SQLite database contains only the 5 normalized BCNF tables.

---

## 📅 Week 7: Schema Redesign Part 4 (Hierarchy & Attribute Restructuring)

### Decisions Made
- **Entity Attribute Restructuring**: Re-aligned attributes across entity tables per requirements:
  - `dim_cities`: Uses `city_name` (no `location_id`).
  - `dim_stations`: Uses `station_id` (station code e.g. `'AP001'`), `location_id`, `station_name`, and `status`.
  - `dim_locations`: Features `location_id`, self-referential `parent_id` (linking station locations to their parent city's `location_id`), and `type` (`'city'` or `'station'`).
- **Parent-Child Location Hierarchy**: Moved parent city linkages into `dim_locations.parent_id`, simplifying hierarchical queries and station rollups.
- **Full Verification**: Verified 0 orphan records across all table joins, 100% agreement between SQL and Pandas analytical queries, and updated the Streamlit dashboard app (`app.py`).

---

## 📅 Week 6: Multi-Agent Ingestion Pipeline, Performance & Public Release

### Decisions Made
- **Automated Multi-Agency Ingestion & Archiving Engine**: Implemented an automated file ingestion system in `agency_ingest.py` driven by `dim_agency_registry`. Supports inbound drop folder scanning, schema header validation (`SchemaA` / `SchemaB`), database insertion into `fact_readings`, timestamped archiving in `data/agency_archive/`, and audit logging in `fact_ingestion_logs`.
- **Database Anomaly Normalization (`dim_city_anomalies`)**: Replaced all hardcoded Python dictionaries and static pandas replacements with database-driven resolution via `dim_city_anomalies`.
- **Streamlit Performance Optimization**: Configured resource and data caching (`@st.cache_resource` / `@st.cache_data`) in `app.py` for instant rendering and query execution across all analytical tabs.
- **Complete Test & BCNF Integrity Verification**: Validated full referential integrity in `verify_ingest.py` across all 8 BCNF tables (`dim_states`, `dim_locations`, `dim_cities`, `dim_city_anomalies`, `dim_stations`, `dim_agency_registry`, `fact_ingestion_logs`, `fact_readings`).

### Blockers Hit & Resolutions
- **Blocker: Non-integer row index iteration**: String indices during row iteration in pandas led to `TypeError: can only concatenate str (not "int") to str` when formatting row numbers.
  - *Resolution*: Updated row enumeration in `agency_ingest.py` to use explicit integer enumeration `enumerate(df.iterrows(), 1)`, guaranteeing robust row index calculations regardless of index type.
