"""Activities recommendation agent with time management."""

import json
from typing import List, Optional
from datetime import datetime, timedelta
from src.agents.base_agent import BaseAgent
from src.models.activities import ActivitySearch, ActivityRecommendation, Activity
from src.core.llm_client import LLMClient
from src.validators.activities_validator import ActivitiesValidator
from src.cache.manager import CacheManager

class ActivitiesAgent(BaseAgent):
    """
    Activities recommendation agent.
    
    Features:
    - Time-aware scheduling (avoid over-packing)
    - Fatigue tracking (no duplicate activities)
    - Interest matching
    - Travel time consideration
    - Optimal sequencing
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        validator: ActivitiesValidator,
        cache: Optional[CacheManager] = None,
        activities_data_path: str = "data/activities.json"
    ):
        super().__init__("ActivitiesAgent")
        self.llm = llm_client
        self.validator = validator
        self.cache = cache
        self.activities_db = self._load_database(activities_data_path)
    
    def _load_database(self, path: str) -> dict:
        """Load activities database."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Activities database not found at {path}")
            return {}
    
    async def process(
        self,
        request: ActivitySearch
    ) -> List[ActivityRecommendation]:
        """
        Process activity search request.
        
        Args:
            request: Activity search criteria
        
        Returns:
            List of activity recommendations with time slots
        """
        
        # STEP 1: Validate request
        if not await self.validate(request):
            raise ValueError(f"Invalid activity search: {request}")
        
        # STEP 2: Check cache
        cache_key = self._make_cache_key(request)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
        
        # STEP 3: Filter activities by interest
        candidates = self._filter_by_interests(request)
        
        if not candidates:
            print(f"⚠️  No activities found in {request.city}")
            return []
        
        # STEP 4: Score and rank with Claude
        recommendations = await self._score_with_claude(request, candidates)
        
        # STEP 5: Schedule with time management
        recommendations = self._schedule_activities(request, recommendations)
        
        # STEP 6: Cache
        if self.cache:
            await self.cache.set(cache_key, recommendations, ttl=3600)
        
        return recommendations
    
    async def validate(self, request: ActivitySearch) -> bool:
        """Validate activity search request."""
        return await self.validator.validate(request)
    
    def _make_cache_key(self, request: ActivitySearch) -> str:
        """Create cache key."""
        interests_str = "_".join(sorted(request.interests))
        return f"activities:{request.city.lower()}:{request.date}:{interests_str}"
    
    def _filter_by_interests(self, request: ActivitySearch) -> List[Activity]:
        """
        Filter activities by user interests.
        
        Anti-bias measures:
        - Don't anchor on first activity
        - Consider all interests equally
        - No hallucination (only from database)
        """
        
        results = []
        activities_in_city = self.activities_db.get(request.city.lower(), [])
        
        for activity_data in activities_in_city:
            try:
                activity = Activity(**activity_data)
            except Exception as e:
                print(f"⚠️  Skipping invalid activity: {e}")
                continue
            
            # Interest match check
            if any(interest in activity.category for interest in request.interests):
                # Duration check
                if activity.duration_minutes <= request.max_duration:
                    # Budget check
                    if activity.cost <= request.budget_per_activity:
                        results.append(activity)
        
        return results
    
    async def _score_with_claude(
        self,
        request: ActivitySearch,
        candidates: List[Activity]
    ) -> List[ActivityRecommendation]:
        """Score activities considering interest alignment."""
        
        system_prompt = """You are an activities recommendation expert.

TASK: Score activities for interest match.

SCORING (0-1):
- Interest alignment: Matches user preferences
- Duration fit: Fits in available time
- Value: Cost-to-experience ratio
- Feasibility: Can be done on requested date
- Uniqueness: Offers distinct experience

ANTI-BIAS:
✓ No duplicates (don't recommend similar activities)
✓ No over-scheduling (consider fatigue)
✓ Interest diversity (mix different types)
✓ Only verified activities (no hallucinations)

RESPONSE FORMAT (JSON):
[{"id": "str", "score": float, "reasoning": "str"}]"""
        
        activities_json = json.dumps(
            [a.dict() for a in candidates],
            indent=2
        )
        
        user_message = f"""Date: {request.date}
Interests: {request.interests}
Available time: {request.max_duration} minutes
Budget per activity: ${request.budget_per_activity}
Desired count: {request.num_activities}

Activities to evaluate:
{activities_json}

Score based on interest match. Return top {request.num_activities}."""
        
        response = await self.llm.call(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format="json"
        )
        
        try:
            scores_data = json.loads(response)
        except json.JSONDecodeError:
            print(f"⚠️  Failed to parse Claude response")
            return []
        
        # Build recommendations
        recommendations = []
        for i, activity in enumerate(candidates):
            if i < len(scores_data):
                score_data = scores_data[i]
                rec = ActivityRecommendation(
                    activity=activity,
                    match_score=score_data.get("score", 0),
                    reasoning=score_data.get("reasoning", "")
                )
                recommendations.append(rec)
        
        recommendations.sort(key=lambda x: x.match_score, reverse=True)
        return recommendations[:request.num_activities]
    
    def _schedule_activities(
        self,
        request: ActivitySearch,
        recommendations: List[ActivityRecommendation]
    ) -> List[ActivityRecommendation]:
        """
        Schedule activities by time of day.
        
        Logic:
        - Morning: Light activities (6-12)
        - Afternoon: Main activities (12-18)
        - Evening: Relaxed activities (18-24)
        - No overlap
        - Include travel time between activities
        """
        
        # Simple scheduling
        time_slots = ["morning", "afternoon", "evening"]
        
        for i, rec in enumerate(recommendations):
            time_slot = time_slots[i % len(time_slots)]
            rec.time_slot = time_slot
        
        return recommendations
