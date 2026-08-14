import os
import sqlite3
import pandas as pd

def run_analytical_query_2(db_path="/Users/shreyashpagia/Desktop/NAVIGAS/air_quality.db"):
    """
    Executes Standalone Analytical Query 2:
    Population-Weighted Average State AQI for the most recent complete month (July 2020).
    Saves and returns the output dataframe.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found at '{db_path}'")

    conn = sqlite3.connect(db_path)
    
    query = """
    WITH LatestMonth AS (
        SELECT strftime('%Y-%m', MAX(date)) AS ym FROM fact_readings
    ),
    MonthlyCityAQI AS (
        SELECT 
            c.state_code,
            c.city_name,
            c.population,
            AVG(r.aqi) AS avg_city_aqi
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE r.is_reliable = 1 AND l.type = 'city' AND r.aqi IS NOT NULL
          AND strftime('%Y-%m', r.date) = (SELECT ym FROM LatestMonth)
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.state_code, c.city_name, c.population
    )
    SELECT 
        s.state_name AS State,
        ROUND(SUM(m.avg_city_aqi * m.population) / SUM(m.population), 2) AS Weighted_Average_AQI,
        COUNT(m.city_name) AS Reporting_Cities_Count,
        SUM(m.population) AS Total_Reporting_Population
    FROM MonthlyCityAQI m
    JOIN dim_states s ON m.state_code = s.state_code
    GROUP BY s.state_code, s.state_name
    ORDER BY Weighted_Average_AQI DESC, s.state_name ASC;
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    output_dir = "/Users/shreyashpagia/Desktop/NAVIGAS/cleaned_data"
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "analytical_query_2_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"[SUCCESS] Standalone Analytical Query 2 executed successfully.")
    print(f"[EXPORT] Results saved to: '{csv_path}'\n")
    return df

if __name__ == "__main__":
    results_df = run_analytical_query_2()
    print(results_df.to_string(index=False))
