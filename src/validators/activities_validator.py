"""Activities validator with time management."""

import logging
from src.validators.base_validator import BaseValidator, ValidationError
from src.models.activities import ActivitySearch

logger = logging.getLogger(__name__)

class ActivitiesValidator(BaseValidator):
    """
    Validate activity search with time/fatigue management.
    
    7-step validation:
    1. Time budget anchor
    2. Date verification
    3. Interest validation
    4. Duration check
    5. Difficulty validation
    6. Budget check
    7. Final fatigue check
    """
    
    def __init__(self):
        super().__init__("ActivitiesValidator")
        self.valid_interests = {
            "history", "culture", "food", "nature", "adventure",
            "shopping", "nightlife", "art", "sports", "relaxation"
        }
        self.valid_difficulties = {"easy", "moderate", "hard"}
    
    async def validate(self, request: ActivitySearch) -> bool:
        """Validate activity search request."""
        
        try:
            logger.info(f"Validating activities search: {request.city}")
            
            # STEP 1: TIME BUDGET ANCHOR (START)
            self._step1_time_anchor(request)
            
            # STEP 2: DATE VERIFICATION (MIDDLE)
            self._step2_verify_date(request)
            
            # STEP 3: INTERESTS CHECK (MIDDLE)
            self._step3_interests(request)
            
            # STEP 4: DURATION (MIDDLE)
            self._step4_duration(request)
            
            # STEP 5: DIFFICULTY (MIDDLE)
            self._step5_difficulty(request)
            
            # STEP 6: BUDGET (MIDDLE)
            self._step6_budget(request)
            
            # STEP 7: FATIGUE CHECK (END)
            self._step7_fatigue_check(request)
            
            logger.info(f"✓ Activities validation PASSED")
            return True
        
        except ValidationError as e:
            logger.error(f"✗ Activities validation FAILED: {e}")
            raise
    
    def _step1_time_anchor(self, request: ActivitySearch):
        """ANCHOR: Time budget constraint."""
        
        logger.info("STEP 1: Time budget anchor (START)")
        
        if request.max_duration < 60:
            raise ValidationError("Minimum 60 minutes needed")
        if request.max_duration > 1440:  # 24 hours
            raise ValidationError("Maximum 1440 minutes (24 hours)")
        
        logger.info(f"  ✓ Time budget: {request.max_duration} minutes")
    
    def _step2_verify_date(self, request: ActivitySearch):
        """VERIFY: Date is valid."""
        
        logger.info("STEP 2: Verify date (MIDDLE)")
        
        from datetime import datetime
        try:
            datetime.fromisoformat(request.date)
        except ValueError:
            raise ValidationError("Invalid date format")
        
        logger.info(f"  ✓ Date: {request.date}")
    
    def _step3_interests(self, request: ActivitySearch):
        """CHECK: Interests are valid."""
        
        logger.info("STEP 3: Check interests (MIDDLE)")
        
        if not request.interests:
            raise ValidationError("At least one interest required")
        
        invalid = set(request.interests) - self.valid_interests
        if invalid:
            raise ValidationError(f"Invalid interests: {invalid}")
        
        logger.info(f"  ✓ Interests: {request.interests}")
    
    def _step4_duration(self, request: ActivitySearch):
        """CHECK: Max duration is reasonable."""
        
        logger.info("STEP 4: Check duration (MIDDLE)")
        
        # Check for over-packing
        if request.max_duration / request.num_activities < 30:
            logger.warning(f"  ⚠️  Only {request.max_duration // request.num_activities}min per activity")
        
        logger.info(f"  ✓ Avg {request.max_duration // request.num_activities}min per activity")
    
    def _step5_difficulty(self, request: ActivitySearch):
        """CHECK: Difficulty level valid."""
        
        logger.info("STEP 5: Check difficulty (MIDDLE)")
        
        if request.difficulty_level not in self.valid_difficulties:
            raise ValidationError(f"Invalid difficulty: {request.difficulty_level}")
        
        logger.info(f"  ✓ Difficulty: {request.difficulty_level}")
    
    def _step6_budget(self, request: ActivitySearch):
        """CHECK: Budget per activity."""
        
        logger.info("STEP 6: Check budget (MIDDLE)")
        
        if request.budget_per_activity <= 0:
            raise ValidationError("Budget must be > 0")
        
        logger.info(f"  ✓ Budget: ${request.budget_per_activity}/activity")
    
    def _step7_fatigue_check(self, request: ActivitySearch):
        """CONFIRM: Fatigue management checklist."""
        
        logger.info("STEP 7: Fatigue check (END)")
        
        # Don't over-pack
        avg_duration = request.max_duration / request.num_activities
        
        checklist = {
            "At least 30min per activity": avg_duration >= 30,
            "Rest between activities": avg_duration >= 45,
            "Mix of activity types": len(request.interests) >= 2,
            "Reasonable activity count": request.num_activities <= 5,
        }
        
        warnings = [k for k, v in checklist.items() if not v]
        if warnings:
            logger.warning(f"  ⚠️  Fatigue warnings: {warnings}")
        
        logger.info(f"  ✓ Fatigue check COMPLETE")
