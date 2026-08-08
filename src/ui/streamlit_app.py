"""
Streamlit App - Travel Recommendation Engine with Master Trip Register.
Shows real-time trip planning with all agents, budget tracking, and conflict detection.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
import asyncio
import logging
import os
import sys
from pathlib import Path

# Streamlit may execute this file outside the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.database import get_db, DATABASE_URL
from src.database.trip_register_repository import TripRegisterRepository
from src.core.llm_client import LLMClient
from src.core.langgraph_router import LangGraphTravelRouter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== PAGE CONFIG ====================

st.set_page_config(
    page_title="✈️ Travel Planner - AI Trip Planning",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== SESSION STATE ====================

if 'trip_id' not in st.session_state:
    st.session_state.trip_id = None
if 'trip_data' not in st.session_state:
    st.session_state.trip_data = None
if 'planning_in_progress' not in st.session_state:
    st.session_state.planning_in_progress = False

# ==================== DATABASE SETUP ====================

@st.cache_resource
def get_db_session():
    """Get database session."""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def configure_openai_key() -> None:
    """Load the OpenAI key from Streamlit Secrets or the process environment."""
    if os.getenv("OPENAI_API_KEY"):
        return

    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except (FileNotFoundError, KeyError, AttributeError):
        secret_key = None

    if secret_key:
        os.environ["OPENAI_API_KEY"] = str(secret_key)

# ==================== SIDEBAR: NAVIGATION ====================

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
    - 📋 Itinerary Generation
    - 🔍 Conflict Detection
    """
)

# ==================== MAIN APP ====================

def main():
    """Main app function."""
    
    # Header
    st.markdown("""
    # ✈️ AI Travel Recommendation Engine
    
    Plan your perfect trip with AI-powered coordination across hotels, activities, and restaurants!
    """)
    
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


# ==================== PAGE: PLAN TRIP ====================

def page_plan_trip():
    """Trip planning page."""
    
    st.header("📝 Plan Your Trip")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Trip Details")
        
        destination = st.text_input("🌍 Destination", placeholder="e.g., Vietnam, Paris, Tokyo")
        
        check_in = st.date_input("📅 Check-in Date", value=date.today() + timedelta(days=7))
        check_out = st.date_input("📅 Check-out Date", value=date.today() + timedelta(days=12))
        
        budget = st.number_input("💰 Budget ($)", min_value=100, value=2000, step=100)
        
    with col2:
        st.subheader("Preferences")
        
        interests = st.multiselect(
            "🎯 Interests",
            ["History", "Culture", "Food", "Nature", "Adventure", "Relaxation", "Shopping", "Architecture"],
            default=["Culture", "Food"]
        )
        
        dietary = st.multiselect(
            "🍽️ Dietary Restrictions",
            ["Vegetarian", "Vegan", "Gluten-free", "Halal", "Kosher", "None"],
            default=["None"]
        )
        
        # Remove "None" if other options selected
        if "None" in dietary and len(dietary) > 1:
            dietary.remove("None")
        if not dietary:
            dietary = ["None"]
    
    # Validate inputs
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if not destination:
            st.warning("⚠️ Please enter a destination")
    
    with col2:
        if check_out <= check_in:
            st.warning("⚠️ Check-out must be after check-in")
    
    with col3:
        if budget <= 0:
            st.warning("⚠️ Budget must be positive")
    
    # Plan Trip Button
    if st.button("🚀 Plan Trip", use_container_width=True, type="primary"):
        if destination and check_out > check_in and budget > 0:
            plan_trip_workflow(destination, check_in, check_out, budget, interests, dietary)
        else:
            st.error("❌ Please fix validation errors above")


