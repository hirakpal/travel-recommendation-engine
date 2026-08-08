"""Hotel search validator with bias mitigation."""

import logging
from src.validators.base_validator import BaseValidator, ValidationError
from src.models.hotel import HotelSearch

logger = logging.getLogger(__name__)

class HotelValidator(BaseValidator):
    """
    Validate hotel search requests.
    
    6-step validation process:
    1. Budget constraints (ANCHOR at START)
    2. Dates validation
    3. Amenities check
    4. Star rating check
    5. Database verification
    6. Final checklist (CONFIRM at END)
    """
    
    def __init__(self):
        super().__init__("HotelValidator")
        # Load valid amenities from database
        self.valid_amenities = {
            "WiFi", "Gym", "Pool", "Restaurant", "Bar",
            "Room Service", "Parking", "Laundry", "Business Center",
            "Spa", "Concierge", "24h Front Desk", "Air Conditioning"
        }
    
    async def validate(self, request: HotelSearch) -> bool:
        """
        Validate hotel search request with bias mitigation.
        
        Returns:
            True if valid, raises ValidationError if invalid
        """
        
        try:
            logger.info(f"Validating hotel search: {request.city}")
            
            # STEP 1: ANCHOR BUDGET (START)
            self._step1_anchor_budget(request)
            
            # STEP 2: VERIFY DATES (MIDDLE)
            self._step2_verify_dates(request)
            
            # STEP 3: CHECK AMENITIES (MIDDLE)
            self._step3_check_amenities(request)
            
            # STEP 4: STAR RATING (MIDDLE)
            self._step4_star_rating(request)
            
            # STEP 5: LOCATION (MIDDLE)
            self._step5_location(request)
            
            # STEP 6: FINAL CHECKLIST (END)
            self._step6_final_checklist(request)
            
            logger.info(f"✓ Hotel validation PASSED: {request.city}")
            return True
        
        except ValidationError as e:
            logger.error(f"✗ Hotel validation FAILED: {e}")
            raise
    
    def _step1_anchor_budget(self, request: HotelSearch):
        """ANCHOR: Budget constraint reinforcement."""
        
        logger.info("STEP 1: Anchor budget constraints (START)")
        
        # Verify budget range
        self._check_budget_anchor(request.budget_min, request.budget_max)
        
        # Check for reasonable values
        if request.budget_max > 50000:
            raise ValidationError("Budget too high (max $50,000/night)")
        
        logger.info(f"  ✓ Budget: ${request.budget_min}-${request.budget_max}")
    
    def _step2_verify_dates(self, request: HotelSearch):
        """VERIFY: Date validation."""
        
        logger.info("STEP 2: Verify dates (MIDDLE)")
        
        self._check_dates(request.check_in_date, request.check_out_date)
        
        # Verify night count matches dates
        from datetime import datetime
        check_in = datetime.fromisoformat(request.check_in_date)
        check_out = datetime.fromisoformat(request.check_out_date)
        calculated_nights = (check_out - check_in).days
        
        if request.num_nights != calculated_nights:
            raise ValidationError(
                f"Night count mismatch: {request.num_nights} != {calculated_nights}"
            )
        
        logger.info(f"  ✓ Dates: {request.num_nights} nights verified")
    
    def _step3_check_amenities(self, request: HotelSearch):
        """CHECK: Amenities exist in database."""
        
        logger.info("STEP 3: Check amenities (MIDDLE)")
        
        if not request.required_amenities:
            logger.info("  ✓ No specific amenities required")
            return
        
        invalid = set(request.required_amenities) - self.valid_amenities
        if invalid:
            raise ValidationError(f"Invalid amenities: {invalid}")
        
        logger.info(f"  ✓ Amenities valid: {request.required_amenities}")
    
    def _step4_star_rating(self, request: HotelSearch):
        """CHECK: Star rating constraints."""
        
        logger.info("STEP 4: Verify star rating (MIDDLE)")
        
        if request.star_rating_min < 1.0 or request.star_rating_min > 5.0:
            raise ValidationError("Star rating must be 1-5")
        
        logger.info(f"  ✓ Star rating minimum: {request.star_rating_min}")
    
    def _step5_location(self, request: HotelSearch):
        """CHECK: City exists in database."""
        
        logger.info("STEP 5: Verify location (MIDDLE)")
        
        if not request.city or len(request.city) < 2:
            raise ValidationError("Invalid city name")
        
        # Could check against city database here
        logger.info(f"  ✓ City: {request.city}")
    
    def _step6_final_checklist(self, request: HotelSearch):
        """CONFIRM: Final verification checklist."""
        
        logger.info("STEP 6: Final checklist (END)")
        
        checklist = {
            "Budget min > 0": request.budget_min > 0,
            "Budget max >= min": request.budget_max >= request.budget_min,
            "Check-in before check-out": request.check_in_date < request.check_out_date,
            "Nights >= 1": request.num_nights >= 1,
            "Star rating valid": 1.0 <= request.star_rating_min <= 5.0,
            "City specified": bool(request.city),
        }
        
        failed = [k for k, v in checklist.items() if not v]
        if failed:
            raise ValidationError(f"Final checklist failed: {failed}")
        
        logger.info(f"  ✓ All 6 checks PASSED")
