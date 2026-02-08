from functools import lru_cache
from typing import Dict, Any

class AIService:
    """Service for handling AI-powered lead analysis and insights."""

    @staticmethod
    def generate_contact_insight(contact: Dict[str, Any]) -> str:
        """
        Generates a descriptive insight for a HubSpot contact.
        Uses an internal cached method to avoid repetitive calculations.
        """
        contact_id = contact.get('id', 'unknown')
        properties = contact.get('properties', {})
        
        # Convert properties to a hashable format (tuple of items) for caching
        prop_tuple = tuple(sorted(properties.items())) if isinstance(properties, dict) else ()
        
        return AIService._cached_insight_logic(contact_id, prop_tuple)

    @staticmethod
    @lru_cache(maxsize=128)
    def _cached_insight_logic(contact_id: str, prop_tuple: tuple) -> str:
        """Internal cached logic for insight generation."""
        properties = dict(prop_tuple)
        company = properties.get('company', 'Unknown Company')
        firstname = properties.get('firstname', 'This contact')
        
        # Rule-based insight generation
        insight = f"💡 {firstname} works at {company}."
        
        # Add basic behavior analysis (if fields exist)
        visits = properties.get('hs_analytics_num_visits')
        if visits and str(visits).isdigit() and int(visits) > 5:
            insight += f" They are a highly engaged visitor with {visits} visits."
        else:
            insight += " They were recently updated in HubSpot."
            
        return insight
