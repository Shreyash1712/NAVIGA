import os
import sys
import shutil
import json
import sqlite3
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "/Users/shreyashpagia/Desktop/NAVIGAS/air_quality.db"
ARCHIVE_DIR = "/Users/shreyashpagia/Desktop/NAVIGAS/data/agency_archive"

# Schema Specifications (2 Core Schemas)
SCHEMA_SPECS = {
    "schemaa": {
        "alias": "schema1",
        "name": "SchemaA (City Reading Schema)",
        "required_cols": ["city_name", "date"],
        "location_col": "city_name",
        "type": "city",
        "pollutant_cols": ["pm25", "pm10", "no2", "co", "so2", "o3", "aqi"]
    },
    "schemab": {
        "alias": "schema2",
        "name": "SchemaB (Station Reading Schema)",
        "required_cols": ["station_id", "date"],
        "location_col": "station_id",
        "type": "station",
        "pollutant_cols": ["pm25", "pm10", "no2", "co", "so2", "o3", "aqi"]
    }
}

def load_valid_locations(conn):
    """Fetch valid city name and station code mappings to their integer location_ids."""
    cursor = conn.cursor()
    # Fetch cities from dim_city_anomalies
    cursor.execute("""
        SELECT a.raw_city_name, a.city_record_id 
        FROM dim_city_anomalies a
    """)
    valid_cities = {row[0].lower(): row[1] for row in cursor.fetchall()}
    
    # Fetch stations
    cursor.execute("SELECT location_id FROM dim_locations WHERE type = 'station' ORDER BY location_id")
    station_loc_ids = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT station_id FROM dim_stations ORDER BY rowid")
    station_codes = [row[0] for row in cursor.fetchall()]
    valid_stations = {code.lower(): loc_id for code, loc_id in zip(station_codes, station_loc_ids)}
    
    return valid_cities, valid_stations

