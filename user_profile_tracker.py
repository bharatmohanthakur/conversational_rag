"""
User Profile Tracker - Remembers user context across conversation.
Extracts and maintains implicit information like role, location, department.
"""

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict, field

logger = logging.getLogger("UserProfileTracker")


@dataclass
class UserProfile:
    """User profile with extracted context."""
    user_id: str

    # Explicitly stated information
    role: Optional[str] = None
    country: Optional[str] = None
    department: Optional[str] = None
    brand: Optional[str] = None
    employment_type: Optional[str] = None

    # Implicit preferences
    preferred_detail_level: str = "medium"  # brief, medium, detailed
    interaction_style: str = "neutral"  # formal, neutral, casual

    # Conversation metadata
    topics_discussed: List[str] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    conversation_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        """Create from dictionary."""
        return cls(**data)

    def get_context_string(self) -> str:
        """Get user context as formatted string."""
        context_parts = []

        if self.role:
            context_parts.append(f"Role: {self.role}")
        if self.country:
            context_parts.append(f"Location: {self.country}")
        if self.department:
            context_parts.append(f"Department: {self.department}")
        if self.brand:
            context_parts.append(f"Brand: {self.brand}")

        return " | ".join(context_parts) if context_parts else "No context available"


class UserProfileTracker:
    """
    Tracks and extracts user profile information from conversations.
    Remembers context to avoid re-asking questions.
    """

    def __init__(self, conversation_manager):
        """
        Initialize user profile tracker.

        Args:
            conversation_manager: ConversationManager for persistence
        """
        self.conv_manager = conversation_manager
        self.profiles: Dict[str, UserProfile] = {}

        # Extraction patterns
        self.country_patterns = {
            r'\b(lebanon|lebanese)\b': 'Lebanon',
            r'\b(saudi|ksa|saudi arabia)\b': 'Saudi Arabia',
            r'\b(uae|dubai|emirates)\b': 'UAE',
            r'\b(egypt|egyptian)\b': 'Egypt',
            r'\b(kuwait|kuwaiti)\b': 'Kuwait',
            r'\b(qatar|qatari)\b': 'Qatar',
            r'\b(jordan|jordanian)\b': 'Jordan',
            r'\b(iraq|iraqi)\b': 'Iraq',
            r'\b(bahrain)\b': 'Bahrain',
        }

        self.role_patterns = {
            r'\b(manager|managing)\b': 'Manager',
            r'\b(senior manager|senior leadership)\b': 'Senior Manager',
            r'\b(director)\b': 'Director',
            r'\b(executive|c-level)\b': 'Executive',
            r'\b(staff|employee|team member)\b': 'Staff',
            r'\b(supervisor)\b': 'Supervisor',
            r'\b(coordinator)\b': 'Coordinator',
            r'\b(analyst)\b': 'Analyst',
            r'\b(assistant)\b': 'Assistant',
        }

        self.department_patterns = {
            r'\b(hr|human resources)\b': 'HR',
            r'\b(it|tech|technology)\b': 'IT',
            r'\b(finance|accounting)\b': 'Finance',
            r'\b(marketing)\b': 'Marketing',
            r'\b(sales|retail)\b': 'Sales',
            r'\b(operations)\b': 'Operations',
            r'\b(legal)\b': 'Legal',
            r'\b(procurement|supply chain)\b': 'Procurement',
        }

        self.brand_patterns = {
            r'\b(azadea group|azadea)\b': 'Azadea Group',
            r'\b(zara)\b': 'Zara',
            r'\b(mango)\b': 'Mango',
            r'\b(oysho)\b': 'Oysho',
            r'\b(pull\s*&?\s*bear|pull and bear)\b': 'Pull & Bear',
            r'\b(massimo dutti)\b': 'Massimo Dutti',
            r'\b(bershka)\b': 'Bershka',
            r'\b(stradivarius)\b': 'Stradivarius',
        }

    def get_profile(self, user_id: str) -> UserProfile:
        """
        Get or create user profile.

        Args:
            user_id: User identifier

        Returns:
            UserProfile instance
        """
        if user_id not in self.profiles:
            # Try to load from storage
            profile = self._load_profile(user_id)
            if profile:
                self.profiles[user_id] = profile
            else:
                # Create new profile
                self.profiles[user_id] = UserProfile(user_id=user_id)

        return self.profiles[user_id]

    def extract_from_text(self, text: str, user_id: str) -> Dict[str, Any]:
        """
        Extract profile information from text.

        Args:
            text: Text to extract from
            user_id: User ID

        Returns:
            Dictionary of extracted information
        """
        text_lower = text.lower()
        extracted = {}

        # Extract country
        for pattern, country in self.country_patterns.items():
            if re.search(pattern, text_lower):
                extracted['country'] = country
                break

        # Extract role
        for pattern, role in self.role_patterns.items():
            if re.search(pattern, text_lower):
                extracted['role'] = role
                break

        # Extract department
        for pattern, dept in self.department_patterns.items():
            if re.search(pattern, text_lower):
                extracted['department'] = dept
                break

        # Extract brand
        for pattern, brand in self.brand_patterns.items():
            if re.search(pattern, text_lower):
                extracted['brand'] = brand
                break

        return extracted

    def update_profile(
        self,
        user_id: str,
        message: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Update user profile from conversation message.

        Args:
            user_id: User identifier
            message: Message content
            role: Message role (user/assistant)
            metadata: Optional metadata
        """
        profile = self.get_profile(user_id)

        # Only extract from user messages
        if role == "user":
            extracted = self.extract_from_text(message, user_id)

            # Update profile with extracted info
            updated = False
            for key, value in extracted.items():
                if hasattr(profile, key) and getattr(profile, key) is None:
                    setattr(profile, key, value)
                    updated = True
                    logger.info(f"Extracted {key}={value} for user {user_id}")

            if updated:
                profile.last_updated = datetime.now().isoformat()
                self._save_profile(profile)

        # Increment conversation count
        profile.conversation_count += 1

    def add_topic(self, user_id: str, topic: str):
        """
        Add a discussed topic to profile.

        Args:
            user_id: User identifier
            topic: Topic discussed
        """
        profile = self.get_profile(user_id)
        if topic not in profile.topics_discussed:
            profile.topics_discussed.append(topic)
            # Keep only last 10 topics
            if len(profile.topics_discussed) > 10:
                profile.topics_discussed = profile.topics_discussed[-10:]
            self._save_profile(profile)

    def has_context(self, user_id: str, attribute: str) -> bool:
        """
        Check if user profile has a specific attribute.

        Args:
            user_id: User identifier
            attribute: Attribute name (e.g., 'country', 'role')

        Returns:
            True if attribute exists and is not None
        """
        profile = self.get_profile(user_id)
        return hasattr(profile, attribute) and getattr(profile, attribute) is not None

    def get_context(self, user_id: str, attribute: str) -> Optional[str]:
        """
        Get specific context attribute.

        Args:
            user_id: User identifier
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        profile = self.get_profile(user_id)
        return getattr(profile, attribute, None)

    def clear_profile(self, user_id: str):
        """
        Clear user profile.

        Args:
            user_id: User identifier
        """
        if user_id in self.profiles:
            del self.profiles[user_id]

        # Clear from storage
        if self.conv_manager.redis_client:
            key = f"user_profile:{user_id}"
            self.conv_manager.redis_client.delete(key)
        else:
            if hasattr(self.conv_manager, '_user_profiles'):
                if user_id in self.conv_manager._user_profiles:
                    del self.conv_manager._user_profiles[user_id]

    def _save_profile(self, profile: UserProfile):
        """Save profile to storage."""
        try:
            import json
            from datetime import timedelta

            key = f"user_profile:{profile.user_id}"
            data = json.dumps(profile.to_dict(), ensure_ascii=False)

            if self.conv_manager.redis_client:
                # Save to Redis with 30 days TTL
                self.conv_manager.redis_client.setex(
                    key,
                    timedelta(days=30),
                    data
                )
            else:
                # Fallback to memory
                if not hasattr(self.conv_manager, '_user_profiles'):
                    self.conv_manager._user_profiles = {}
                self.conv_manager._user_profiles[profile.user_id] = data

        except Exception as e:
            logger.error(f"Failed to save user profile: {e}")

    def _load_profile(self, user_id: str) -> Optional[UserProfile]:
        """Load profile from storage."""
        try:
            import json

            key = f"user_profile:{user_id}"

            if self.conv_manager.redis_client:
                data = self.conv_manager.redis_client.get(key)
                if data:
                    return UserProfile.from_dict(json.loads(data))
            else:
                # Fallback to memory
                if hasattr(self.conv_manager, '_user_profiles'):
                    data = self.conv_manager._user_profiles.get(user_id)
                    if data:
                        return UserProfile.from_dict(json.loads(data))

            return None

        except Exception as e:
            logger.error(f"Failed to load user profile: {e}")
            return None


# Global instance
_user_profile_tracker: Optional[UserProfileTracker] = None


def get_user_profile_tracker() -> Optional[UserProfileTracker]:
    """Get global user profile tracker instance."""
    return _user_profile_tracker


def init_user_profile_tracker(conversation_manager):
    """
    Initialize global user profile tracker.

    Args:
        conversation_manager: ConversationManager instance
    """
    global _user_profile_tracker
    _user_profile_tracker = UserProfileTracker(conversation_manager)
    logger.info("Initialized user profile tracker")
