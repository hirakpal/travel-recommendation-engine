from src.agents.base_agent import BaseAgent


class HotelAgent(BaseAgent):
    """Hotel agent using Master Trip Register."""
    
    async def recommend(self, trip_id: str, city: str):
        """Recommend hotel using register."""
        
        # Get trip state
        trip = self.get_trip_state(trip_id)
        if not trip:
            return {"error": "Trip not found"}
        
        # Check budget
        budget_info = self.get_budget_info(trip_id)
        available = budget_info["remaining"]
        max_per_night = available / trip.num_nights
        
        # Check existing hotel bookings
        existing_hotels = self.get_existing_bookings(trip_id, "hotel")
        if existing_hotels:
            return {"message": "Hotel already booked", "booking": existing_hotels[0]}
        
        # Search hotels within budget
        from src.database.repository import HotelRepository
        hotel_repo = HotelRepository(self.db)
        candidates = hotel_repo.get_by_city_and_budget(city, 0, max_per_night)
        
        if not candidates:
            return {"error": f"No hotels found within budget"}
        
        # Select best hotel
        best_hotel = max(candidates, key=lambda h: h.rating)
        total_cost = best_hotel.price_per_night * trip.num_nights
        
        # Add booking to register
        success, message, booking_id = self.add_booking(
            trip_id=trip_id,
            booking_type="hotel",
            resource_id=best_hotel.id,
            resource_name=best_hotel.name,
            cost=total_cost,
            check_in_date=trip.check_in_date,
            check_out_date=trip.check_out_date
        )
        
        if not success:
            return {"error": message}
        
        return {
            "hotel": best_hotel,
            "booking_id": booking_id,
            "cost": total_cost,
            "message": message
        }
