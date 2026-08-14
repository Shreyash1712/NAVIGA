from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class State(Base):
    """
    Dimension table for State metadata. Normalises dim_cities to 3NF.
    """
    __tablename__ = 'dim_states'
    
    state_code = Column(Integer, primary_key=True)
    state_name = Column(String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<State(code={self.state_code}, name='{self.state_name}')>"


class Location(Base):
    """
    Unified Supertype table registering all unique geographic locations (cities and stations).
    Contains self-referential parent_id linking stations to their parent city location_id.
    """
    __tablename__ = 'dim_locations'
    
    location_id = Column(Integer, primary_key=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey('dim_locations.location_id'), nullable=True) # NULL for cities, parent city location_id for stations
    type = Column(String(20), nullable=False) # 'city' or 'station'

    def __repr__(self):
        return f"<Location(id={self.location_id}, parent_id={self.parent_id}, type='{self.type}')>"


class City(Base):
    """
    Subtype table for city metadata and demographics.
    """
    __tablename__ = 'dim_cities'
    
    city_record_id = Column(Integer, primary_key=True, autoincrement=True)
    city_name = Column(String(100), nullable=False)
    state_code = Column(Integer, ForeignKey('dim_states.state_code'), nullable=False)
    population = Column(Integer, nullable=False)
    literacy_rate = Column(Float)
    sex_ratio = Column(Integer)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True) # NULL means currently active

    def __repr__(self):
        return f"<City(record_id={self.city_record_id}, city_name='{self.city_name}', population={self.population})>"


class CityAnomaly(Base):
    """
    Dimension table storing raw city name variations/anomalies (e.g. Ahmadabad, Gurgaon)
    and mapping them to their normalized city_record_id in dim_cities.
    Satisfies BCNF (raw_city_name is Candidate Key).
    """
    __tablename__ = 'dim_city_anomalies'
    
    raw_city_name = Column(String(100), primary_key=True)
    city_record_id = Column(Integer, ForeignKey('dim_cities.city_record_id'), nullable=False)

    def __repr__(self):
        return f"<CityAnomaly(raw='{self.raw_city_name}', record_id={self.city_record_id})>"


class Station(Base):
    """
    Subtype table for monitoring station metadata. Keyed by station_id string (e.g. AP001), linked to dim_cities via city_record_id.
    """
    __tablename__ = 'dim_stations'
    
    station_id = Column(String(100), primary_key=True)
    city_record_id = Column(Integer, ForeignKey('dim_cities.city_record_id'), nullable=False)
    station_name = Column(String(255), nullable=False)
    status = Column(String(50))

    def __repr__(self):
        return f"<Station(id='{self.station_id}', city_record_id={self.city_record_id}, name='{self.station_name}', status='{self.status}')>"


class AgencyRegistry(Base):
    """
    Setup table storing agent mappings (agent_name vs supported_schema vs drop_location).
    Allows adding new agents dynamically without code modifications.
    """
    __tablename__ = 'dim_agency_registry'
    
    agent_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(100), unique=True, nullable=False)
    supported_schema = Column(String(50), nullable=False) # e.g. SchemaA / SchemaB / schema1 / schema2
    drop_location = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<AgencyRegistry(agent='{self.agent_name}', schema='{self.supported_schema}', path='{self.drop_location}')>"


class IngestionLog(Base):
    """
    Audit log table storing post-processing ingestion metrics, archiving info, and error messages.
    """
    __tablename__ = 'fact_ingestion_logs'
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(100), nullable=False)
    schema_used = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    drop_location = Column(String(500), nullable=False)
    archive_location = Column(String(500), nullable=False)
    total_rows = Column(Integer, nullable=False)
    processed_rows = Column(Integer, nullable=False)
    rejected_rows = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=func.now())
    error_details = Column(Text, nullable=True)

    def __repr__(self):
        return f"<IngestionLog(id={self.log_id}, agent='{self.agent_name}', file='{self.file_name}', status='{self.status}')>"


class Reading(Base):
    """
    Unified Fact table storing daily pollutant and AQI measurements for both cities and stations.
    Foreign key constrained to dim_locations using location_id.
    """
    __tablename__ = 'fact_readings'
    
    reading_id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey('dim_locations.location_id'), nullable=False)
    date = Column(Date, nullable=False)
    pm25 = Column(Float)
    pm10 = Column(Float)
    no2 = Column(Float)
    co = Column(Float)
    so2 = Column(Float)
    o3 = Column(Float)
    aqi = Column(Float)
    is_reliable = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_readings_loc_date', 'location_id', 'date'),
    )

    def __repr__(self):
        return f"<Reading(location_id={self.location_id}, date={self.date}, AQI={self.aqi})>"