def plan_trip_workflow(destination, check_in, check_out, budget, interests, dietary):
    """Execute trip planning workflow."""
    
    st.session_state.planning_in_progress = True
    
    # Create progress container
    progress_container = st.container()
    
    with progress_container:
        st.markdown("---")
        st.subheader("🔄 Planning Your Trip...")
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Log container
        log_container = st.container()
        
        try:
            # Get database session
            db = get_db_session()
            
            # Initialize supervisor
            configure_openai_key()
            llm_client = LLMClient()
            router = LangGraphTravelRouter(db, llm_client)
            
            # Build natural language request
            interests_str = ", ".join(interests)
            dietary_str = ", ".join(d for d in dietary if d != "None")
            
            natural_request = f"""
            Plan a trip to {destination}.
            Check-in: {check_in}, Check-out: {check_out}
            Budget: ${budget}
            Interests: {interests_str}
            Dietary restrictions: {dietary_str if dietary_str else 'None'}
            """
            
            # ==================== STEP 1: PARSING ====================
            progress_bar.progress(10)
            status_text.text("🔍 Parsing your request...")
            with log_container:
                st.info("Step 1/8: Parsing request...")
            
            # ==================== STEP 2-4: EXECUTE AGENTS ====================
            progress_bar.progress(25)
            status_text.text("🏨 Booking hotel...")
            with log_container:
                st.info("Step 2/8: Hotel Agent - Searching and booking hotel...")
            
            progress_bar.progress(40)
            status_text.text("🎫 Planning activities...")
            with log_container:
                st.info("Step 3/8: Activities Agent - Planning activities...")
            
            progress_bar.progress(55)
            status_text.text("🍜 Booking restaurants...")
            with log_container:
                st.info("Step 4/8: Restaurant Agent - Booking restaurants...")
            
            # ==================== RUN SUPERVISOR ====================
            result = asyncio.run(
                router.ainvoke(natural_request, "streamlit_user")
            )
            
            # ==================== STEP 5-8: FINALIZATION ====================
            progress_bar.progress(70)
            status_text.text("🔍 Detecting conflicts...")
            with log_container:
                st.info("Step 5/8: Checking for conflicts...")
            
            progress_bar.progress(85)
            status_text.text("📅 Building itinerary...")
            with log_container:
                st.info("Step 6/8: Building itinerary...")
            
            progress_bar.progress(95)
            status_text.text("✅ Finalizing trip...")
            with log_container:
                st.info("Step 7/8: Finalizing trip...")
            
            progress_bar.progress(100)
            status_text.text("✅ Trip planned successfully!")
            
            if result['success']:
                st.session_state.trip_id = result['trip_id']
                st.session_state.trip_data = result
                
                # Success message
                st.success(result['message'])
                
                # Show summary
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("🏨 Hotel", "Booked ✓")
                
                with col2:
                    st.metric("🎫 Activities", f"{result['stats']['total_activities']}")
                
                with col3:
                    st.metric("🍜 Meals", f"{result['stats']['total_meals']}")
                
                with col4:
                    remaining = result['budget']['remaining']
                    spent = result['budget']['spent']
                    st.metric("💰 Budget", f"${remaining:.0f} left", f"${spent:.0f} spent")
                
                # Trip details
                st.markdown("---")
                st.subheader("📋 Trip Summary")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Destination:** {result['trip']['destination']}")
                    st.write(f"**Nights:** {result['trip']['nights']}")
                    st.write(f"**Status:** {result['stats']['conflicts']} conflicts detected")
                
                with col2:
                    st.write(f"**Check-in:** {result['trip']['check_in']}")
                    st.write(f"**Check-out:** {result['trip']['check_out']}")
                    st.write(f"**Budget Used:** {result['budget']['percentage_used']:.1f}%")
                
                # Show hotel
                if result['bookings']['hotel']:
                    st.markdown("---")
                    st.subheader("🏨 Hotel Booking")
                    hotel = result['bookings']['hotel']
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**{hotel['name']}**")
                    with col2:
                        st.write(f"⭐ {hotel['rating']}/5")
                    with col3:
                        st.write(f"${hotel['total_cost']:.0f}")
                
                # Show activities
                if result['bookings']['activities']:
                    st.markdown("---")
                    st.subheader("🎫 Activities Booked")
                    activities_df = pd.DataFrame([
                        {
                            "Activity": a['name'],
                            "Date": a['date'],
                            "Time": a['time'],
                            "Cost": f"${a['cost']}"
                        }
                        for a in result['bookings']['activities']
                    ])
                    st.dataframe(activities_df, use_container_width=True)
                
                # Show meals summary
                if result['bookings']['meals']:
                    st.markdown("---")
                    st.subheader("🍜 Meals Booked")
                    st.success(f"✅ Booked {len(result['bookings']['meals'])} meals")
                    
                    # Show first few meals
                    meals_sample = result['bookings']['meals'][:3]
                    meals_df = pd.DataFrame([
                        {
                            "Restaurant": m['restaurant'],
                            "Date": m['date'],
                            "Type": m['meal_type'].title(),
                            "Time": m['time'],
                            "Cost": f"${m['cost']}"
                        }
                        for m in meals_sample
                    ])
                    st.dataframe(meals_df, use_container_width=True)
                    
                    if len(result['bookings']['meals']) > 3:
                        st.info(f"... and {len(result['bookings']['meals']) - 3} more meals")
            else:
                st.error(f"❌ {result.get('error', 'Trip planning failed')}")
        
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            logger.error(f"Error in trip planning: {e}")
        
        finally:
            st.session_state.planning_in_progress = False


