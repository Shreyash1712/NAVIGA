import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db_schema import Base, State, Location, City, CityAnomaly, Station, Reading, AgencyRegistry, IngestionLog

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")



def clean_columns(df):
    """
    Standardize DataFrame column names: lowercase, strip, replace PM2.5/PM10 with pm25/pm10
    """
    rename_dict = {}
    for col in df.columns:
        clean_name = col.strip().lower()
        clean_name = clean_name.replace("pm2.5", "pm25").replace("pm10", "pm10")
        rename_dict[col] = clean_name
    return df.rename(columns=rename_dict)

def flag_reliability(df, group_col):
    """
    Flag records as unreliable if they meet any of the following:
    1. PM2.5 or AQI flatlines (stuck values) for 3+ consecutive days.
    2. AQI exceeds 500 (standard limit) or PM2.5/PM10 is exactly 1000 (sensor saturation).
    3. Physically impossible negative concentration values.
    """
    df['is_reliable'] = True
    df = df.sort_values(by=[group_col, 'date'])
    
    pm25_prev1 = df.groupby(group_col)['pm25'].shift(1)
    pm25_prev2 = df.groupby(group_col)['pm25'].shift(2)
    pm25_stuck = (df['pm25'].notnull()) & (df['pm25'] == pm25_prev1) & (df['pm25'] == pm25_prev2)
    
    aqi_prev1 = df.groupby(group_col)['aqi'].shift(1)
    aqi_prev2 = df.groupby(group_col)['aqi'].shift(2)
    aqi_stuck = (df['aqi'].notnull()) & (df['aqi'] == aqi_prev1) & (df['aqi'] == aqi_prev2)
    
    impossible_aqi = (df['aqi'] > 500)
    saturated_pm25 = (df['pm25'] == 1000.0)
    saturated_pm10 = (df['pm10'] == 1000.0)
    
    pollutant_cols = ['pm25', 'pm10', 'no2', 'co', 'so2', 'o3', 'aqi']
    negative_values = pd.Series(False, index=df.index)
    for col in pollutant_cols:
        if col in df.columns:
            negative_values = negative_values | (df[col] < 0)
            
    anomaly_mask = pm25_stuck | aqi_stuck | impossible_aqi | saturated_pm25 | saturated_pm10 | negative_values
    df.loc[anomaly_mask, 'is_reliable'] = False
    
    total_anomalies = anomaly_mask.sum()
    logger.info(f"  Anomaly flag stats for {group_col}:")
    logger.info(f"    Stuck PM2.5 count: {pm25_stuck.sum()}")
    logger.info(f"    Stuck AQI count: {aqi_stuck.sum()}")
    logger.info(f"    Impossible AQI (>500) count: {impossible_aqi.sum()}")
    logger.info(f"    Saturated pollutants (=1000) count: {(saturated_pm25 | saturated_pm10).sum()}")
    logger.info(f"    Negative values count: {negative_values.sum()}")
    logger.info(f"    Total unreliable rows flagged: {total_anomalies} ({total_anomalies/len(df)*100:.2f}%)")
    
    return df

def interpolate_column(series, max_gap=2):
    """
    Applies linear interpolation on a Pandas Series, but only fills gaps
    of size <= max_gap. Gaps larger than max_gap are left unchanged.
    """
    is_na = series.isna()
    na_blocks = (is_na != is_na.shift()).cumsum()
    block_sizes = is_na.groupby(na_blocks).transform('sum')
    
    interpolated = series.interpolate(method='linear')
    interpolated[is_na & (block_sizes > max_gap)] = np.nan
    return interpolated

def interpolate_short_gaps(df, group_col, cols_to_interpolate, max_gap=2):
    df = df.sort_values(by=[group_col, 'date']).copy()
    for col in cols_to_interpolate:
        if col in df.columns:
            df[col] = df.groupby(group_col)[col].transform(lambda x: interpolate_column(x, max_gap))
    return df

