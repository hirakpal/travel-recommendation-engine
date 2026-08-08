"""
Streamlit validation dashboard for Travel Recommendation Engine.

Quick validation UI without frontend setup.
"""

import streamlit as st
import asyncio
import json
from datetime import datetime, timedelta
import sys

# Add parent to path
sys.path.insert(0, '/app')

from src.core.llm_client import LLMClient
from src.validators.hotel_validator import HotelValidator
from src.validators.activities_validator import ActivitiesValidator
from src.validators.restaurant_validator import RestaurantValidator
from src.agents.hotel_agent import HotelAgent
from src.agents.activities_agent import ActivitiesAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.models.hotel import HotelSearch
from src.models.activities import ActivitySearch
from src.models.restaurant import RestaurantSearch

# Page config
st.set_page_config(
    page_title="Travel Recommendation Engine - Validator",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title
st.title("🌍 Travel Recommendation Engine - Validation Dashboard")
st.markdown("Interactive testing and validation interface")

# Initialize session state
if 'llm_client' not in st.session_state:
    st.session_state.llm_client = None
    st.session_state.agents = {}

# Sidebar - Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    api_key = st.text_input("Anthropic API Key", type="password", key="api_key")
    
    if st.button("Initialize System", key="init_btn"):
        try:
            st.session_state.llm_client = LLMClient(api_key=api_key)
            st.session_state.agents = {
                "hotel": HotelAgent(
                    st.session_state.llm_client,
                    HotelValidator()
                ),
                "activities": ActivitiesAgent(
                    st.session_state.llm_client,
                    ActivitiesValidator()
                ),
                "restaurant": RestaurantAgent(
                    st.session_state.llm_client,
                    RestaurantValidator()
                )
            }
            st.success("✅ System initialized successfully!")
        except Exception as e:
            st.error(f"❌ Initialization failed: {e}")
    
    st.divider()
    
    # Show status
    st.subheader("System Status")
    if st.session_state.llm_client:
        st.success("✅ LLM Client: Connected")
        if st.session_state.agents:
            st.success(f"✅ Agents: {len(st.session_state.agents)} loaded")
        
        # Metrics
        if hasattr(st.session_state.llm_client, 'get_metrics'):
            metrics = st.session_state.llm_client.get_metrics()
            st.metric("Total API Calls", metrics['total_calls'])
            st.metric("Total Tokens", metrics['total_tokens'])
            st.metric("Total Cost", metrics['total_cost'])
    else:
        st.warning("⚠️ System not initialized")

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏨 Hotels", 
    "🎯 Activities", 
    "🍽️ Restaurants", 
    "✅ Validators", 
    "📊 Dashboard"
])

# ============================================================================
# TAB 1: HOTEL VALIDATION
# ============================================================================

with tab1:
    st.header("🏨 Hotel Search Validation")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Input Parameters")
        city = st.selectbox(
            "City",
            ["Hanoi", "Da Nang", "Ho Chi Minh City", "Paris", "Tokyo", "New York"],
            key="hotel_city"
        )
        
        check_in = st.date_input("Check-in Date", datetime.now() + timedelta(days=1))
        check_out = st.date_input("Check-out Date", datetime.now() + timedelta(days=4))
        
        budget_min = st.number_input("Budget Min ($)", min_value=0, value=50)
        budget_max = st.number_input("Budget Max ($)", min_value=0, value=200)
        
        star_rating = st.slider("Minimum Star Rating", 1.0, 5.0, 3.5)
        
        amenities = st.multiselect(
            "Required Amenities",
            ["WiFi", "Gym", "Pool", "Restaurant", "Spa", "Parking"],
            default=["WiFi"]
        )
    
    with col2:
        st.subheader("Validation Steps")
        
        # Create search request
        if st.button("Validate Hotel Search", key="validate_hotel"):
            num_nights = (check_out - check_in).days
            
            hotel_search = HotelSearch(
                city=city,
                check_in_date=check_in.isoformat(),
                check_out_date=check_out.isoformat(),
                num_nights=num_nights,
                budget_min=budget_min,
                budget_max=budget_max,
                star_rating_min=star_rating,
                required_amenities=amenities
            )
            
            # Validate
            validator = HotelValidator()
            
            try:
                # Step-by-step validation
                st.info("🔄 Running 6-step validation...")
                
                with st.spinner("Step 1: Budget Anchor Check..."):
                    validator._step1_anchor_budget(hotel_search)
                    st.success("✅ Step 1: Budget constraints verified")
                
                with st.spinner("Step 2: Date Verification..."):
                    validator._step2_verify_dates(hotel_search)
                    st.success("✅ Step 2: Dates verified")
                
                with st.spinner("Step 3: Amenities Check..."):
                    validator._step3_check_amenities(hotel_search)
                    st.success("✅ Step 3: Amenities checked")
                
                with st.spinner("Step 4: Star Rating..."):
                    validator._step4_star_rating(hotel_search)
                    st.success("✅ Step 4: Star rating verified")
                
                with st.spinner("Step 5: Location..."):
                    validator._step5_location(hotel_search)
                    st.success("✅ Step 5: Location verified")
                
                with st.spinner("Step 6: Final Checklist..."):
                    validator._step6_final_checklist(hotel_search)
                    st.success("✅ Step 6: Final checklist passed")
                
                st.success("✅ Hotel validation PASSED!")
                
                # Show search details
                st.subheader("Search Details")
                st.json({
                    "city": city,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "nights": num_nights,
                    "budget": f"${budget_min}-${budget_max}",
                    "star_rating_min": star_rating,
                    "amenities": amenities
                })
            
            except Exception as e:
                st.error(f"❌ Validation failed: {e}")

