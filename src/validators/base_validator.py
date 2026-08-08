"""Base validator with common anti-bias checks."""

from abc import ABC, abstractmethod
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Validation failed."""
    pass

class BaseValidator(ABC):
    """Base class for all validators."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def validate(self, request: BaseModel) -> bool:
        """Validate request. Raise ValidationError if invalid."""
        pass
    
    def _check_budget_anchor(self, min_budget: float, max_budget: float) -> bool:
        """
        STEP 1: ANCHOR CHECK (START)
        Verify budget constraints at start.
        """
        if min_budget <= 0:
            raise ValidationError("Budget minimum must be > 0")
        if max_budget < min_budget:
            raise ValidationError("Budget maximum must be >= minimum")
        if (max_budget - min_budget) / min_budget > 10:
            raise ValidationError("Budget range too wide (max 10x min)")
        
        logger.info(f"✓ Budget anchor check: ${min_budget}-${max_budget}")
        return True
    
    def _check_dates(self, start_date: str, end_date: str) -> bool:
        """
        STEP 2: VERIFY DATES (MIDDLE)
        Check dates are valid and in order.
        """
        from datetime import datetime
        
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        except ValueError:
            raise ValidationError("Invalid date format (use YYYY-MM-DD)")
        
        if start > end:
            raise ValidationError("Start date must be before end date")
        
        days = (end - start).days
        if days > 30:
            raise ValidationError("Trip duration > 30 days")
        if days < 1:
            raise ValidationError("Trip must be at least 1 day")
        
        logger.info(f"✓ Date check: {days} days ({start_date} to {end_date})")
        return True
    
    def _check_no_hallucination(self, items: list, item_ids: set) -> bool:
        """
        STEP 3: ANTI-HALLUCINATION (END)
        Verify all items exist in database.
        """
        for item in items:
            item_id = getattr(item, 'id', None) or item.get('id')
            if item_id and item_id not in item_ids:
                raise ValidationError(f"Hallucinated item: {item_id}")
        
        logger.info(f"✓ Anti-hallucination check: {len(items)} items verified")
        return True
