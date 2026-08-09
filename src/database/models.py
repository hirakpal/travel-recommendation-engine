"""
Updated SQLAlchemy database models with Master Trip Register support.
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, Boolean, Text, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid

Base = declarative_base()

# ==================== TRIP & BOOKING MODELS ====================

class Trip(Base):
    """Trip model with register support."""
    __tablename__ = "trips"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    destination = Column(String, nullable=False)
    
    # Dates
    check_in_date = Column(Date, nullable=False)
    check_out_date = Column(Date, nullable=False)
    num_nights = Column(Integer)
    travelers = Column(Integer, nullable=False, default=1)
    adults = Column(Integer, nullable=False, default=1)
    
    # Budget
    budget_total = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    
    # Preferences & Constraints
    interests = Column(JSON)  # [history, culture, food, nature]
    dietary_restrictions = Column(JSON)  # [vegetarian, vegan, gluten-free]
    accessibility_needs = Column(JSON)
    transport_preferences = Column(JSON)
    accommodation_preferences = Column(JSON)
    preferences = Column(JSON)
    notes = Column(Text)
    
    # Status
    status = Column(String, default="planning")  # planning, booked, completed
    
    # Relationships
    bookings = relationship("Booking", back_populates="trip", cascade="all, delete-orphan")
    itinerary = relationship("Itinerary", back_populates="trip", cascade="all, delete-orphan")
    conflicts = relationship("Conflict", back_populates="trip", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="trip", cascade="all, delete-orphan")
    budget_history = relationship("BudgetHistory", back_populates="trip", cascade="all, delete-orphan")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optimistic locking
    version = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<Trip {self.destination} ({self.check_in_date})>"


class Booking(Base):
    """Booking model - single booking entry."""
    __tablename__ = "bookings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, index=True)
    
    # Booking details
    booking_type = Column(String, nullable=False, index=True)  # hotel, activity, restaurant
    resource_id = Column(String, nullable=False)
    resource_name = Column(String, nullable=False)
    
    # Dates (for hotels)
    check_in_date = Column(Date)
    check_out_date = Column(Date)
    
    # Time (for activities/restaurants)
    booking_date = Column(Date)
    booking_time_start = Column(String)  # HH:MM format
    booking_time_end = Column(String)    # HH:MM format
    duration_minutes = Column(Integer)
    
    # Cost
    cost = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    quantity = Column(Integer, default=1)
    
    # Status
    status = Column(String, default="pending")  # pending, confirmed, cancelled
    confirmation_number = Column(String, unique=True)
    
    # Metadata
    created_by_agent = Column(String)  # Which agent created this booking
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    trip = relationship("Trip", back_populates="bookings")
    
    def __repr__(self):
        return f"<Booking {self.booking_type}: {self.resource_name}>"


class Itinerary(Base):
    """Itinerary model - daily schedule."""
    __tablename__ = "itinerary"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, index=True)
    booking_id = Column(String, ForeignKey("bookings.id"))
    
    # Schedule
    day_number = Column(Integer)
    date = Column(Date, nullable=False, index=True)
    time_slot = Column(String)  # morning, afternoon, evening, night
    start_time = Column(String)  # HH:MM
    end_time = Column(String)    # HH:MM
    
    # Activity type
    activity_type = Column(String)  # meal, activity, travel, rest, hotel
    activity_name = Column(String)
    
    # Details
    details = Column(JSON)
    notes = Column(Text)
    
    # Relationship
    trip = relationship("Trip", back_populates="itinerary")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Itinerary {self.date} {self.activity_name}>"


class Conflict(Base):
    """Conflict model - tracks issues."""
    __tablename__ = "conflicts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, index=True)
    
    # Conflict details
    conflict_type = Column(String)  # time_overlap, budget_exceeded, constraint_violation
    severity = Column(String)  # low, medium, high
    
    # Related bookings
    booking_id_1 = Column(String, ForeignKey("bookings.id"))
    booking_id_2 = Column(String, ForeignKey("bookings.id"))
    
    # Description
    description = Column(Text, nullable=False)
    suggested_resolution = Column(Text)
    
    # Status
    status = Column(String, default="unresolved")  # unresolved, resolved, ignored
    resolution_notes = Column(Text)
    
    # Relationship
    trip = relationship("Trip", back_populates="conflicts")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    
    def __repr__(self):
        return f"<Conflict {self.conflict_type}: {self.status}>"


class AuditLog(Base):
    """Audit log model - tracks all changes."""
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, index=True)
    
    # Action details
    action = Column(String, nullable=False)  # create, update, add_booking, remove_booking
    entity_type = Column(String)  # trip, booking, itinerary
    entity_id = Column(String)
    
    # Changes
    before_state = Column(JSON)
    after_state = Column(JSON)
    
    # Who & Why
    agent_name = Column(String)
    user_id = Column(String)
    reason = Column(Text)
    
    # Relationship
    trip = relationship("Trip", back_populates="audit_logs")
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<AuditLog {self.action} at {self.created_at}>"


class BudgetHistory(Base):
    """Budget history model - tracks budget changes."""
    __tablename__ = "budget_history"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id = Column(String, ForeignKey("trips.id"), nullable=False, index=True)
    
    # Budget snapshot
    total_budget = Column(Float)
    spent_amount = Column(Float)
    remaining_amount = Column(Float)
    percentage_used = Column(Float)
    
    # Breakdown by category
    breakdown = Column(JSON)  # {hotel: 100, activities: 50, food: 30}
    
    # Context
    booking_id = Column(String)
    change_reason = Column(String)
    agent_name = Column(String)
    
    # Relationship
    trip = relationship("Trip", back_populates="budget_history")
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<BudgetHistory {self.created_at}>"


# ==================== LEGACY MODELS (unchanged) ====================

class Hotel(Base):
    """Hotel model."""
    __tablename__ = "hotels"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    city = Column(String, nullable=False, index=True)
    country = Column(String)
    rating = Column(Float)
    price_per_night = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    amenities = Column(JSON)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    website = Column(String)
    image_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Activity(Base):
    """Activity model."""
    __tablename__ = "activities"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    city = Column(String, nullable=False, index=True)
    category = Column(String, index=True)
    description = Column(Text)
    duration_minutes = Column(Integer)
    cost = Column(Float)
    currency = Column(String, default="USD")
    difficulty_level = Column(String)
    rating = Column(Float)
    best_time = Column(String)
    location = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    image_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Restaurant(Base):
    """Restaurant model."""
    __tablename__ = "restaurants"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    city = Column(String, nullable=False, index=True)
    cuisine = Column(String, index=True)
    description = Column(Text)
    rating = Column(Float)
    price_range = Column(String)
    average_cost = Column(Float)
    currency = Column(String, default="USD")
    dietary_options = Column(JSON)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    website = Column(String)
    image_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