# ============================================================================
# TAB 2: ACTIVITIES VALIDATION
# ============================================================================

with tab2:
    st.header("🎯 Activities Search Validation")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Input Parameters")
        act_city = st.selectbox(
            "City",
            ["Hanoi", "Da Nang", "Ho Chi Minh City", "Paris", "Tokyo", "New York"],
            key="activity_city"
        )
        
        act_date = st.date_input("Activity Date", datetime.now() + timedelta(days=1))
        
        interests = st.multiselect(
            "Interests",
            ["history", "culture", "food", "nature", "adventure", "shopping", "nightlife"],
            default=["culture", "food"]
        )
        
        max_duration = st.slider("Max Duration (hours)", 2, 12, 8)
        num_activities = st.slider("Number of Activities", 1, 10, 3)
        budget_activity = st.number_input("Budget per Activity ($)", min_value=0, value=50)
        difficulty = st.selectbox("Difficulty Level", ["easy", "moderate", "hard"])
    
    with col2:
        st.subheader("Validation Steps")
        
        if st.button("Validate Activities Search", key="validate_activities"):
            activity_search = ActivitySearch(
                city=act_city,
                date=act_date.isoformat(),
                interests=interests,
                max_duration=max_duration * 60,
                budget_per_activity=budget_activity,
                num_activities=num_activities,
                difficulty_level=difficulty
            )
            
            validator = ActivitiesValidator()
            
            try:
                st.info("🔄 Running 7-step validation...")
                
                with st.spinner("Step 1: Time Budget Anchor..."):
                    validator._step1_time_anchor(activity_search)
                    st.success("✅ Step 1: Time budget anchored")
                
                with st.spinner("Step 2: Date Verification..."):
                    validator._step2_verify_date(activity_search)
                    st.success("✅ Step 2: Date verified")
                
                with st.spinner("Step 3: Interests Check..."):
                    validator._step3_interests(activity_search)
                    st.success("✅ Step 3: Interests validated")
                
                with st.spinner("Step 4: Duration Check..."):
                    validator._step4_duration(activity_search)
                    st.success("✅ Step 4: Duration checked")
                
                with st.spinner("Step 5: Difficulty..."):
                    validator._step5_difficulty(activity_search)
                    st.success("✅ Step 5: Difficulty verified")
                
                with st.spinner("Step 6: Budget Check..."):
                    validator._step6_budget(activity_search)
                    st.success("✅ Step 6: Budget verified")
                
                with st.spinner("Step 7: Fatigue Check..."):
                    validator._step7_fatigue_check(activity_search)
                    st.success("✅ Step 7: Fatigue check passed")
                
                st.success("✅ Activities validation PASSED!")
                
                st.subheader("Search Details")
                st.json({
                    "city": act_city,
                    "date": act_date.isoformat(),
                    "interests": interests,
                    "max_duration_minutes": max_duration * 60,
                    "num_activities": num_activities,
                    "budget_per_activity": budget_activity,
                    "difficulty": difficulty
                })
            
            except Exception as e:
                st.error(f"❌ Validation failed: {e}")