# ==================== PAGE: TRIP DETAILS ====================

def page_trip_details():
    """Trip details page."""
    
    st.header("📊 Trip Details")
    
    if not st.session_state.trip_id:
        if st.session_state.trip_data:
            trip_id = st.session_state.trip_id
        else:
            trip_id = st.text_input("Enter Trip ID")
            if not trip_id:
                st.info("Create a trip first or enter a Trip ID")
                return
    else:
        trip_id = st.session_state.trip_id
    
    try:
        db = get_db_session()
        register = TripRegisterRepository(db)
        
        trip = register.get_trip(trip_id)
        if not trip:
            st.error(f"Trip {trip_id} not found")
            return
        
        # Trip info
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📍 Destination", trip.destination)
        
        with col2:
            st.metric("🌙 Nights", trip.num_nights)
        
        with col3:
            st.metric("💰 Budget", f"${trip.budget_total:.0f}")
        
        with col4:
            st.metric("📊 Status", trip.status.title())
        
        # Preferences
        st.markdown("---")
        st.subheader("🎯 Preferences")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if trip.interests:
                st.write(f"**Interests:** {', '.join(trip.interests)}")
        
        with col2:
            if trip.dietary_restrictions:
                st.write(f"**Dietary:** {', '.join(trip.dietary_restrictions)}")
        
        # Dates
        st.markdown("---")
        st.subheader("📅 Dates")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**Check-in:** {trip.check_in_date}")
        
        with col2:
            st.write(f"**Check-out:** {trip.check_out_date}")
        
        with col3:
            days_until = (trip.check_in_date - date.today()).days
            if days_until > 0:
                st.write(f"**Days until trip:** {days_until}")
            else:
                st.write(f"**Days since start:** {abs(days_until)}")
        
    except Exception as e:
        st.error(f"Error loading trip details: {e}")


# ==================== PAGE: ITINERARY ====================

def page_itinerary():
    """Itinerary page."""
    
    st.header("📅 Day-by-Day Itinerary")
    
    if not st.session_state.trip_id:
        trip_id = st.text_input("Enter Trip ID")
        if not trip_id:
            st.info("Create a trip first or enter a Trip ID")
            return
    else:
        trip_id = st.session_state.trip_id
    
    try:
        db = get_db_session()
        register = TripRegisterRepository(db)
        
        itinerary = register.get_itinerary(trip_id)
        
        if not itinerary:
            st.info("No itinerary items yet")
            return
        
        # Group by date
        by_date = {}
        for item in itinerary:
            date_str = str(item.date)
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append(item)
        
        # Display each day
        for date_str in sorted(by_date.keys()):
            items = by_date[date_str]
            
            # Date header
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                day_name = date_obj.strftime("%A, %B %d")
                st.subheader(f"📅 {day_name}")
            except:
                st.subheader(f"📅 {date_str}")
            
            # Items for this day
            for item in items:
                col1, col2, col3 = st.columns([2, 3, 2])
                
                with col1:
                    if item.start_time:
                        st.write(f"🕐 {item.start_time}-{item.end_time}")
                    else:
                        st.write("🕐 All day")
                
                with col2:
                    icon = "🏨" if item.activity_type == "hotel" else \
                           "🎫" if item.activity_type == "activity" else \
                           "🍽️" if item.activity_type == "restaurant" else "📍"
                    st.write(f"{icon} **{item.activity_name}**")
                
                with col3:
                    if item.details:
                        cost = item.details.get('cost', '')
                        if cost:
                            st.write(f"💰 ${cost}")
            
            st.divider()
    
    except Exception as e:
        st.error(f"Error loading itinerary: {e}")


# ==================== PAGE: CONFLICTS ====================

