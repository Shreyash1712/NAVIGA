import os
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Imports from project modules
from agency_ingest import validate_and_ingest_agency_data, run_multi_agent_pipeline, SCHEMA_SPECS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "air_quality.db")

# Streamlit Page Configuration
st.set_page_config(
    page_title="NAVIGA | Air Quality & Public Data Dashboard",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Glassmorphism & Sleek Dark Accents)
st.markdown("""
<style>
    /* Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 18px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        border-color: #38ef7d;
    }
    .metric-val {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #11998e, #38ef7d);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-lbl {
        font-size: 0.9rem;
        color: #a0aec0;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Header Banner */
    .header-banner {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        padding: 24px;
        border-radius: 14px;
        margin-bottom: 25px;
        color: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    
    /* Badge styling */
    .badge-improving {
        background-color: #2e7d32;
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
    }
    .badge-worsening {
        background-color: #c62828;
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Helper Database Connection
@st.cache_resource
def get_db_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def run_query(query, params=()):
    conn = get_db_connection()
    return pd.read_sql_query(query, conn, params=params)

# Header Banner
st.markdown("""
<div class="header-banner">
    <h1 style="margin:0; font-size: 2.2rem; font-weight:700;">🍃 NAVIGA: Air Quality & Public Data Dashboard</h1>
    <p style="margin:5px 0 0 0; font-size:1.05rem; opacity: 0.9;">
        CPCB Daily Air Quality & 2011 Census Metadata Reporting System (BCNF Relational Architecture)
    </p>
</div>
""", unsafe_allow_html=True)

# Sidebar Navigation
st.sidebar.title("NAVIGA Navigation")
navigation = st.sidebar.radio(
    "Select View / Feature:",
    [
        "📊 Overview & System Health",
        "❄️ Seasonal Swing Analytics",
        "⚖️ Weighted State Rankings",
        "⚠️ Threshold Exceedance Trends",
        "🔍 Station Audit & Reliability",
        "📥 Multi-Agency Ingestion",
        "🔎 Database Explorer"
    ]
)

# Filter options in Sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("Global Filters")
only_reliable = st.sidebar.checkbox("Filter Reliable Data Only (`is_reliable = TRUE`)", value=True)
reliability_clause = "AND r.is_reliable = 1" if only_reliable else ""

# ------------------------------------------------------------------------------
# 1. OVERVIEW & SYSTEM HEALTH
# ------------------------------------------------------------------------------
if navigation == "📊 Overview & System Health":
    st.subheader("📊 System Executive Summary & Data Health Metrics")
    
    # Calculate System Stats
    total_locations = run_query("SELECT COUNT(*) FROM dim_locations").iloc[0,0]
    total_cities = run_query("SELECT COUNT(*) FROM dim_cities").iloc[0,0]
    total_stations = run_query("SELECT COUNT(*) FROM dim_stations").iloc[0,0]
    total_readings = run_query("SELECT COUNT(*) FROM fact_readings").iloc[0,0]
    unreliable_readings = run_query("SELECT COUNT(*) FROM fact_readings WHERE is_reliable = 0").iloc[0,0]
    reliable_rate = ((total_readings - unreliable_readings) / total_readings) * 100 if total_readings > 0 else 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""<div class="metric-card"><div class="metric-val">{total_cities}</div><div class="metric-lbl">Active Cities</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card"><div class="metric-val">{total_stations}</div><div class="metric-lbl">Stations</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card"><div class="metric-val">{total_locations}</div><div class="metric-lbl">Total Locations</div></div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="metric-card"><div class="metric-val">{total_readings:,}</div><div class="metric-lbl">Fact Readings</div></div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""<div class="metric-card"><div class="metric-val">{reliable_rate:.1f}%</div><div class="metric-lbl">Data Reliability</div></div>""", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Timeline overview chart
    st.markdown("### 📈 Historical AQI Trends Across Top Cities")
    top_cities_df = run_query("""
        SELECT c.city_name as city_name, COUNT(r.reading_id) as cnt
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE l.type = 'city' AND r.aqi IS NOT NULL
        GROUP BY c.city_record_id, c.city_name
        ORDER BY cnt DESC
        LIMIT 6
    """)
    top_city_list = top_cities_df['city_name'].tolist()
    
    selected_cities = st.multiselect("Select Cities to Compare:", top_city_list, default=top_city_list[:3])
    
    if selected_cities:
        placeholders = ','.join(['?'] * len(selected_cities))
        timeseries_df = run_query(f"""
            SELECT r.date, c.city_name as city_name, r.aqi, r.pm25
            FROM fact_readings r
            JOIN dim_locations l ON r.location_id = l.location_id
            JOIN dim_cities c ON l.location_id = c.city_record_id
            WHERE l.type = 'city' AND c.city_name IN ({placeholders}) {reliability_clause}
            ORDER BY r.date ASC
        """, params=selected_cities)
        
        timeseries_df['date'] = pd.to_datetime(timeseries_df['date'])
        
        fig = px.line(
            timeseries_df,
            x='date',
            y='aqi',
            color='city_name',
            title="Daily Air Quality Index (AQI) Over Time",
            labels={"date": "Date", "aqi": "Air Quality Index (AQI)", "city_name": "City"},
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# 2. SEASONAL SWING ANALYTICS
# ------------------------------------------------------------------------------
elif navigation == "❄️ Seasonal Swing Analytics":
    st.subheader("🌡️ Analytical Query 1: Seasonal Swing (Winter vs. Summer PM2.5)")
    st.markdown("Comparing average PM2.5 concentrations during **Winter (Nov-Feb)** vs. **Summer (Apr-Jun)** per city to identify the most severe seasonal swings.")
    
    top_n = st.slider("Select Top N Cities with Highest Seasonal Swing:", min_value=3, max_value=20, value=5)
    
    swing_query = f"""
    WITH CitySeasons AS (
        SELECT 
            c.city_name AS city_name,
            AVG(CASE WHEN strftime('%m', r.date) IN ('11', '12', '01', '02') THEN r.pm25 END) AS winter_avg,
            AVG(CASE WHEN strftime('%m', r.date) IN ('04', '05', '06') THEN r.pm25 END) AS summer_avg
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE l.type = 'city' AND r.pm25 IS NOT NULL {reliability_clause}
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.city_record_id, c.city_name
    )
    SELECT 
        city_name,
        winter_avg,
        summer_avg,
        (winter_avg - summer_avg) AS seasonal_swing
    FROM CitySeasons
    WHERE winter_avg IS NOT NULL AND summer_avg IS NOT NULL
    ORDER BY seasonal_swing DESC
    LIMIT {top_n};
    """
    
    swing_df = run_query(swing_query)
    
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown(f"#### Top {top_n} Cities Data Table")
        formatted_df = swing_df.copy()
        formatted_df['winter_avg'] = formatted_df['winter_avg'].round(2)
        formatted_df['summer_avg'] = formatted_df['summer_avg'].round(2)
        formatted_df['seasonal_swing'] = formatted_df['seasonal_swing'].round(2)
        st.dataframe(formatted_df, use_container_width=True)
        
    with col_right:
        st.markdown("#### Seasonal PM2.5 Comparison (µg/m³)")
        melted_df = swing_df.melt(id_vars=['city_name'], value_vars=['winter_avg', 'summer_avg'],
                                  var_name='Season', value_name='PM2.5 Avg')
        melted_df['Season'] = melted_df['Season'].map({'winter_avg': 'Winter (Nov-Feb)', 'summer_avg': 'Summer (Apr-Jun)'})
        
        fig = px.bar(
            melted_df,
            x='city_name',
            y='PM2.5 Avg',
            color='Season',
            barmode='group',
            color_discrete_sequence=['#ef5350', '#26a69a'],
            template="plotly_dark",
            title=f"Top {top_n} Cities Winter vs Summer PM2.5 Comparison"
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# 3. WEIGHTED STATE RANKINGS
# ------------------------------------------------------------------------------
elif navigation == "⚖️ Weighted State Rankings":
    st.subheader("🗺️ Analytical Query 2: Population-Weighted State AQI")
    st.markdown("Ranking states by population-weighted average AQI for a given month.")
    
    months_df = run_query("SELECT DISTINCT strftime('%Y-%m', date) as ym FROM fact_readings ORDER BY ym DESC")
    month_list = months_df['ym'].tolist()
    
    selected_ym = st.selectbox("Select Target Month:", month_list, index=0)
    
    weighted_query = f"""
    WITH MonthlyCityAQI AS (
        SELECT 
            c.state_code,
            c.city_name AS city_name,
            c.population,
            AVG(r.aqi) AS avg_city_aqi
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE l.type = 'city' AND r.aqi IS NOT NULL {reliability_clause}
          AND strftime('%Y-%m', r.date) = '{selected_ym}'
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.state_code, c.city_record_id, c.city_name, c.population
    )
    SELECT 
        s.state_name,
        SUM(m.avg_city_aqi * m.population) / SUM(m.population) AS weighted_aqi
    FROM MonthlyCityAQI m
    JOIN dim_states s ON m.state_code = s.state_code
    GROUP BY s.state_code
    ORDER BY weighted_aqi DESC, s.state_name ASC;
    """
    
    weighted_df = run_query(weighted_query)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"#### Ranked State Table ({selected_ym})")
        weighted_df_fmt = weighted_df.copy()
        weighted_df_fmt['weighted_aqi'] = weighted_df_fmt['weighted_aqi'].round(2)
        st.dataframe(weighted_df_fmt, use_container_width=True)
        
    with col2:
        st.markdown(f"#### State Population-Weighted AQI Ranking ({selected_ym})")
        fig = px.bar(
            weighted_df,
            x='weighted_aqi',
            y='state_name',
            orientation='h',
            color='weighted_aqi',
            color_continuous_scale='Reds',
            template="plotly_dark",
            title=f"Population-Weighted AQI by State ({selected_ym})"
        )
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# 4. THRESHOLD EXCEEDANCE TRENDS
# ------------------------------------------------------------------------------
elif navigation == "⚠️ Threshold Exceedance Trends":
    st.subheader("📈 Analytical Query 3: PM2.5 Threshold Compliance & Year-over-Year Trend")
    st.markdown("For major cities, calculates the percentage of days exceeding the national PM2.5 threshold (**60 µg/m³**) and checks Year-over-Year trends.")
    
    threshold_val = st.slider("National PM2.5 Threshold Limit (µg/m³):", min_value=30, max_value=100, value=60)
    
    trend_query = f"""
    WITH CityYearlyCompliance AS (
        SELECT 
            c.city_name AS city_name,
            strftime('%Y', r.date) AS year,
            COUNT(CASE WHEN r.pm25 > {threshold_val} THEN 1 END) * 100.0 / COUNT(r.pm25) AS exceedance_rate
        FROM fact_readings r
        JOIN dim_locations l ON r.location_id = l.location_id
        JOIN dim_cities c ON l.location_id = c.city_record_id
        WHERE l.type = 'city' AND r.pm25 IS NOT NULL {reliability_clause}
          AND r.date BETWEEN c.start_date AND COALESCE(c.end_date, '9999-12-31')
        GROUP BY c.city_record_id, c.city_name, year
    ),
    YearOverYear AS (
        SELECT 
            y1.city_name,
            y1.year AS current_year,
            y1.exceedance_rate AS current_rate,
            y2.year AS prev_year,
            y2.exceedance_rate AS prev_rate
        FROM CityYearlyCompliance y1
        LEFT JOIN CityYearlyCompliance y2 
            ON y1.city_name = y2.city_name AND CAST(y1.year AS INTEGER) = CAST(y2.year AS INTEGER) + 1
    )
    SELECT 
        y.city_name,
        y.current_year,
        y.current_rate,
        y.prev_rate,
        CASE 
            WHEN y.prev_rate IS NULL THEN 'No Baseline'
            WHEN y.current_rate < y.prev_rate THEN 'Improving'
            ELSE 'Worsening'
        END AS trend
    FROM YearOverYear y
    ORDER BY y.city_name, y.current_year DESC;
    """
    
    trend_df = run_query(trend_query)
    
    city_filter = st.selectbox("Filter by Specific City:", ["All Cities"] + sorted(trend_df['city_name'].unique().tolist()))
    
    if city_filter != "All Cities":
        filtered_df = trend_df[trend_df['city_name'] == city_filter]
    else:
        filtered_df = trend_df
        
    formatted_trend = filtered_df.copy()
    formatted_trend['current_rate'] = formatted_trend['current_rate'].round(1).astype(str) + "%"
    formatted_trend['prev_rate'] = formatted_trend['prev_rate'].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "N/A")
    
    st.dataframe(formatted_trend, use_container_width=True)

# ------------------------------------------------------------------------------
# 5. STATION AUDIT & RELIABILITY
# ------------------------------------------------------------------------------
elif navigation == "🔍 Station Audit & Reliability":
    st.subheader("🛡️ Analytical Query 4: Station Data Reliability Audit")
    st.markdown("Identifies monitoring stations with stuck values, sensor saturation, or physical impossibilities.")
    
    audit_query = """
    SELECT 
        s.station_id AS station_id,
        s.station_name AS station_name,
        c.city_name AS city_name,
        COUNT(CASE WHEN r.is_reliable = 0 THEN 1 END) AS unreliable_count,
        COUNT(r.reading_id) AS total_readings,
        (COUNT(CASE WHEN r.is_reliable = 0 THEN 1 END) * 100.0 / COUNT(r.reading_id)) AS unreliable_percentage
    FROM fact_readings r
    JOIN dim_locations l ON r.location_id = l.location_id
    JOIN dim_cities c ON l.parent_id = c.city_record_id
    JOIN (
        SELECT station_id, city_record_id, station_name, ROW_NUMBER() OVER () as rnum FROM dim_stations
    ) s ON s.city_record_id = c.city_record_id AND s.rnum = (
        SELECT COUNT(*) FROM dim_locations l2 WHERE l2.type = 'station' AND l2.location_id <= l.location_id
    )
    WHERE l.type = 'station'
    GROUP BY s.station_id, s.station_name, c.city_name
    HAVING total_readings > 0
    ORDER BY unreliable_percentage DESC;
    """
    
    audit_df = run_query(audit_query)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### Station Reliability Summary")
        audit_fmt = audit_df.copy()
        audit_fmt['unreliable_percentage'] = audit_fmt['unreliable_percentage'].round(2).astype(str) + "%"
        st.dataframe(audit_fmt, use_container_width=True)
        
    with col2:
        st.markdown("#### Unreliable Reading Ratio Distribution")
        fig = px.histogram(
            audit_df,
            x='unreliable_percentage',
            nbins=20,
            title="Distribution of Unreliable Reading % per Station",
            labels={"unreliable_percentage": "Unreliable Reading (%)"},
            template="plotly_dark",
            color_discrete_sequence=['#ef5350']
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# 6. MULTI-AGENCY INGESTION
# ------------------------------------------------------------------------------
elif navigation == "📥 Multi-Agency Ingestion":
    st.subheader("📥 Multi-Agency Ingestion & Validation Portal")
    st.markdown("Assign agency schemas, upload mapping registries, validate incoming records, and view rejected rows.")
    
    tab1, tab2, tab3 = st.tabs(["🚀 Folder Scanner & Ingestion", "⚙️ Registered Agents Setup", "📋 Audit Log History"])
    
    with tab2:
        st.markdown("### ⚙️ Registered Agents Setup (`dim_agency_registry`)")
        try:
            conn = sqlite3.connect(DB_PATH)
            setup_df = pd.read_sql_query("SELECT agent_name, supported_schema, drop_location, is_active FROM dim_agency_registry", conn)
            st.dataframe(setup_df, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load setup table: {e}")
            
        st.markdown("#### ➕ Add New Agent to System")
        with st.form("add_agent_form"):
            new_agent = st.text_input("Agent Name", placeholder="e.g. Agent4")
            new_schema = st.selectbox("Supported Schema", ["SchemaA", "SchemaB"])
            new_drop = st.text_input("Drop Location Path", placeholder="/Users/.../data/IBLocationD")
            submitted = st.form_submit_button("Register Agent")
            if submitted and new_agent and new_drop:
                try:
                    os.makedirs(new_drop, exist_ok=True)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO dim_agency_registry (agent_name, supported_schema, drop_location, is_active)
                        VALUES (?, ?, ?, 1)
                    """, (new_agent, new_schema, new_drop))
                    conn.commit()
                    st.success(f"Successfully registered agent '{new_agent}' with drop location '{new_drop}'!")
                except Exception as ex:
                    st.error(f"Error registering agent: {ex}")
        conn.close()

    with tab3:
        st.markdown("### 📋 System Audit Log History (`fact_ingestion_logs`)")
        try:
            conn = sqlite3.connect(DB_PATH)
            logs_df = pd.read_sql_query("SELECT * FROM fact_ingestion_logs ORDER BY timestamp DESC", conn)
            conn.close()
            if not logs_df.empty:
                st.dataframe(logs_df, use_container_width=True)
            else:
                st.info("No ingestion audit logs recorded yet.")
        except Exception as e:
            st.error(f"Error reading audit logs: {e}")
        
    with tab1:
        st.markdown("#### 📁 Multi-Agency Ingestion & Validation")
        st.info("Scans all active agent drop locations registered in `dim_agency_registry`, validates records against assigned schemas (`SchemaA` / `SchemaB`), inserts clean rows into `fact_readings`, and archives processed files.")
        
        if st.button("▶️ Run Folder Scanner & Process Files"):
            with st.spinner("Scanning drop locations, validating schemas, archiving files, and logging metrics..."):
                try:
                    summary_df, rejected_df = run_multi_agent_pipeline(DB_PATH)
                    st.success("Multi-Agent Folder Scanner & Ingestion completed successfully!")
                except Exception as e:
                    st.error(f"Error during ingestion execution: {e}")

# ------------------------------------------------------------------------------
# 7. DATABASE EXPLORER
# ------------------------------------------------------------------------------
elif navigation == "🔎 Database Explorer":
    st.subheader("🔎 Interactive BCNF Database Explorer")
    
    selected_table = st.selectbox(
        "Select Database Table to Inspect:",
        ["dim_states", "dim_locations", "dim_cities", "dim_city_anomalies", "dim_stations", "dim_agency_registry", "fact_ingestion_logs", "fact_readings"]
    )
    
    # Text input search box
    search_query = st.text_input("🔍 Search table across all columns:", "")
    
    limit = st.slider("Max Rows to Display:", 5, 500, 50)
    
    # Query all table data
    df_table_all = run_query(f"SELECT * FROM {selected_table}")
    total_table_rows = len(df_table_all)
    
    # Filter using search query
    if search_query:
        mask = df_table_all.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
        df_table = df_table_all[mask]
        total_filtered_rows = len(df_table)
        st.markdown(f"Found **{total_filtered_rows}** matching records (showing top {min(limit, total_filtered_rows)}):")
    else:
        df_table = df_table_all
        st.markdown(f"Displaying **{min(limit, total_table_rows)}** of **{total_table_rows:,}** total rows in `{selected_table}`:")
        
    st.dataframe(df_table.head(limit), use_container_width=True)