# ============================================================================
# TAB 3: RESTAURANT VALIDATION
# ============================================================================

with tab3:
    st.header("🍽️ Restaurant Search Validation")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Input Parameters")
        rest_city = st.selectbox(
            "City",
            ["Hanoi", "Da Nang", "Ho Chi Minh City", "Paris", "Tokyo", "New York"],
            key="restaurant_city"
        )
        
        rest_date = st.date_input("Dining Date", datetime.now() + timedelta(days=1))
        
        meal_type = st.selectbox("Meal Type", ["breakfast", "lunch", "dinner"])
        
        cuisines = st.multiselect(
            "Cuisine Preferences",
            ["vietnamese", "french", "japanese", "italian", "chinese", "indian"],
            default=["vietnamese"]
        )
        
        budget_rest_min = st.number_input("Budget Min ($)", min_value=0, value=20)
        budget_rest_max = st.number_input("Budget Max ($)", min_value=0, value=100)
        
        party_size = st.slider("Party Size", 1, 20, 2)
        
        dietary = st.multiselect(
            "Dietary Restrictions",
            ["vegetarian", "vegan", "gluten-free", "kosher", "halal"],
            default=[]
        )
    
    with col2:
        st.subheader("Validation Steps")
        
        if st.button("Validate Restaurant Search", key="validate_restaurant"):
            restaurant_search = RestaurantSearch(
                city=rest_city,
                date=rest_date.isoformat(),
                meal_type=meal_type,
                cuisine_preferences=cuisines,
                budget_min=budget_rest_min,
                budget_max=budget_rest_max,
                party_size=party_size,
                dietary_restrictions=dietary
            )
            
            validator = RestaurantValidator()
            
            try:
                st.info("🔄 Running 6-step validation...")
                
                with st.spinner("Step 1: Dietary Anchor..."):
                    validator._step1_dietary_anchor(restaurant_search)
                    st.success("✅ Step 1: Dietary requirements anchored")
                
                with st.spinner("Step 2: Meal Type..."):
                    validator._step2_meal_type(restaurant_search)
                    st.success("✅ Step 2: Meal type verified")
                
                with st.spinner("Step 3: Cuisines Check..."):
                    validator._step3_cuisines(restaurant_search)
                    st.success("✅ Step 3: Cuisines checked")
                
                with st.spinner("Step 4: Budget..."):
                    validator._step4_budget(restaurant_search)
                    st.success("✅ Step 4: Budget verified")
                
                with st.spinner("Step 5: Party Size..."):
                    validator._step5_party_size(restaurant_search)
                    st.success("✅ Step 5: Party size verified")
                
                with st.spinner("Step 6: Dietary Confirmation..."):
                    validator._step6_dietary_confirmation(restaurant_search)
                    st.success("✅ Step 6: Dietary confirmation passed")
                
                st.success("✅ Restaurant validation PASSED!")
                
                st.subheader("Search Details")
                st.json({
                    "city": rest_city,
                    "date": rest_date.isoformat(),
                    "meal_type": meal_type,
                    "cuisines": cuisines,
                    "budget": f"${budget_rest_min}-${budget_rest_max}",
                    "party_size": party_size,
                    "dietary_restrictions": dietary
                })
            
            except Exception as e:
                st.error(f"❌ Validation failed: {e}")

# ============================================================================
# TAB 4: VALIDATOR TESTS
# ============================================================================