def page_conflicts():
    """Conflicts page."""
    
    st.header("⚠️ Trip Conflicts & Issues")
    
    if not st.session_state.trip_id:
        trip_id = st.text_input("Enter Trip ID")
        if not trip_id:
            st.info("Create a trip first or enter a Trip ID")
            return
    else:
        trip_id = st.session_state.trip_id
    
    try:
        db = get_db_session()
        register = TripRegisterRepository(db)
        
        conflicts = register.get_conflicts(trip_id, resolved=False)
        
        if not conflicts:
            st.success("✅ No conflicts detected! Your trip is well-coordinated.")
            return
        
        st.warning(f"⚠️ {len(conflicts)} conflicts detected")
        
        for conflict in conflicts:
            with st.expander(f"🔴 {conflict.conflict_type.replace('_', ' ').title()}"):
                st.write(f"**Severity:** {conflict.severity.upper()}")
                st.write(f"**Description:** {conflict.description}")
                
                if conflict.suggested_resolution:
                    st.info(f"**Suggested Fix:** {conflict.suggested_resolution}")
                
                st.write(f"**Status:** {conflict.status.title()}")
    
    except Exception as e:
        st.error(f"Error loading conflicts: {e}")


# ==================== PAGE: BUDGET ====================

def page_budget():
    """Budget tracking page."""
    
    st.header("💰 Budget Tracking")
    
    if not st.session_state.trip_id:
        trip_id = st.text_input("Enter Trip ID")
        if not trip_id:
            st.info("Create a trip first or enter a Trip ID")
            return
    else:
        trip_id = st.session_state.trip_id
    
    try:
        db = get_db_session()
        register = TripRegisterRepository(db)
        
        budget = register.get_budget_summary(trip_id)
        
        # Budget metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💵 Total Budget", f"${budget['total']:.2f}")
        
        with col2:
            st.metric("✅ Spent", f"${budget['spent']:.2f}")
        
        with col3:
            st.metric("📌 Remaining", f"${budget['remaining']:.2f}")
        
        with col4:
            percentage = budget['percentage_used']
            color = "🟢" if percentage <= 75 else "🟡" if percentage <= 90 else "🔴"
            st.metric(f"{color} Usage", f"{percentage:.1f}%")
        
        # Progress bar
        st.markdown("---")
        st.subheader("Budget Progress")
        
        progress = budget['percentage_used'] / 100
        st.progress(min(progress, 1.0))
        
        # Breakdown
        st.markdown("---")
        st.subheader("💸 Breakdown by Category")
        
        if budget['breakdown']:
            breakdown_df = pd.DataFrame([
                {"Category": k.title(), "Amount": f"${v:.2f}"}
                for k, v in budget['breakdown'].items()
            ])
            st.dataframe(breakdown_df, use_container_width=True)
            
            # Pie chart
            import matplotlib.pyplot as plt
            
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.pie(
                budget['breakdown'].values(),
                labels=[k.title() for k in budget['breakdown'].keys()],
                autopct='%1.1f%%',
                startangle=90
            )
            ax.set_title("Budget Breakdown")
            st.pyplot(fig)
    
    except Exception as e:
        st.error(f"Error loading budget: {e}")


# ==================== PAGE: AUDIT LOG ====================

def page_audit_log():
    """Audit log page."""
    
    st.header("📜 Trip Audit Trail")
    
    if not st.session_state.trip_id:
        trip_id = st.text_input("Enter Trip ID")
        if not trip_id:
            st.info("Create a trip first or enter a Trip ID")
            return
    else:
        trip_id = st.session_state.trip_id
    
    try:
        db = get_db_session()
        register = TripRegisterRepository(db)
        
        logs = register.get_audit_logs(trip_id, limit=100)
        
        if not logs:
            st.info("No audit log entries yet")
            return
        
        st.info(f"📊 {len(logs)} actions logged")
        
        # Display as table
        logs_data = []
        for log in logs:
            logs_data.append({
                "Time": log.created_at.strftime("%H:%M:%S"),
                "Agent": log.agent_name or "System",
                "Action": log.action.replace('_', ' ').title(),
                "Entity": log.entity_type.title(),
                "Reason": log.reason or ""
            })
        
        logs_df = pd.DataFrame(logs_data)
        st.dataframe(logs_df, use_container_width=True)
        
        # Timeline view
        st.markdown("---")
        st.subheader("📈 Action Timeline")
        
        # Group by agent
        agents = {}
        for log in logs:
            agent = log.agent_name or "System"
            if agent not in agents:
                agents[agent] = 0
            agents[agent] += 1
        
        for agent, count in sorted(agents.items()):
            st.write(f"**{agent}:** {count} actions")
    
    except Exception as e:
        st.error(f"Error loading audit log: {e}")


# ==================== RUN APP ====================

if __name__ == "__main__":
    main()