def fetch_agent_setup(db_path=DB_PATH):
    """
    Step 1: Load active agent setup info (agent_name vs supported_schema vs drop_location)
    directly and exclusively from database table dim_agency_registry.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found at: '{db_path}'")
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT agent_name, supported_schema, drop_location FROM dim_agency_registry WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise RuntimeError("No active agent setup records found in database table 'dim_agency_registry'.")
        
    agents = [{"agent_name": r[0], "supported_schema": r[1], "drop_location": r[2]} for r in rows]
    return pd.DataFrame(agents)

def process_single_file(file_path, agent_name, schema_key, conn, valid_cities, valid_stations):
    """
    Step 2: Validates and processes a single file against the assigned schema.
    """
    schema_clean = schema_key.strip().lower().replace(" ", "").replace("_", "").replace("schema1", "schemaa").replace("schema2", "schemab")
    spec = SCHEMA_SPECS.get(schema_clean)
    if not spec:
        raise ValueError(f"Unsupported schema '{schema_key}' for agent '{agent_name}'")
        
    fname_lower = os.path.basename(file_path).lower()
    if "agency_registry" in fname_lower:
        reason = f"File Ignored: '{os.path.basename(file_path)}' is an Agency Registry configuration file, not a reading data file."
        return 0, 0, 0, reason, [], []

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return 0, 0, 1, f"Read Error: {e}", [], [{
            "agent": agent_name,
            "schema": schema_key,
            "file": os.path.basename(file_path),
            "row_index": 0,
            "rejection_reason": f"Read Error: {e}",
            "raw_data": "Unreadable File"
        }]
        
    # Standardize column names
    clean_col_map = {}
    for col in df.columns:
        c_clean = col.strip().lower().replace("pm2.5", "pm25").replace("pm10", "pm10")
        if c_clean in ["city", "city_name", "name_of_city"]:
            clean_col_map[col] = "city_name"
        elif c_clean in ["stationid", "station_id", "station", "station_code"]:
            clean_col_map[col] = "station_id"
        elif c_clean in ["date", "reading_date", "datetime"]:
            clean_col_map[col] = "date"
        else:
            clean_col_map[col] = c_clean
    df = df.rename(columns=clean_col_map)
    
    total_rows = len(df)
    if total_rows == 0:
        return 0, 0, 0, "Empty File: No data rows found", [], []

    missing_req = [c for c in spec['required_cols'] if c not in df.columns]
    if missing_req:
        found_cols = list(df.columns[:5])
        reason = f"Schema Mismatch: Agent '{agent_name}' is assigned {spec['name']} requiring {spec['required_cols']}, but file has columns {found_cols} (Missing {missing_req})"
        rejections = [{
            "agent": agent_name,
            "schema": schema_key,
            "file": os.path.basename(file_path),
            "row_index": i,
            "rejection_reason": reason,
            "raw_data": str(row.to_dict())
        } for i, (_, row) in enumerate(df.iterrows(), 1)]
        return total_rows, 0, total_rows, reason, [], rejections
        
    valid_db_rows = []
    rejected_log_rows = []
    
    for i, (_, row) in enumerate(df.iterrows(), 1):
        is_row_valid = True
        rejection_reasons = []
        
        # 1. Location ID check
        raw_loc = row.get(spec['location_col'])
        matched_loc_id = None
        if pd.isna(raw_loc) or str(raw_loc).strip() == "":
            is_row_valid = False
            rejection_reasons.append(f"Missing '{spec['location_col']}' value")
        else:
            loc_str = str(raw_loc).strip()
            loc_key = loc_str.lower()
            if spec['type'] == 'city':
                if loc_key not in valid_cities:
                    is_row_valid = False
                    rejection_reasons.append(f"City '{loc_str}' not found in registered dim_cities")
                else:
                    matched_loc_id = valid_cities[loc_key]
            elif spec['type'] == 'station':
                if loc_key not in valid_stations:
                    is_row_valid = False
                    rejection_reasons.append(f"Station ID '{loc_str}' not found in registered dim_stations")
                else:
                    matched_loc_id = valid_stations[loc_key]
                    
        # 2. Date format check
        raw_date = row.get("date")
        parsed_date = None
        if pd.isna(raw_date):
            is_row_valid = False
            rejection_reasons.append("Missing 'date' value")
        else:
            try:
                parsed_date = pd.to_datetime(raw_date).strftime("%Y-%m-%d")
            except Exception:
                is_row_valid = False
                rejection_reasons.append(f"Invalid date format '{raw_date}'")
                
        # 3. Numeric & domain check
        pollutant_vals = {}
        for p in spec['pollutant_cols']:
            val = row.get(p)
            if pd.isna(val) or val == "":
                pollutant_vals[p] = None
            else:
                try:
                    num_v = float(val)
                    if num_v < 0:
                        is_row_valid = False
                        rejection_reasons.append(f"Negative pollutant value {p}={num_v}")
                    else:
                        pollutant_vals[p] = num_v
                except Exception:
                    is_row_valid = False
                    rejection_reasons.append(f"Non-numeric value for {p}='{val}'")
                    
        if is_row_valid:
            valid_db_rows.append((
                matched_loc_id,
                parsed_date,
                pollutant_vals.get('pm25'),
                pollutant_vals.get('pm10'),
                pollutant_vals.get('no2'),
                pollutant_vals.get('co'),
                pollutant_vals.get('so2'),
                pollutant_vals.get('o3'),
                pollutant_vals.get('aqi'),
                1
            ))
        else:
            rejected_log_rows.append({
                "agent": agent_name,
                "schema": schema_key,
                "file": os.path.basename(file_path),
                "row_index": i,
                "rejection_reason": "; ".join(rejection_reasons),
                "raw_data": str(row.to_dict())
            })
            
    processed_count = len(valid_db_rows)
    rejected_count = len(rejected_log_rows)
    err_msg = "; ".join(set([r['rejection_reason'] for r in rejected_log_rows])) if rejected_log_rows else None
    
    return total_rows, processed_count, rejected_count, err_msg, valid_db_rows, rejected_log_rows

def run_multi_agent_pipeline(db_path=DB_PATH):
    """
    Steps 1, 2, & 3:
    1. Scans all drop locations configured for agents in dim_agency_registry DB table.
    2. Validates files against assigned schemas and processes rules.
    3. Archives processed files to data/agency_archive/ and writes audit entries to fact_ingestion_logs table.
    """
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    setup_df = fetch_agent_setup(db_path)
    
    conn = sqlite3.connect(db_path)
    valid_cities, valid_stations = load_valid_locations(conn)
    cursor = conn.cursor()
    
    summary_reports = []
    all_rejections = []
    
    print("\n================================================================================")
    print("               MULTI-AGENT FILE INGESTION & ARCHIVING PIPELINE                  ")
    print("================================================================================\n")
    
    for idx, agent_row in setup_df.iterrows():
        agent_name = str(agent_row.get("agent_name", f"Agent_{idx+1}")).strip()
        schema_key = str(agent_row.get("supported_schema", "SchemaA")).strip()
        drop_loc = str(agent_row.get("drop_location", "")).strip()
        
        print(f"[SCANNING] {agent_name} | Schema: {schema_key} | Drop Location: '{drop_loc}'")
        
        if not os.path.exists(drop_loc):
            if not drop_loc.lower().endswith(".csv"):
                try:
                    os.makedirs(drop_loc, exist_ok=True)
                except Exception:
                    pass

        if not os.path.exists(drop_loc):
            print(f"  └─ [WARNING] Drop location '{drop_loc}' does not exist. Skipping.")
            summary_reports.append({
                "agent_name": agent_name,
                "supported_schema": schema_key,
                "drop_location": drop_loc,
                "file_name": "N/A",
                "total_rows": 0,
                "processed_rows": 0,
                "rejected_rows": 0,
                "status": "Directory Not Found"
            })
            continue
            
        # Scan files in drop location (if drop_loc is a directory)
        if os.path.isdir(drop_loc):
            files = [os.path.join(drop_loc, f) for f in os.listdir(drop_loc) if f.endswith('.csv')]
        else:
            files = [drop_loc] if os.path.exists(drop_loc) else []
            
        if not files:
            print("  └─ [INFO] No pending files found in drop location.")
            summary_reports.append({
                "agent_name": agent_name,
                "supported_schema": schema_key,
                "drop_location": drop_loc,
                "file_name": "No Files Found",
                "total_rows": 0,
                "processed_rows": 0,
                "rejected_rows": 0,
                "status": "No Pending Files"
            })
            continue
            
        for file_path in files:
            fname = os.path.basename(file_path)
            print(f"  └─ [PROCESSING FILE] '{fname}'...")
            
            tot, proc, rej, errs, valid_rows, rejections = process_single_file(
                file_path, agent_name, schema_key, conn, valid_cities, valid_stations
            )
            
            # Insert valid rows into fact_readings
            if valid_rows:
                cursor.executemany("""
                    INSERT INTO fact_readings (location_id, date, pm25, pm10, no2, co, so2, o3, aqi, is_reliable)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, valid_rows)
                conn.commit()
                
            # Step 3: Archive file to data/agency_archive/
            time_stamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
            archived_fname = f"{time_stamp_prefix}_{agent_name}_{fname}"
            archive_path = os.path.join(ARCHIVE_DIR, archived_fname)
            
            try:
                shutil.move(file_path, archive_path)
                print(f"     └─ [ARCHIVED] Moved file to: '{archive_path}'")
            except Exception as archive_err:
                print(f"     └─ [WARNING] Could not move file to archive: {archive_err}")
                archive_path = file_path # Keep original path if move fails
                
            # Log into fact_ingestion_logs table
            status_str = "Completed" if rej == 0 else ("Partial Success" if proc > 0 else "Failed")
            now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO fact_ingestion_logs 
                (agent_name, schema_used, file_name, drop_location, archive_location, total_rows, processed_rows, rejected_rows, status, timestamp, error_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_name, schema_key, fname, drop_loc, archive_path, tot, proc, rej, status_str, now_ts, errs))
            conn.commit()
            
            summary_reports.append({
                "agent_name": agent_name,
                "supported_schema": schema_key,
                "drop_location": drop_loc,
                "file_name": fname,
                "archive_location": archive_path,
                "total_rows": tot,
                "processed_rows": proc,
                "rejected_rows": rej,
                "status": status_str
            })
            all_rejections.extend(rejections)
            
    conn.close()
    
    summary_df = pd.DataFrame(summary_reports)
    rejected_df = pd.DataFrame(all_rejections) if all_rejections else pd.DataFrame(columns=["agent", "schema", "file", "row_index", "rejection_reason", "raw_data"])
    
    print("\n--------------------------------------------------------------------------------")
    print("                            PROCESSING SUMMARY REPORT                            ")
    print("--------------------------------------------------------------------------------")
    print(summary_df.to_string(index=False))
    print("--------------------------------------------------------------------------------\n")
    
    if not rejected_df.empty:
        print("--------------------------------------------------------------------------------")
        print("                            ALL REJECTED DATA ROWS                              ")
        print("--------------------------------------------------------------------------------")
        for i, r in rejected_df.iterrows():
            print(f"[{i+1}] Agent: {r['agent']} | File: {r['file']} | Row #{r['row_index']}")
            print(f"    Reason(s): {r['rejection_reason']}")
            print(f"    Raw Data:  {r['raw_data']}\n")
        print("--------------------------------------------------------------------------------\n")
        
    return summary_df, rejected_df

def validate_and_ingest_agency_data(db_path=DB_PATH):
    """
    Backward-compatible wrapper for Streamlit UI and CLI calls.
    """
    return run_multi_agent_pipeline(db_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent File Ingestion & Archiving Pipeline")
    parser.add_argument("--db", type=str, default=DB_PATH, help="Path to SQLite database file")
    args = parser.parse_args()
    
    run_multi_agent_pipeline(args.db)
