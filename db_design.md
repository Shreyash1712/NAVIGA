# Relational Database Schema Design (Redesigned to BCNF)

This document details the database schema design for the **Public-Data Reporting Dashboard** in table formats, explaining how the design satisfies 1NF, 2NF, 3NF, and BCNF under the redesigned temporal and unified schema structure.

---

## 1. Table Schemas

### Table: `dim_states`
Contains state-level identifiers. Normalises `dim_cities` to 3NF.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `state_code` | `INTEGER` | `PRIMARY KEY` | Unique census identifier for each state. |
| `state_name` | `VARCHAR(100)` | `UNIQUE`, `NOT NULL` | Standardised name of the state (e.g., `"Gujarat"`, `"Delhi"`). |

---

### Table: `dim_locations`
Unified location registry serving as the supertype for both cities and stations. Enforces referential integrity on the unified fact table.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `location_id` | `INTEGER` | `PRIMARY KEY`, `AUTOINCREMENT` | Unique integer identifier for each geographic location. |
| `parent_id` | `INTEGER` | `FOREIGN KEY` references `dim_locations(location_id)` | Self-referential parent location ID (points to parent city location_id for stations, NULL for cities). |
| `type` | `VARCHAR(20)` | `NOT NULL` | The entity type: `'city'` or `'station'`. |

---

### Table: `dim_cities`
Subtype table storing city demographic and temporal population records (SCD Type 2).

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `city_record_id`| `INTEGER` | `PRIMARY KEY`, `AUTOINCREMENT` | Unique surrogate key for each historical city version. |
| `city_name` | `VARCHAR(100)` | `NOT NULL` | Name of the city (e.g., `"Ahmedabad"`). |
| `state_code` | `INTEGER` | `FOREIGN KEY` references `dim_states(state_code)` | State code (linked to `dim_states`). |
| `population` | `INTEGER` | `NOT NULL` | Population count during the active period. |
| `literacy_rate`| `FLOAT` | None | Total literacy rate percentage. |
| `sex_ratio` | `INTEGER` | None | Sex ratio (females per 1,000 males). |
| `start_date` | `DATE` | `NOT NULL` | Date when this city version became active. |
| `end_date` | `DATE` | `NULL` | Date when this city version expired. `NULL` means active. |

---

### Table: `dim_city_anomalies` [NEW]
Dimension table mapping raw city name variations/misspellings to normalized city records.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `raw_city_name` | `VARCHAR(100)` | `PRIMARY KEY` | Raw or variation city name (e.g. `"Ahmadabad"`, `"Gurgaon"`). |
| `city_record_id`| `INTEGER` | `FOREIGN KEY` references `dim_cities(city_record_id)` | Integer ID of the target city record. |

---

### Table: `dim_stations`
Subtype table storing monitoring station metadata.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `station_id` | `VARCHAR(100)`| `PRIMARY KEY` | Original CPCB station identifier (e.g., `"AP001"`). |
| `city_record_id`| `INTEGER` | `FOREIGN KEY` references `dim_cities(city_record_id)` | Foreign key linking station to its city record. |
| `station_name`| `VARCHAR(255)`| `NOT NULL` | Station name / address description (e.g., `"Secretariat, Amaravati - APPCB"`). |
| `status` | `VARCHAR(50)` | None | Operation status (e.g., `"Active"`, `"Unknown"`). |

---

### Table: `dim_agency_registry` [NEW]
Setup table storing agent names, assigned schemas, and folder drop locations.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `agent_id` | `INTEGER` | `PRIMARY KEY`, `AUTOINCREMENT` | Unique agent setup ID. |
| `agent_name` | `VARCHAR(100)` | `UNIQUE`, `NOT NULL` | Agent identifier (e.g., `"Agent1"`, `"Agent2"`). |
| `supported_schema`| `VARCHAR(50)` | `NOT NULL` | Schema structure (`"SchemaA"` or `"SchemaB"`). |
| `drop_location` | `VARCHAR(500)`| `NOT NULL` | Folder path where agent drops inbound files. |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Active status flag. |

---

### Table: `fact_ingestion_logs` [NEW]
Audit log table recording multi-agent execution runs, archiving locations, and error details.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `log_id` | `INTEGER` | `PRIMARY KEY`, `AUTOINCREMENT` | Unique audit log entry ID. |
| `agent_name` | `VARCHAR(100)` | `NOT NULL` | Agent name. |
| `schema_used` | `VARCHAR(50)` | `NOT NULL` | Schema used (`"SchemaA"` or `"SchemaB"`). |
| `file_name` | `VARCHAR(255)` | `NOT NULL` | Name of the inbound file. |
| `drop_location` | `VARCHAR(500)`| `NOT NULL` | Original folder drop location. |
| `archive_location`| `VARCHAR(500)`| `NOT NULL` | Folder path where file was archived post-processing. |
| `total_rows` | `INTEGER` | `NOT NULL` | Total rows found in file. |
| `processed_rows` | `INTEGER` | `NOT NULL` | Clean rows inserted into `fact_readings`. |
| `rejected_rows` | `INTEGER` | `NOT NULL` | Invalid rows rejected. |
| `status` | `VARCHAR(50)` | `NOT NULL` | Processing status (`"Completed"`, `"Partial Success"`, `"Failed"`). |
| `timestamp` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Run timestamp. |
| `error_details` | `TEXT` | `NULL` | Formatted rejection error messages. |

---

### Table: `fact_readings`
Unified fact table storing daily pollutant and AQI measurements for both cities and stations.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `reading_id` | `INTEGER` | `PRIMARY KEY`, `AUTOINCREMENT` | Unique identifier for each daily reading record. |
| `location_id` | `INTEGER` | `FOREIGN KEY` references `dim_locations(location_id)` | Integer location ID (city or station). |
| `date` | `DATE` | `NOT NULL` | Date of the reading (Format: `YYYY-MM-DD`). |
| `pm25` | `FLOAT` | None | Daily average concentration of PM2.5 (µg/m³). |
| `pm10` | `FLOAT` | None | Daily average concentration of PM10 (µg/m³). |
| `no2` | `FLOAT` | None | Daily average concentration of NO2 (µg/m³). |
| `co` | `FLOAT` | None | Daily average concentration of Carbon Monoxide (mg/m³). |
| `so2` | `FLOAT` | None | Daily average concentration of SO2 (µg/m³). |
| `o3` | `FLOAT` | None | Daily average concentration of Ozone (µg/m³). |
| `aqi` | `FLOAT` | None | Daily Air Quality Index value. |
| `is_reliable` | `BOOLEAN` | `DEFAULT TRUE` | Reliability flag (set to `FALSE` for anomalies/stuck sensors). |

*Query Optimization Index*: `idx_readings_loc_date` on `(location_id, date)`.
