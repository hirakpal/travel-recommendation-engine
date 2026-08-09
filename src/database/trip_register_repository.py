"""
Master Trip Register Repository - Data access layer.
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
import uuid

from src.database.models import (
    Trip, Booking, Itinerary, Conflict, AuditLog, BudgetHistory
)


class TripUpdateConflict(RuntimeError):
    """Raised when an update is based on an outdated register version."""


class TripRegisterRepository:
    """Repository for Master Trip Register operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== TRIP OPERATIONS ====================
    
    def create_trip(
        self,
        user_id: str,
        destination: str,
        check_in_date: date,
        check_out_date: date,
        budget_total: float,
        currency: str = "USD",
        travelers: int = 1,
        adults: int = 1,
        interests: List[str] = None,
        dietary_restrictions: List[str] = None,
        accessibility_needs: List[str] = None,
        transport_preferences: List[str] = None,
        accommodation_preferences: List[str] = None,
        notes: Optional[str] = None,
    ) -> Trip:
        """Create new trip."""
        num_nights = (check_out_date - check_in_date).days
        
        trip = Trip(
            id=str(uuid.uuid4()),
            user_id=user_id,
            destination=destination,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            num_nights=num_nights,
            budget_total=budget_total,
            currency=currency,
            travelers=travelers,
            adults=adults,
            interests=interests or [],
            dietary_restrictions=dietary_restrictions or [],
            accessibility_needs=accessibility_needs or [],
            transport_preferences=transport_preferences or [],
            accommodation_preferences=accommodation_preferences or [],
            notes=notes,
        )
        
        self.db.add(trip)
        self.db.commit()
        self.db.refresh(trip)
        return trip
    
    def get_trip(self, trip_id: str) -> Optional[Trip]:
        """Get trip by ID."""
        return self.db.query(Trip).filter(Trip.id == trip_id).first()
    
    def get_user_trips(self, user_id: str) -> List[Trip]:
        """Get all trips for user."""
        return self.db.query(Trip).filter(Trip.user_id == user_id).all()

    def update_trip(
        self,
        trip_id: str,
        updates: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        agent_name: str = "Ask Anita",
        reason: str = "User-requested trip update",
    ) -> Trip:
        """Safely apply a partial update to an existing trip.

        Unspecified fields are never modified.  The version check prevents a
        stale conversation from overwriting a newer update.  Any validation,
        commit, or audit failure rolls the transaction back.
        """

        allowed_fields = {
            "destination",
            "check_in_date",
            "check_out_date",
            "budget_total",
            "currency",
            "travelers",
            "adults",
            "interests",
            "dietary_restrictions",
            "accessibility_needs",
            "transport_preferences",
            "accommodation_preferences",
            "notes",
        }
        unknown = set(updates) - allowed_fields
        if unknown:
            raise ValueError(
                f"Unsupported trip update fields: {sorted(unknown)}"
            )
        if not updates:
            raise ValueError("Trip update cannot be empty")

        try:
            query = self.db.query(Trip).filter(Trip.id == trip_id)
            trip = query.with_for_update().first()
            if trip is None:
                raise ValueError(f"Trip not found: {trip_id}")

            current_version = trip.version or 0
            if (
                expected_version is not None
                and current_version != expected_version
            ):
                raise TripUpdateConflict(
                    f"Trip {trip_id} changed from version "
                    f"{expected_version} to {current_version}. "
                    "Reload the trip before applying changes."
                )

            before_state = self._trip_to_dict(trip)
            candidate = dict(updates)

            for field_name, value in candidate.items():
                setattr(trip, field_name, value)

            if trip.check_out_date <= trip.check_in_date:
                raise ValueError(
                    "Trip check-out must be after check-in"
                )
            if trip.adults > trip.travelers:
                raise ValueError("Adults cannot exceed travelers")

            trip.num_nights = (
                trip.check_out_date - trip.check_in_date
            ).days
            trip.version = current_version + 1
            trip.updated_at = datetime.utcnow()
            self.db.flush()

            after_state = self._trip_to_dict(trip)
            self._log_audit(
                trip_id,
                "update",
                "trip",
                trip_id,
                agent_name,
                before_state=before_state,
                after_state=after_state,
            )
            self.db.commit()
            self.db.refresh(trip)
            return trip
        except Exception:
            self.db.rollback()
            raise
    
    def update_trip_status(self, trip_id: str, status: str) -> bool:
        """Update trip status."""
        trip = self.get_trip(trip_id)
        if trip:
            trip.status = status
            trip.updated_at = datetime.utcnow()
            self.db.commit()
            return True
        return False
    
    # ==================== BOOKING OPERATIONS ====================
    
    def add_booking(
        self,
        trip_id: str,
        booking_type: str,
        resource_id: str,
        resource_name: str,
        cost: float,
        agent_name: str,
        **kwargs
    ) -> Tuple[bool, str, Optional[str]]:
        """Add booking to trip."""
        
        # Verify trip exists
        trip = self.get_trip(trip_id)
        if not trip:
            return False, "Trip not found", None
        
        # Check budget
        budget_ok, budget_msg = self._check_budget(trip_id, cost)
        if not budget_ok:
            return False, budget_msg, None
        
        # Check time conflicts (if applicable)
        if "booking_time_start" in kwargs:
            conflicts = self._check_time_conflicts(
                trip_id,
                kwargs.get("booking_date"),
                kwargs.get("booking_time_start"),
                kwargs.get("booking_time_end")
            )
            if conflicts:
                return False, f"Time conflict: {conflicts[0]}", None
        
        # Create booking
        booking = Booking(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            booking_type=booking_type,
            resource_id=resource_id,
            resource_name=resource_name,
            cost=cost,
            currency=trip.currency,
            status="confirmed",
            confirmation_number=f"CONF-{str(uuid.uuid4())[:8].upper()}",
            created_by_agent=agent_name,
            **{k: v for k, v in kwargs.items() if k in [
                'check_in_date', 'check_out_date', 'booking_date',
                'booking_time_start', 'booking_time_end', 'duration_minutes', 'quantity'
            ]}
        )
        
        self.db.add(booking)
        
        # Update budget history
        self._add_budget_history(trip_id, cost, agent_name, f"Added {booking_type}")
        
        # Log audit
        self._log_audit(
            trip_id,
            "add_booking",
            "booking",
            booking.id,
            agent_name,
            after_state=self._booking_to_dict(booking)
        )
        
        self.db.commit()
        
        return True, f"Booking confirmed: {booking.confirmation_number}", booking.id
    
    def get_trip_bookings(
        self,
        trip_id: str,
        status: str = None,
        booking_type: str = None
    ) -> List[Booking]:
        """Get bookings for trip."""
        query = self.db.query(Booking).filter(Booking.trip_id == trip_id)
        
        if status:
            query = query.filter(Booking.status == status)
        if booking_type:
            query = query.filter(Booking.booking_type == booking_type)
        
        return query.order_by(Booking.created_at).all()
    
    def remove_booking(self, trip_id: str, booking_id: str, agent_name: str) -> bool:
        """Remove booking."""
        booking = self.db.query(Booking).filter(
            and_(Booking.id == booking_id, Booking.trip_id == trip_id)
        ).first()
        
        if not booking:
            return False
        
        # Log audit
        self._log_audit(
            trip_id,
            "remove_booking",
            "booking",
            booking_id,
            agent_name,
            before_state=self._booking_to_dict(booking)
        )
        
        self.db.delete(booking)
        self.db.commit()
        return True
    
    # ==================== BUDGET OPERATIONS ====================
    
    def get_budget_summary(self, trip_id: str) -> Dict[str, float]:
        """Get budget summary."""
        trip = self.get_trip(trip_id)
        if not trip:
            return {}
        
        bookings = self.db.query(Booking).filter(
            and_(Booking.trip_id == trip_id, Booking.status == "confirmed")
        ).all()
        
        spent = sum(b.cost for b in bookings)
        remaining = trip.budget_total - spent
        
        # Breakdown by type
        breakdown = {}
        for b in bookings:
            breakdown[b.booking_type] = breakdown.get(b.booking_type, 0) + b.cost
        
        return {
            "total": trip.budget_total,
            "spent": spent,
            "remaining": remaining,
            "percentage_used": (spent / trip.budget_total * 100) if trip.budget_total > 0 else 0,
            "breakdown": breakdown
        }
    
    def can_afford(self, trip_id: str, cost: float) -> bool:
        """Check if trip can afford cost."""
        budget = self.get_budget_summary(trip_id)
        return cost <= budget.get("remaining", 0)
    
    def get_remaining_budget(self, trip_id: str) -> float:
        """Get remaining budget."""
        budget = self.get_budget_summary(trip_id)
        return budget.get("remaining", 0)
    
    # ==================== ITINERARY OPERATIONS ====================
    
    def build_itinerary(self, trip_id: str) -> List[Itinerary]:
        """Build itinerary from bookings."""
        trip = self.get_trip(trip_id)
        if not trip:
            return []
        
        # Get all confirmed bookings
        bookings = self.get_trip_bookings(trip_id, status="confirmed")
        
        itinerary_items = []
        
        for booking in bookings:
            if booking.booking_type == "hotel":
                # Hotel spans multiple days
                current_date = booking.check_in_date
                while current_date < booking.check_out_date:
                    item = Itinerary(
                        id=str(uuid.uuid4()),
                        trip_id=trip_id,
                        booking_id=booking.id,
                        date=current_date,
                        activity_type="hotel",
                        activity_name=booking.resource_name,
                        details={"nights": booking.duration_minutes // (24 * 60) if booking.duration_minutes else 1}
                    )
                    itinerary_items.append(item)
                    current_date += timedelta(days=1)
            
            else:  # activity or restaurant
                item = Itinerary(
                    id=str(uuid.uuid4()),
                    trip_id=trip_id,
                    booking_id=booking.id,
                    date=booking.booking_date,
                    start_time=booking.booking_time_start,
                    end_time=booking.booking_time_end,
                    activity_type=booking.booking_type,
                    activity_name=booking.resource_name,
                    details={"cost": booking.cost, "confirmation": booking.confirmation_number}
                )
                itinerary_items.append(item)
        
        # Save itinerary items
        for item in itinerary_items:
            self.db.add(item)
        
        self.db.commit()
        return itinerary_items
    
    def get_itinerary(self, trip_id: str) -> List[Itinerary]:
        """Get itinerary ordered by date."""
        return self.db.query(Itinerary).filter(
            Itinerary.trip_id == trip_id
        ).order_by(Itinerary.date, Itinerary.start_time).all()
    
    # ==================== CONFLICT DETECTION ====================
    
    def detect_conflicts(self, trip_id: str) -> List[Conflict]:
        """Detect all conflicts."""
        bookings = self.get_trip_bookings(trip_id, status="confirmed")
        conflicts = []
        
        # Check time conflicts
        for i, b1 in enumerate(bookings):
            if not b1.booking_time_start:
                continue
            
            for b2 in bookings[i+1:]:
                if not b2.booking_time_start or b1.booking_date != b2.booking_date:
                    continue
                
                if self._times_overlap(b1.booking_time_start, b1.booking_time_end,
                                       b2.booking_time_start, b2.booking_time_end):
                    conflict = Conflict(
                        id=str(uuid.uuid4()),
                        trip_id=trip_id,
                        conflict_type="time_overlap",
                        severity="high",
                        booking_id_1=b1.id,
                        booking_id_2=b2.id,
                        description=f"Time conflict: {b1.resource_name} ({b1.booking_time_start}-{b1.booking_time_end}) overlaps with {b2.resource_name} ({b2.booking_time_start}-{b2.booking_time_end})"
                    )
                    conflicts.append(conflict)
        
        # Save conflicts
        for conflict in conflicts:
            self.db.add(conflict)
        
        self.db.commit()
        return conflicts
    
    def get_conflicts(self, trip_id: str, resolved: bool = False) -> List[Conflict]:
        """Get conflicts."""
        query = self.db.query(Conflict).filter(Conflict.trip_id == trip_id)
        
        if resolved:
            query = query.filter(Conflict.status != "unresolved")
        else:
            query = query.filter(Conflict.status == "unresolved")
        
        return query.all()
    
    # ==================== AUDIT LOG ====================
    
    def get_audit_logs(self, trip_id: str, limit: int = 50) -> List[AuditLog]:
        """Get audit logs for trip."""
        return self.db.query(AuditLog).filter(
            AuditLog.trip_id == trip_id
        ).order_by(desc(AuditLog.created_at)).limit(limit).all()
    
    # ==================== HELPER METHODS ====================
    
    def _check_budget(self, trip_id: str, amount: float) -> Tuple[bool, str]:
        """Check if booking amount fits in budget."""
        remaining = self.get_remaining_budget(trip_id)
        if amount > remaining:
            return False, f"Insufficient budget. Need {amount}, have {remaining}"
        return True, "OK"
    
    def _check_time_conflicts(
        self,
        trip_id: str,
        date_val: date,
        start_time: str,
        end_time: str
    ) -> List[str]:
        """Check for time conflicts."""
        bookings = self.db.query(Booking).filter(
            and_(
                Booking.trip_id == trip_id,
                Booking.booking_date == date_val,
                Booking.status == "confirmed"
            )
        ).all()
        
        conflicts = []
        for booking in bookings:
            if self._times_overlap(start_time, end_time,
                                   booking.booking_time_start, booking.booking_time_end):
                conflicts.append(booking.resource_name)
        
        return conflicts
    
    @staticmethod
    def _times_overlap(s1: str, e1: str, s2: str, e2: str) -> bool:
        """Check if time ranges overlap."""
        def time_to_min(t: str) -> int:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        
        s1_min, e1_min = time_to_min(s1), time_to_min(e1)
        s2_min, e2_min = time_to_min(s2), time_to_min(e2)
        
        return not (e1_min <= s2_min or s1_min >= e2_min)
    
    def _add_budget_history(
        self,
        trip_id: str,
        cost: float,
        agent_name: str,
        reason: str
    ):
        """Add budget history entry."""
        budget = self.get_budget_summary(trip_id)
        history = BudgetHistory(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            total_budget=budget["total"],
            spent_amount=budget["spent"],
            remaining_amount=budget["remaining"],
            percentage_used=budget["percentage_used"],
            breakdown=budget["breakdown"],
            change_reason=reason,
            agent_name=agent_name
        )
        self.db.add(history)
    
    def _log_audit(
        self,
        trip_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        agent_name: str,
        before_state: Dict = None,
        after_state: Dict = None
    ):
        """Log audit entry."""
        log = AuditLog(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            agent_name=agent_name,
            before_state=before_state,
            after_state=after_state
        )
        self.db.add(log)
    
    @staticmethod
    def _booking_to_dict(booking: Booking) -> Dict[str, Any]:
        """Convert booking to dict."""
        return {
            "id": booking.id,
            "type": booking.booking_type,
            "resource": booking.resource_name,
            "cost": booking.cost,
            "confirmation": booking.confirmation_number
        }

    @staticmethod
    def _trip_to_dict(trip: Trip) -> Dict[str, Any]:
        """Serialize register fields for audit before/after snapshots."""

        return {
            "id": trip.id,
            "user_id": trip.user_id,
            "destination": trip.destination,
            "check_in_date": str(trip.check_in_date),
            "check_out_date": str(trip.check_out_date),
            "num_nights": trip.num_nights,
            "budget_total": trip.budget_total,
            "currency": trip.currency,
            "travelers": trip.travelers,
            "adults": trip.adults,
            "interests": trip.interests or [],
            "dietary_restrictions": trip.dietary_restrictions or [],
            "accessibility_needs": trip.accessibility_needs or [],
            "transport_preferences": trip.transport_preferences or [],
            "accommodation_preferences": (
                trip.accommodation_preferences or []
            ),
            "notes": trip.notes,
            "status": trip.status,
            "version": trip.version or 0,
        }
