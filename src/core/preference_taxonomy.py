"""Global preference taxonomy and conservative free-text normalization."""

from __future__ import annotations

import re
from typing import Iterable, List


PREFERENCE_ALIASES = {
    "dietary_restrictions": {
        "vegetarian": "Vegetarian",
        "vegan": "Vegan",
        "gluten free": "Gluten-Free",
        "gluten-free": "Gluten-Free",
        "lactose intolerant": "Dairy-Free / Lactose-Intolerant",
        "dairy free": "Dairy-Free / Lactose-Intolerant",
        "dairy-free": "Dairy-Free / Lactose-Intolerant",
        "halal": "Halal",
        "kosher": "Kosher",
        "jain": "Jain",
        "nut free": "Nut-Free",
        "nut-free": "Nut-Free",
        "shellfish free": "Shellfish-Free",
        "shellfish-free": "Shellfish-Free",
        "low sugar": "Diabetic / Low Sugar",
        "diabetic": "Diabetic / Low Sugar",
    },
    "accessibility_needs": {
        "wheelchair": "Wheelchair Accessible",
        "wheelchair accessible": "Wheelchair Accessible",
        "limited mobility": "Limited Mobility / Minimal Walking",
        "limited walking": "Limited Mobility / Minimal Walking",
        "minimal walking": "Limited Mobility / Minimal Walking",
        "visual assistance": "Visual Assistance / Braille",
        "braille": "Visual Assistance / Braille",
        "hearing assistance": "Hearing Assistance",
        "neurodivergent": "Neurodivergent / Quiet Spaces",
        "quiet spaces": "Neurodivergent / Quiet Spaces",
        "assistance animal": "Assistance Animal Friendly",
        "service animal": "Assistance Animal Friendly",
    },
    "transport_preferences": {
        "walk": "Walking",
        "walking": "Walking",
        "metro": "Public Transport (Metro/Bus)",
        "bus": "Public Transport (Metro/Bus)",
        "public transport": "Public Transport (Metro/Bus)",
        "public transportation": "Public Transport (Metro/Bus)",
        "taxi": "Taxis & Rideshares",
        "taxis": "Taxis & Rideshares",
        "cab": "Taxis & Rideshares",
        "cabs": "Taxis & Rideshares",
        "uber": "Taxis & Rideshares",
        "rideshare": "Taxis & Rideshares",
        "rental car": "Rental Car / Self-Drive",
        "self drive": "Rental Car / Self-Drive",
        "chauffeur": "Private Transfer / Chauffeur",
        "private transfer": "Private Transfer / Chauffeur",
        "bicycle": "Bicycle",
        "bike": "Bicycle",
        "train": "Intercity Trains",
        "intercity train": "Intercity Trains",
    },
    "accommodation_preferences": {
        "hotel": "Hotel",
        "hostel": "Hostel",
        "serviced apartment": "Serviced Apartment",
        "apartment": "Serviced Apartment",
        "boutique hotel": "Boutique Hotel",
        "vacation rental": "Vacation Rental",
        "budget": "Budget / Backpacker",
        "backpacker": "Budget / Backpacker",
        "mid budget": "Mid-Range",
        "mid-range": "Mid-Range",
        "mid range": "Mid-Range",
        "luxury": "Luxury / 5-Star",
        "5 star": "Luxury / 5-Star",
        "city center": "City Center",
        "city centre": "City Center",
        "major attractions": "Near Major Attractions",
        "near attractions": "Near Major Attractions",
        "quiet neighborhood": "Quiet Neighborhood",
        "quiet neighbourhood": "Quiet Neighborhood",
        "near transit": "Near Transit Hub",
        "near metro": "Near Transit Hub",
    },
}


PREFERENCE_OPTIONS = {
    "interests": [
        "Culture",
        "Food",
        "History",
        "Nature",
        "Shopping",
        "Adventure",
        "Relaxation",
        "Architecture",
    ],
    "dietary_restrictions": [
        "Vegetarian",
        "Vegan",
        "Gluten-Free",
        "Dairy-Free / Lactose-Intolerant",
        "Halal",
        "Kosher",
        "Jain",
        "Nut-Free",
        "Shellfish-Free",
        "Diabetic / Low Sugar",
    ],
    "accessibility_needs": [
        "Wheelchair Accessible",
        "Limited Mobility / Minimal Walking",
        "Visual Assistance / Braille",
        "Hearing Assistance",
        "Neurodivergent / Quiet Spaces",
        "Assistance Animal Friendly",
    ],
    "transport_preferences": [
        "Walking",
        "Public Transport (Metro/Bus)",
        "Taxis & Rideshares",
        "Rental Car / Self-Drive",
        "Private Transfer / Chauffeur",
        "Bicycle",
        "Intercity Trains",
    ],
    "accommodation_preferences": [
        "Budget / Backpacker",
        "Mid-Range",
        "Luxury / 5-Star",
    ],
}


def _parts(value: str) -> List[str]:
    return [
        part.strip()
        for part in re.split(r",|;|\band\b|\bor\b|/", value, flags=re.I)
        if part.strip()
    ]


def normalize_preference_values(
    field_name: str,
    values: str | Iterable[str] | None,
) -> List[str]:
    """Normalize known aliases while retaining unknown custom text."""

    if values is None:
        return []
    if isinstance(values, str):
        if values.strip().lower() in {
            "none", "no", "no preference", "n/a", "na", "skip",
        }:
            return []
        raw_values = _parts(values)
    else:
        raw_values = []
        for value in values:
            raw_values.extend(_parts(str(value)))

    aliases = PREFERENCE_ALIASES.get(field_name, {})
    normalized: List[str] = []
    for raw in raw_values:
        cleaned = re.sub(r"\s+", " ", raw).strip()
        lowered = cleaned.lower()
        matches: List[str] = []
        for alias, canonical in sorted(
            aliases.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if alias == "budget" and "mid budget" in lowered:
                continue
            if lowered == alias or alias in lowered:
                if canonical not in matches:
                    matches.append(canonical)
        for value in matches or [cleaned]:
            if value and value not in normalized:
                normalized.append(value)
    return normalized
