import sqlite3

db_path = "/Users/shreyashpagia/Desktop/NAVIGAS/air_quality.db"

def run_tests():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- 1. Table Row Counts ---")
    tables = {
        "dim_states": 30,
        "dim_locations": 760,
        "dim_cities": 530,
        "dim_city_anomalies": 535,
        "dim_stations": 230,
        "dim_agency_registry": 3
    }
    for t, expected in tables.items():
        cursor.execute(f"SELECT COUNT(*) FROM {t}")
        count = cursor.fetchone()[0]
        print(f"  Table '{t}': {count} rows (Expected {expected})")
        if t == "dim_agency_registry":
            assert count >= expected, f"Row count mismatch for {t}: expected at least {expected}, got {count}"
        else:
            assert count == expected, f"Row count mismatch for {t}: expected {expected}, got {count}"
        
    cursor.execute("SELECT COUNT(*) FROM fact_ingestion_logs")
    log_count = cursor.fetchone()[0]
    print(f"  Table 'fact_ingestion_logs': {log_count} log entries recorded.")
    assert log_count >= 3, f"Expected at least 3 log entries, got {log_count}"
        
    print("\n--- 2. Foreign Key Integrity Check (fact_readings -> dim_locations) ---")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM fact_readings r
        LEFT JOIN dim_locations l ON r.location_id = l.location_id
        WHERE l.location_id IS NULL
    """)
    orphan_readings = cursor.fetchone()[0]
    print(f"  Orphan rows in fact_readings (no matching location in dim_locations): {orphan_readings}")
    
    print("\n--- 3. Foreign Key Integrity Check (dim_locations parent_id check for stations) ---")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM dim_locations ls
        LEFT JOIN dim_locations lc ON ls.parent_id = lc.location_id
        WHERE ls.type = 'station' AND lc.location_id IS NULL
    """)
    orphan_station_parents = cursor.fetchone()[0]
    print(f"  Orphan rows in dim_locations (station parent_id not found in city locations): {orphan_station_parents}")
    
    print("\n--- 4. Foreign Key Integrity Check (dim_cities -> dim_states) ---")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM dim_cities c
        LEFT JOIN dim_states s ON c.state_code = s.state_code
        WHERE s.state_code IS NULL
    """)
    orphan_states = cursor.fetchone()[0]
    print(f"  Orphan rows in dim_cities (no matching state in dim_states): {orphan_states}")
    
    print("\n--- 5. Foreign Key Integrity Check (dim_city_anomalies -> dim_cities) ---")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM dim_city_anomalies a
        LEFT JOIN dim_cities c ON a.city_record_id = c.city_record_id
        WHERE c.city_record_id IS NULL
    """)
    orphan_anomalies = cursor.fetchone()[0]
    print(f"  Orphan rows in dim_city_anomalies (no matching city in dim_cities): {orphan_anomalies}")
    
    print("\n--- 6. Foreign Key Integrity Check (dim_stations -> dim_cities city_record_id) ---")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM dim_stations s
        LEFT JOIN dim_cities c ON s.city_record_id = c.city_record_id
        WHERE c.city_record_id IS NULL
    """)
    orphan_station_cities = cursor.fetchone()[0]
    print(f"  Orphan rows in dim_stations (no matching city in dim_cities): {orphan_station_cities}")
    
    print("\n--- 6. City Anomaly Resolution Test ---")
    test_variations = ['Ahmadabad', 'Gurgaon', 'Greater Mumbai', 'Amravati', 'Ahmedabad']
    for var in test_variations:
        cursor.execute("""
            SELECT a.raw_city_name, a.city_record_id, c.city_name
            FROM dim_city_anomalies a
            JOIN dim_cities c ON a.city_record_id = c.city_record_id
            WHERE a.raw_city_name = ?
        """, (var,))
        row = cursor.fetchone()
        if row:
            print(f"  Raw: '{row[0]}' -> City Record ID: {row[1]}, Standard: '{row[2]}'")
            
    print("\n--- 7. Check Query Indexes ---")
    cursor.execute("PRAGMA index_list('fact_readings')")
    indexes = cursor.fetchall()
    print("  Indexes on fact_readings:")
    for idx in indexes:
        print(f"    {idx[1]} (Unique={idx[2]})")
        
    print("\n--- 8. Redesigned Sample Join Query ---")
    cursor.execute("""
        SELECT c.city_name, s.state_name, c.population, AVG(r.aqi) as avg_aqi
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        JOIN dim_states s ON c.state_code = s.state_code
        WHERE r.is_reliable = 1 AND r.aqi IS NOT NULL AND l.type = 'city'
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.city_name
        LIMIT 5
    """)
    results = cursor.fetchall()
    for row in results:
        print(f"  City: {row[0]}, State: {row[1]}, Population: {row[2]}, Avg AQI: {row[3]:.2f}")
        
    conn.close()
    
    # Assertions
    assert orphan_readings == 0, f"Expected 0 orphan readings, got {orphan_readings}"
    assert orphan_station_parents == 0, f"Expected 0 orphan station parent links, got {orphan_station_parents}"
    assert orphan_states == 0, f"Expected 0 orphan states, got {orphan_states}"
    assert orphan_anomalies == 0, f"Expected 0 orphan anomalies, got {orphan_anomalies}"
    assert orphan_station_cities == 0, f"Expected 0 orphan station city links, got {orphan_station_cities}"
    print("\nAll database integration tests passed successfully with dim_city_anomalies!")

if __name__ == "__main__":
    run_tests()
