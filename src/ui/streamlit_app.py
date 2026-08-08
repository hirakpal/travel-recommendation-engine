"""
Streamlit App - FIXED VERSION
Includes sys.path workaround for import errors
"""

# ==================== CRITICAL: PATH FIX ====================
import sys
import os
from pathlib import Path

current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

# ==================== IMPORTS ====================

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import asyncio
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.database import get_db, DATABASE_URL
from src.database.trip_register_repository import TripRegisterRepository
from src.agents.supervisor_agent import SupervisorAgent
from src.core.llm_client import LLMClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== PAGE CONFIG ====================

st.set_page_config(
    page_title="✈️ Travel Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== SESSION STATE ====================

if 'trip_id' not in st.session_state:
    st.session_state.trip_id = None
if 'trip_data' not in st.session_state:
    st.session_state.trip_data = None

# ==================== DATABASE ====================

@st.cache_resource
def get_db_session():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()

# ==================== SIDEBAR ====================

st.sidebar.title("🧭 Navigation")
page = st.sidebar.radio(
    "Select Page",
    ["📝 Plan Trip", "📊 Trip Details", "📅 Itinerary", "⚠️ Conflicts", "💰 Budget", "📜 Audit Log"]
)

st.sidebar.markdown("---")
st.sidebar.info(
    """
    **Travel Recommendation Engine**
    
    AI-powered trip planning with:
    - 🏨 Hotel Booking
    - 🎫 Activity Planning
    - 🍜 Restaurant Reservations
    """
)

# ==================== MAIN ====================

def main():
    st.markdown("# ✈️ AI Travel Recommendation Engine")
    
    if page == "📝 Plan Trip":
        page_plan_trip()
    elif page == "📊 Trip Details":
        page_trip_details()
    elif page == "📅 Itinerary":
        page_itinerary()
    elif page == "⚠️ Conflicts":
        page_conflicts()
    elif page == "💰 Budget":
        page_budget()
    elif page == "📜 Audit Log":
        page_audit_log()

def page_plan_trip():
    st.header("📝 Plan Your Trip")
    
    col1, col2 = st.columns(2)
    
    with col1:
        destination = st.text_input("🌍 Destination")
        check_in = st.date_input("📅 Check-in")
        check_out = st.date_input("📅 Check-out")
        budget = st.number_input("💰 Budget ($)", min_value=100, value=2000)
    
    with col2:
        interests = st.multiselect(
            "🎯 Interests",
            ["Culture", "Food", "History", "Nature", "Adventure"]
        )
        dietary = st.multiselect(
            "🍽️ Dietary",
            ["Vegetarian", "Vegan", "Gluten-free", "None"]
        )
    
    if st.button("🚀 Plan Trip", use_container_width=True, type="primary"):
        if destination and check_out > check_in and budget > 0:
            with st.spinner("Planning your trip..."):
                try:
                    db = get_db_session()
                    supervisor = SupervisorAgent(db, LLMClient())
                    
                    request = f"Plan trip to {destination}, {check_in} to {check_out}, ${budget}"
                    result = asyncio.run(supervisor.plan_trip(request, "user"))
                    
                    if result['success']:
                        st.session_state.trip_id = result['trip_id']
                        st.success("✅ Trip planned!")
                        st.json(result)
                    else:
                        st.error(result.get('error'))
                except Exception as e:
                    st.error(f"Error: {e}")

def page_trip_details():
    st.header("📊 Trip Details")
    trip_id = st.text_input("Trip ID", value=st.session_state.trip_id or "")
    
    if trip_id:
        try:
            db = get_db_session()
            register = TripRegisterRepository(db)
            trip = register.get_trip(trip_id)
            
            if trip:
                st.write(f"**Destination:** {trip.destination}")
                st.write(f"**Nights:** {trip.num_nights}")
                st.write(f"**Budget:** ${trip.budget_total}")
            else:
                st.error("Trip not found")
        except Exception as e:
            st.error(f"Error: {e}")

def page_itinerary():
    st.header("📅 Itinerary")
    trip_id = st.text_input("Trip ID", value=st.session_state.trip_id or "")
    
    if trip_id:
        try:
            db = get_db_session()
            register = TripRegisterRepository(db)
            itinerary = register.get_itinerary(trip_id)
            
            if itinerary:
                for item in itinerary:
                    st.write(f"{item.date}: {item.activity_name}")
            else:
                st.info("No itinerary")
        except Exception as e:
            st.error(f"Error: {e}")

def page_conflicts():
    st.header("⚠️ Conflicts")
    trip_id = st.text_input("Trip ID", value=st.session_state.trip_id or "")
    
    if trip_id:
        try:
            db = get_db_session()
            register = TripRegisterRepository(db)
            conflicts = register.get_conflicts(trip_id)
            
            if conflicts:
                for conflict in conflicts:
                    st.warning(conflict.description)
            else:
                st.success("✅ No conflicts!")
        except Exception as e:
            st.error(f"Error: {e}")

def page_budget():
    st.header("💰 Budget")
    trip_id = st.text_input("Trip ID", value=st.session_state.trip_id or "")
    
    if trip_id:
        try:
            db = get_db_session()
            register = TripRegisterRepository(db)
            budget = register.get_budget_summary(trip_id)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total", f"${budget['total']:.0f}")
            with col2:
                st.metric("Spent", f"${budget['spent']:.0f}")
            with col3:
                st.metric("Remaining", f"${budget['remaining']:.0f}")
            
            st.progress(budget['percentage_used'] / 100)
        except Exception as e:
            st.error(f"Error: {e}")

def page_audit_log():
    st.header("📜 Audit Log")
    trip_id = st.text_input("Trip ID", value=st.session_state.trip_id or "")
    
    if trip_id:
        try:
            db = get_db_session()
            register = TripRegisterRepository(db)
            logs = register.get_audit_logs(trip_id)
            
            if logs:
                data = [
                    {
                        "Time": log.created_at.strftime("%H:%M:%S"),
                        "Agent": log.agent_name or "System",
                        "Action": log.action
                    }
                    for log in logs
                ]
                st.dataframe(pd.DataFrame(data))
            else:
                st.info("No logs")
        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
