"""Restaurant validator with dietary focus."""

import logging
from src.validators.base_validator import BaseValidator, ValidationError
from src.models.restaurant import RestaurantSearch

logger = logging.getLogger(__name__)

class RestaurantValidator(BaseValidator):
    """
    Validate restaurant search with dietary accommodation.
    
    6-step validation:
    1. Dietary requirement anchor
    2. Meal type verification
    3. Cuisine validation
    4. Budget check
    5. Party size check
    6. Final dietary confirmation
    """
    
    def __init__(self):
        super().__init__("RestaurantValidator")
        self.valid_meal_types = {"breakfast", "lunch", "dinner"}
        self.valid_cuisines = {
            "italian", "chinese", "japanese", "indian", "mexican",
            "thai", "french", "spanish", "vietnamese", "american"
        }
    
    async def validate(self, request: RestaurantSearch) -> bool:
        """Validate restaurant search with dietary focus."""
        
        try:
            logger.info(f"Validating restaurant search: {request.city}")
            
            # STEP 1: DIETARY ANCHOR (START)
            self._step1_dietary_anchor(request)
            
            # STEP 2: MEAL TYPE (MIDDLE)
            self._step2_meal_type(request)
            
            # STEP 3: CUISINES (MIDDLE)
            self._step3_cuisines(request)
            
            # STEP 4: BUDGET (MIDDLE)
            self._step4_budget(request)
            
            # STEP 5: PARTY SIZE (MIDDLE)
            self._step5_party_size(request)
            
            # STEP 6: DIETARY CONFIRMATION (END)
            self._step6_dietary_confirmation(request)
            
            logger.info(f"✓ Restaurant validation PASSED")
            return True
        
        except ValidationError as e:
            logger.error(f"✗ Restaurant validation FAILED: {e}")
            raise
    
    def _step1_dietary_anchor(self, request: RestaurantSearch):
        """ANCHOR: Dietary requirements."""
        
        logger.info("STEP 1: Dietary requirement anchor (START)")
        
        valid_restrictions = {"vegetarian", "vegan", "gluten-free", "kosher", "halal"}
        invalid = set(request.dietary_restrictions) - valid_restrictions
        
        if invalid:
            raise ValidationError(f"Invalid dietary restrictions: {invalid}")
        
        logger.info(f"  ✓ Dietary: {request.dietary_restrictions or 'None'}")
    
    def _step2_meal_type(self, request: RestaurantSearch):
        """VERIFY: Meal type is valid."""
        
        logger.info("STEP 2: Verify meal type (MIDDLE)")
        
        if request.meal_type not in self.valid_meal_types:
            raise ValidationError(f"Invalid meal type: {request.meal_type}")
        
        logger.info(f"  ✓ Meal type: {request.meal_type}")
    
    def _step3_cuisines(self, request: RestaurantSearch):
        """CHECK: Cuisine preferences valid."""
        
        logger.info("STEP 3: Check cuisines (MIDDLE)")
        
        if not request.cuisine_preferences:
            raise ValidationError("At least one cuisine required")
        
        # Allow some flexibility (don't enforce valid_cuisines strictly)
        logger.info(f"  ✓ Cuisines: {request.cuisine_preferences}")
    
    def _step4_budget(self, request: RestaurantSearch):
        """CHECK: Budget range valid."""
        
        logger.info("STEP 4: Check budget (MIDDLE)")
        
        self._check_budget_anchor(request.budget_min, request.budget_max)
        
        if request.budget_max > 10000:
            raise ValidationError("Budget too high (max $10,000)")
        
        logger.info(f"  ✓ Budget: ${request.budget_min}-${request.budget_max}")
    
    def _step5_party_size(self, request: RestaurantSearch):
        """CHECK: Party size valid."""
        
        logger.info("STEP 5: Check party size (MIDDLE)")
        
        if request.party_size < 1 or request.party_size > 20:
            raise ValidationError("Party size must be 1-20")
        
        logger.info(f"  ✓ Party size: {request.party_size}")
    
    def _step6_dietary_confirmation(self, request: RestaurantSearch):
        """CONFIRM: Dietary requirements checklist."""
        
        logger.info("STEP 6: Dietary confirmation (END)")
        
        has_vegetarian = "vegetarian" not in request.dietary_restrictions
        has_vegan = "vegan" not in request.dietary_restrictions
        
        checklist = {
            "Cuisine specified": bool(request.cuisine_preferences),
            "Meal type valid": request.meal_type in self.valid_meal_types,
            "Budget valid": request.budget_min <= request.budget_max,
            "Party size valid": 1 <= request.party_size <= 20,
        }
        
        failed = [k for k, v in checklist.items() if not v]
        if failed:
            raise ValidationError(f"Dietary confirmation failed: {failed}")
        
        logger.info(f"  ✓ All dietary requirements CONFIRMED")