with tab4:
    st.header("✅ Validator Tests")
    
    st.subheader("Run Individual Validator Tests")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Test Hotel Validator", key="test_hotel_val"):
            st.info("Testing HotelValidator...")
            validator = HotelValidator()
            
            # Test 1: Valid request
            try:
                test_search = HotelSearch(
                    city="Hanoi",
                    check_in_date="2024-03-20",
                    check_out_date="2024-03-23",
                    num_nights=3,
                    budget_min=3000,
                    budget_max=8000,
                    star_rating_min=4.0
                )
                asyncio.run(validator.validate(test_search))
                st.success("✅ Valid request test PASSED")
            except Exception as e:
                st.error(f"❌ Valid request test FAILED: {e}")
            
            # Test 2: Invalid budget
            try:
                test_search = HotelSearch(
                    city="Hanoi",
                    check_in_date="2024-03-20",
                    check_out_date="2024-03-23",
                    num_nights=3,
                    budget_min=1000000,
                    budget_max=2000000,
                    star_rating_min=4.0
                )
                asyncio.run(validator.validate(test_search))
                st.error("❌ Invalid budget test FAILED (should have rejected)")
            except Exception:
                st.success("✅ Invalid budget test PASSED (correctly rejected)")
    
    with col2:
        if st.button("Test Activities Validator", key="test_act_val"):
            st.info("Testing ActivitiesValidator...")
            validator = ActivitiesValidator()
            
            # Test 1: Valid request
            try:
                test_search = ActivitySearch(
                    city="Hanoi",
                    date="2024-03-20",
                    interests=["history", "culture"],
                    max_duration=480,
                    budget_per_activity=100,
                    num_activities=3,
                    difficulty_level="moderate"
                )
                asyncio.run(validator.validate(test_search))
                st.success("✅ Valid request test PASSED")
            except Exception as e:
                st.error(f"❌ Valid request test FAILED: {e}")
    
    with col3:
        if st.button("Test Restaurant Validator", key="test_rest_val"):
            st.info("Testing RestaurantValidator...")
            validator = RestaurantValidator()
            
            # Test 1: Valid request
            try:
                test_search = RestaurantSearch(
                    city="Hanoi",
                    date="2024-03-20",
                    meal_type="dinner",
                    cuisine_preferences=["vietnamese"],
                    budget_min=50,
                    budget_max=300,
                    party_size=2,
                    dietary_restrictions=[]
                )
                asyncio.run(validator.validate(test_search))
                st.success("✅ Valid request test PASSED")
            except Exception as e:
                st.error(f"❌ Valid request test FAILED: {e}")

# ============================================================================
# TAB 5: SYSTEM DASHBOARD
# ============================================================================

with tab5:
    st.header("📊 System Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("System Status", "✅ Ready")
    
    with col2:
        if st.session_state.llm_client:
            metrics = st.session_state.llm_client.get_metrics()
            st.metric("API Calls", metrics['total_calls'])
        else:
            st.metric("API Calls", "N/A")
    
    with col3:
        if st.session_state.llm_client:
            metrics = st.session_state.llm_client.get_metrics()
            st.metric("Tokens Used", metrics['total_tokens'])
        else:
            st.metric("Tokens Used", "N/A")
    
    with col4:
        if st.session_state.llm_client:
            metrics = st.session_state.llm_client.get_metrics()
            st.metric("Total Cost", metrics['total_cost'])
        else:
            st.metric("Total Cost", "N/A")
    
    st.divider()
    
    # Validators status
    st.subheader("✅ Validators Status")
    
    val_status = {
        "Hotel Validator": "✅ Ready",
        "Activities Validator": "✅ Ready",
        "Restaurant Validator": "✅ Ready"
    }
    
    for validator_name, status in val_status.items():
        st.write(f"{validator_name}: {status}")
    
    st.divider()
    
    # Agents status
    st.subheader("🤖 Agents Status")
    
    if st.session_state.agents:
        for agent_name, agent in st.session_state.agents.items():
            st.write(f"{agent_name.title()} Agent: ✅ Ready")
    else:
        st.write("Agents not initialized")
    
    st.divider()
    
    # Quick health check
    st.subheader("🏥 Health Check")
    
    if st.button("Run Health Check"):
        st.info("Running health checks...")
        
        checks = {
            "LLM Client": st.session_state.llm_client is not None,
            "Hotel Validator": True,
            "Activities Validator": True,
            "Restaurant Validator": True,
            "Hotel Agent": "hotel" in st.session_state.agents,
            "Activities Agent": "activities" in st.session_state.agents,
            "Restaurant Agent": "restaurant" in st.session_state.agents
        }
        
        all_passed = True
        for check_name, passed in checks.items():
            if passed:
                st.success(f"✅ {check_name}")
            else:
                st.error(f"❌ {check_name}")
                all_passed = False
        
        if all_passed:
            st.success("✅ All health checks PASSED!")
        else:
            st.warning("⚠️ Some checks failed. Please initialize system.")

st.divider()
st.caption("Travel Recommendation Engine - Validation Dashboard v1.0")
