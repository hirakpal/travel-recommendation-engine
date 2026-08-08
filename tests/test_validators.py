"""Validator tests."""

import pytest
from src.validators.hotel_validator import HotelValidator
from src.validators.activities_validator import ActivitiesValidator
from src.validators.restaurant_validator import RestaurantValidator
from src.models.hotel import HotelSearch
from src.models.activities import ActivitySearch
from src.models.restaurant import RestaurantSearch

class TestHotelValidator:
    """Hotel validator tests."""
    
    @pytest.mark.asyncio
    async def test_valid_request(self, sample_hotel_search):
        """Test valid hotel request."""
        validator = HotelValidator()
        result = await validator.validate(sample_hotel_search)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_budget_too_high(self, sample_hotel_search):
        """Test rejection of too-high budget."""
        sample_hotel_search.budget_max = 100000
        validator = HotelValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_hotel_search)
    
    @pytest.mark.asyncio
    async def test_invalid_star_rating(self, sample_hotel_search):
        """Test invalid star rating."""
        sample_hotel_search.star_rating_min = 10  # Invalid
        validator = HotelValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_hotel_search)
    
    @pytest.mark.asyncio
    async def test_invalid_amenity(self, sample_hotel_search):
        """Test invalid amenity."""
        sample_hotel_search.required_amenities = ["InvalidAmenity"]
        validator = HotelValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_hotel_search)


class TestActivitiesValidator:
    """Activities validator tests."""
    
    @pytest.mark.asyncio
    async def test_valid_request(self, sample_activity_search):
        """Test valid activity request."""
        validator = ActivitiesValidator()
        result = await validator.validate(sample_activity_search)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_time_too_short(self, sample_activity_search):
        """Test too-short time budget."""
        sample_activity_search.max_duration = 30  # Too short
        validator = ActivitiesValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_activity_search)
    
    @pytest.mark.asyncio
    async def test_invalid_interests(self, sample_activity_search):
        """Test invalid interests."""
        sample_activity_search.interests = ["invalid_interest"]
        validator = ActivitiesValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_activity_search)


class TestRestaurantValidator:
    """Restaurant validator tests."""
    
    @pytest.mark.asyncio
    async def test_valid_request(self, sample_restaurant_search):
        """Test valid restaurant request."""
        validator = RestaurantValidator()
        result = await validator.validate(sample_restaurant_search)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_invalid_meal_type(self, sample_restaurant_search):
        """Test invalid meal type."""
        sample_restaurant_search.meal_type = "invalid"
        validator = RestaurantValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_restaurant_search)
    
    @pytest.mark.asyncio
    async def test_party_size_too_large(self, sample_restaurant_search):
        """Test party size too large."""
        sample_restaurant_search.party_size = 100
        validator = RestaurantValidator()
        
        with pytest.raises(ValueError):
            await validator.validate(sample_restaurant_search)
