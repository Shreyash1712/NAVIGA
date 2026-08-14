import sqlite3
import pandas as pd
import numpy as np

db_path = "/Users/shreyashpagia/Desktop/NAVIGAS/air_quality.db"

def run_seasonal_swing_sql(conn):
    query = """
    WITH CitySeasons AS (
        SELECT 
            c.city_name,
            AVG(CASE WHEN strftime('%m', r.date) IN ('11', '12', '01', '02') THEN r.pm25 END) AS winter_avg,
            AVG(CASE WHEN strftime('%m', r.date) IN ('04', '05', '06') THEN r.pm25 END) AS summer_avg
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE r.is_reliable = 1 AND l.type = 'city' AND r.pm25 IS NOT NULL
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.city_name
    )
    SELECT 
        city_name,
        winter_avg,
        summer_avg,
        (winter_avg - summer_avg) AS seasonal_swing
    FROM CitySeasons
    WHERE winter_avg IS NOT NULL AND summer_avg IS NOT NULL
    ORDER BY seasonal_swing DESC
    LIMIT 5;
    """
    return pd.read_sql_query(query, conn)

def run_weighted_aqi_sql(conn):
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
        s.state_name,
        SUM(m.avg_city_aqi * m.population) / SUM(m.population) AS weighted_aqi
    FROM MonthlyCityAQI m
    JOIN dim_states s ON m.state_code = s.state_code
    GROUP BY s.state_code
    ORDER BY weighted_aqi DESC, s.state_name ASC;
    """
    return pd.read_sql_query(query, conn)

def validate_seasonal_swing_pandas(conn):
    readings = pd.read_sql_query("SELECT * FROM fact_readings WHERE is_reliable = 1 AND pm25 IS NOT NULL", conn)
    locations = pd.read_sql_query("SELECT * FROM dim_locations WHERE type = 'city'", conn)
    cities = pd.read_sql_query("SELECT * FROM dim_cities", conn)
    
    readings['date'] = pd.to_datetime(readings['date'])
    cities['start_date'] = pd.to_datetime(cities['start_date'])
    cities['end_date'] = pd.to_datetime(cities['end_date']).fillna(pd.Timestamp('9999-12-31'))
    
    merged = readings.merge(locations, on='location_id')
    merged = merged.merge(cities, left_on='location_id', right_on='city_record_id')
    merged = merged[(merged['date'] >= merged['start_date']) & (merged['date'] <= merged['end_date'])]
    
    merged['month'] = merged['date'].dt.month
    winter = merged[merged['month'].isin([11, 12, 1, 2])]
    summer = merged[merged['month'].isin([4, 5, 6])]
    
    winter_avg = winter.groupby('city_name')['pm25'].mean().rename('winter_avg')
    summer_avg = summer.groupby('city_name')['pm25'].mean().rename('summer_avg')
    
    swing_df = pd.concat([winter_avg, summer_avg], axis=1).dropna()
    swing_df['seasonal_swing'] = swing_df['winter_avg'] - swing_df['summer_avg']
    swing_df = swing_df.sort_values(by='seasonal_swing', ascending=False).head(5).reset_index()
    
    return swing_df[['city_name', 'winter_avg', 'summer_avg', 'seasonal_swing']]

def validate_weighted_aqi_pandas(conn):
    readings = pd.read_sql_query("SELECT * FROM fact_readings WHERE is_reliable = 1 AND aqi IS NOT NULL", conn)
    locations = pd.read_sql_query("SELECT * FROM dim_locations WHERE type = 'city'", conn)
    cities = pd.read_sql_query("SELECT * FROM dim_cities", conn)
    states = pd.read_sql_query("SELECT * FROM dim_states", conn)
    
    readings['date'] = pd.to_datetime(readings['date'])
    cities['start_date'] = pd.to_datetime(cities['start_date'])
    cities['end_date'] = pd.to_datetime(cities['end_date']).fillna(pd.Timestamp('9999-12-31'))
    
    max_date = readings['date'].max()
    latest_ym = max_date.strftime('%Y-%m')
    
    latest_readings = readings[readings['date'].dt.strftime('%Y-%m') == latest_ym]
    
    merged = latest_readings.merge(locations, on='location_id')
    merged = merged.merge(cities, left_on='location_id', right_on='city_record_id')
    merged = merged[(merged['date'] >= merged['start_date']) & (merged['date'] <= merged['end_date'])]
    
    city_aqi = merged.groupby(['state_code', 'city_name', 'population'])['aqi'].mean().rename('avg_city_aqi').reset_index()
    
    def calc_weighted(group):
        total_pop = group['population'].sum()
        if total_pop == 0:
            return np.nan
        return (group['avg_city_aqi'] * group['population']).sum() / total_pop
        
    state_weighted = city_aqi.groupby('state_code').apply(calc_weighted).rename('weighted_aqi').reset_index()
    state_weighted = state_weighted.merge(states, on='state_code').sort_values(by=['weighted_aqi', 'state_name'], ascending=[False, True])
    
    return state_weighted[['state_name', 'weighted_aqi']].dropna().reset_index(drop=True)

def main():
    conn = sqlite3.connect(db_path)
    
    print("====================================================")
    print("1. QUERY 1: SEASONAL SWING (WINTER VS SUMMER PM2.5)")
    print("====================================================")
    sql_swing = run_seasonal_swing_sql(conn)
    print("\n--- SQL Output (Top 5 Cities) ---")
    print(sql_swing.to_string(index=False))
    
    pd_swing = validate_seasonal_swing_pandas(conn)
    print("\n--- Pandas Validation Output ---")
    print(pd_swing.to_string(index=False))
    
    assert len(sql_swing) == len(pd_swing), "Row count mismatch in Seasonal Swing!"
    for i in range(len(sql_swing)):
        assert sql_swing.iloc[i]['city_name'] == pd_swing.iloc[i]['city_name'], f"City mismatch at row {i}!"
        assert abs(sql_swing.iloc[i]['seasonal_swing'] - pd_swing.iloc[i]['seasonal_swing']) < 1e-5, f"Value mismatch at row {i}!"
    print("\n[SUCCESS] Seasonal Swing SQL matches Pandas validation perfectly!")
    
    print("\n====================================================")
    print("2. QUERY 2: POPULATION-WEIGHTED STATE AQI")
    print("====================================================")
    sql_weighted = run_weighted_aqi_sql(conn)
    print("\n--- SQL Output ---")
    print(sql_weighted.to_string(index=False))
    
    pd_weighted = validate_weighted_aqi_pandas(conn)
    print("\n--- Pandas Validation Output ---")
    print(pd_weighted.to_string(index=False))
    
    assert len(sql_weighted) == len(pd_weighted), "Row count mismatch in Population-Weighted AQI!"
    for i in range(len(sql_weighted)):
        assert sql_weighted.iloc[i]['state_name'] == pd_weighted.iloc[i]['state_name'], f"State mismatch at row {i}!"
        assert abs(sql_weighted.iloc[i]['weighted_aqi'] - pd_weighted.iloc[i]['weighted_aqi']) < 1e-5, f"Value mismatch at row {i}!"
    print("\n[SUCCESS] Population-Weighted AQI SQL matches Pandas validation perfectly!")
    
    conn.close()

if __name__ == "__main__":
    main()