def clean_and_interpolate_readings(df, group_col):
    initial_len = len(df)
    df = df.drop_duplicates(subset=[group_col, 'date'])
    dups_removed = initial_len - len(df)
    if dups_removed > 0:
        logger.info(f"  Removed {dups_removed} duplicate records.")
        
    df = flag_reliability(df, group_col)
    
    pollutant_cols = ['pm25', 'pm10', 'no2', 'co', 'so2', 'o3', 'aqi']
    for col in pollutant_cols:
        if col in df.columns:
            df.loc[~df['is_reliable'], col] = np.nan
            
    logger.info("  Applying linear interpolation for gaps <= 2 days...")
    for col in ['pm25', 'pm10', 'aqi']:
        if col in df.columns:
            original_nans = df[col].isna().sum()
            df = interpolate_short_gaps(df, group_col, [col], max_gap=2)
            new_nans = df[col].isna().sum()
            logger.info(f"    {col}: Imputed {original_nans - new_nans} missing values.")
            
    return df

def main():
    default_db_path = "/Users/shreyashpagia/Desktop/NAVIGAS/air_quality.db"
    db_url = os.getenv("DATABASE_URL", f"sqlite:///{default_db_path}")
    logger.info(f"Connecting to database: {db_url}")
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    logger.info("Dropping and recreating all tables...")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    
    pop_df = pd.read_csv(os.path.join(DATA_DIR, "cities_population.csv"))
    stations_df = pd.read_csv(os.path.join(DATA_DIR, "stations.csv"))
    city_readings_df = pd.read_csv(os.path.join(DATA_DIR, "city_day.csv"))
    station_readings_df = pd.read_csv(os.path.join(DATA_DIR, "station_day.csv"))
    
    for df in [pop_df, stations_df, city_readings_df, station_readings_df]:
        for col in df.select_dtypes(include='object').columns:
            df[col] = df[col].str.strip()
            
    # ----------------------------------------------------
    # 1. Ingest dim_states
    # ----------------------------------------------------
    logger.info("Ingesting dim_states...")
    states_data = pop_df[['state_code', 'state_name']].drop_duplicates().copy()
    states_data['state_name'] = states_data['state_name'].str.title()
    states_data['state_name'] = states_data['state_name'].replace({
        "Orissa": "Odisha",
        "Nct Of Delhi": "Delhi"
    })
    
    if 36 not in states_data['state_code'].values:
        states_data = pd.concat([states_data, pd.DataFrame([{'state_code': 36, 'state_name': 'Telangana'}])], ignore_index=True)
        
    states_dict = states_data.to_dict(orient='records')
    session.bulk_insert_mappings(State, states_dict)
    session.commit()
    logger.info(f"Successfully ingested {len(states_dict)} records into dim_states.")
    
    state_name_to_code = {s['state_name'].lower(): s['state_code'] for s in states_dict}
    state_name_to_code['orissa'] = 21
    state_name_to_code['odisha'] = 21
    state_name_to_code['delhi'] = 7
    state_name_to_code['nct of delhi'] = 7
    state_name_to_code['telangana'] = 36
    
    # ----------------------------------------------------
    # 2. Ingest dim_locations & dim_cities
    # ----------------------------------------------------
    logger.info("Ingesting dim_locations and dim_cities (Temporal)...")
    
    pop_df = pop_df.drop_duplicates(subset=['name_of_city']).copy()
    pop_df = pop_df.rename(columns={
        'name_of_city': 'city_name',
        'population_total': 'population',
        'effective_literacy_rate_total': 'literacy_rate',
        'sex_ratio': 'sex_ratio'
    })
    
    cities_map = {}
    for _, row in pop_df.iterrows():
        name = row['city_name']
        cities_map[name.lower()] = {
            'city_name': name,
            'state_code': row['state_code'],
            'population': row['population'],
            'literacy_rate': row['literacy_rate'] if pd.notnull(row['literacy_rate']) else None,
            'sex_ratio': row['sex_ratio'] if pd.notnull(row['sex_ratio']) else None
        }
        
    alt_spelling_seeds = {
        "ahmedabad": "ahmadabad",
        "amaravati": "amravati",
        "gurugram": "gurgaon",
        "hyderabad": "greater hyderabad",
        "mumbai": "greater mumbai"
    }

    unique_stations_cities = stations_df[['City', 'State']].drop_duplicates()
    for _, row in unique_stations_cities.iterrows():
        raw_city = row['City']
        raw_state = row['State']
        city_key = raw_city.lower()
        
        if city_key not in cities_map and city_key not in alt_spelling_seeds:
            state_code = state_name_to_code.get(raw_state.lower(), 28)
            cities_map[city_key] = {
                'city_name': raw_city,
                'state_code': state_code,
                'population': 0,
                'literacy_rate': None,
                'sex_ratio': None
            }
            
    # Add cities to dim_locations (parent_id = None, type = 'city')
    city_locations = []
    for c_key, c_info in cities_map.items():
        loc = Location(parent_id=None, type='city')
        session.add(loc)
        city_locations.append((c_info['city_name'].lower(), loc))
        
    session.flush()
    
    # Ingest dim_cities
    start_date_val = datetime.strptime('2011-01-01', '%Y-%m-%d').date()
    cities_to_insert = []
    for c_key, c_info in cities_map.items():
        cities_to_insert.append(City(
            city_name=c_info['city_name'],
            state_code=c_info['state_code'],
            population=c_info['population'],
            literacy_rate=c_info['literacy_rate'],
            sex_ratio=c_info['sex_ratio'],
            start_date=start_date_val,
            end_date=None
        ))
    session.add_all(cities_to_insert)
    session.flush()
    
    # ----------------------------------------------------
    # 2b. Ingest dim_city_anomalies
    # ----------------------------------------------------
    logger.info("Ingesting dim_city_anomalies...")
    city_record_map = {c.city_name.lower(): c.city_record_id for c in cities_to_insert}
    
    anomalies_to_insert = []
    seen_anomalies = set()
    
    for c_obj in cities_to_insert:
        if c_obj.city_name.lower() not in seen_anomalies:
            seen_anomalies.add(c_obj.city_name.lower())
            anomalies_to_insert.append(CityAnomaly(
                raw_city_name=c_obj.city_name,
                city_record_id=c_obj.city_record_id
            ))
        
    for alt_raw, census_std in alt_spelling_seeds.items():
        if alt_raw not in seen_anomalies and census_std in city_record_map:
            seen_anomalies.add(alt_raw)
            anomalies_to_insert.append(CityAnomaly(
                raw_city_name=alt_raw.title(),
                city_record_id=city_record_map[census_std]
            ))
            
    session.add_all(anomalies_to_insert)
    session.flush()
    logger.info(f"Successfully ingested {len(anomalies_to_insert)} records into dim_city_anomalies.")
    
    # Create lookup map using dim_city_anomalies DB table
    city_anomalies = session.query(CityAnomaly).all()
    city_loc_map = {a.raw_city_name.lower(): a.city_record_id for a in city_anomalies}
    
    # ----------------------------------------------------
    # 3. Ingest dim_stations
    # ----------------------------------------------------
    logger.info("Ingesting stations...")
    stations_df = clean_columns(stations_df)
    stations_df['status'] = stations_df['status'].fillna('Unknown')
    
    # Add stations to dim_locations (parent_id = city_loc_id, type = 'station')
    station_locations = []
    for _, row in stations_df.iterrows():
        parent_city_loc_id = city_loc_map[row['city'].lower()]
        loc = Location(parent_id=parent_city_loc_id, type='station')
        session.add(loc)
        station_locations.append((row['stationid'].lower(), loc))
        
    session.flush()
    station_loc_map = {code: loc.location_id for code, loc in station_locations}
    
    # Ingest dim_stations (station_id PK string, city_record_id FK, station_name, status)
    stations_to_insert = []
    for _, row in stations_df.iterrows():
        parent_city_id = city_loc_map[row['city'].lower()]
        stations_to_insert.append(Station(
            station_id=row['stationid'],
            city_record_id=parent_city_id,
            station_name=row['stationname'],
            status=row['status']
        ))
    session.add_all(stations_to_insert)
    session.flush()
    
    session.commit()
    logger.info(f"Successfully populated dim_locations, dim_cities, and dim_stations under Part 4 design.")
    
    # ----------------------------------------------------
    # 3b. Ingest dim_agency_registry (Agent Setup Table)
    # ----------------------------------------------------
    logger.info("Ingesting dim_agency_registry setup table...")
    setup_records = [
        AgencyRegistry(agent_name="Agent1", supported_schema="SchemaA", drop_location="/Users/shreyashpagia/Desktop/NAVIGAS/data/IBLocationA", is_active=True),
        AgencyRegistry(agent_name="Agent2", supported_schema="SchemaB", drop_location="/Users/shreyashpagia/Desktop/NAVIGAS/data/IBLocationB", is_active=True),
        AgencyRegistry(agent_name="Agent3", supported_schema="SchemaA", drop_location="/Users/shreyashpagia/Desktop/NAVIGAS/data/IBLocationC", is_active=True),
    ]
    session.add_all(setup_records)
    session.flush()
    session.commit()
    logger.info(f"Successfully populated {len(setup_records)} setup records in dim_agency_registry.")
    
    # ----------------------------------------------------
    # 4. Ingest fact_readings (Merged Facts)
    # ----------------------------------------------------
    logger.info("Ingesting fact_readings...")
    
    # 4a. Process City Readings
    logger.info("Processing city daily readings...")
    city_readings_df = clean_columns(city_readings_df)
    city_readings_df['date'] = pd.to_datetime(city_readings_df['date']).dt.date
    city_readings_df = clean_and_interpolate_readings(city_readings_df, 'city')
    
    readings_to_insert = []
    for _, row in city_readings_df.iterrows():
        city_loc_id = city_loc_map.get(row['city'].lower())
        if not city_loc_id:
            continue
        readings_to_insert.append({
            'location_id': city_loc_id,
            'date': row['date'],
            'pm25': row['pm25'] if pd.notnull(row['pm25']) else None,
            'pm10': row['pm10'] if pd.notnull(row['pm10']) else None,
            'no2': row['no2'] if pd.notnull(row['no2']) else None,
            'co': row['co'] if pd.notnull(row['co']) else None,
            'so2': row['so2'] if pd.notnull(row['so2']) else None,
            'o3': row['o3'] if pd.notnull(row['o3']) else None,
            'aqi': row['aqi'] if pd.notnull(row['aqi']) else None,
            'is_reliable': bool(row['is_reliable'])
        })
        
    # 4b. Process Station Readings
    logger.info("Processing station daily readings...")
    station_readings_df = clean_columns(station_readings_df)
    station_readings_df['date'] = pd.to_datetime(station_readings_df['date']).dt.date
    station_readings_df = clean_and_interpolate_readings(station_readings_df, 'stationid')
    
    for _, row in station_readings_df.iterrows():
        station_loc_id = station_loc_map.get(row['stationid'].lower())
        if not station_loc_id:
            continue
        readings_to_insert.append({
            'location_id': station_loc_id,
            'date': row['date'],
            'pm25': row['pm25'] if pd.notnull(row['pm25']) else None,
            'pm10': row['pm10'] if pd.notnull(row['pm10']) else None,
            'no2': row['no2'] if pd.notnull(row['no2']) else None,
            'co': row['co'] if pd.notnull(row['co']) else None,
            'so2': row['so2'] if pd.notnull(row['so2']) else None,
            'o3': row['o3'] if pd.notnull(row['o3']) else None,
            'aqi': row['aqi'] if pd.notnull(row['aqi']) else None,
            'is_reliable': bool(row['is_reliable'])
        })
        
    chunk_size = 5000
    for i in range(0, len(readings_to_insert), chunk_size):
        chunk = readings_to_insert[i:i+chunk_size]
        session.bulk_insert_mappings(Reading, chunk)
    session.commit()
    logger.info(f"Successfully ingested {len(readings_to_insert)} records into fact_readings.")
    
    session.close()
    logger.info("Database ingestion pipeline finished successfully under Part 4 schema design!")

if __name__ == "__main__":
    main()
