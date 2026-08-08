from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def process(self, request: BaseModel) -> Any:
        """Process request and return recommendation"""
        pass
    
    @abstractmethod
    async def validate(self, request: BaseModel) -> bool:
        """Validate request format"""
        pass
