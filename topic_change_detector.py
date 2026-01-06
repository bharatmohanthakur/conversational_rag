"""
Topic Change Detector - Detects when user changes conversation topic.
Enables smooth transitions like ChatGPT/Claude/Gemini.
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger("TopicChangeDetector")


class TopicChangeType(Enum):
    """Types of topic changes."""
    NO_CHANGE = "no_change"  # Continuing same topic
    SLIGHT_SHIFT = "slight_shift"  # Related topic shift
    MAJOR_CHANGE = "major_change"  # Completely different topic
    RETURN_TO_PREVIOUS = "return_to_previous"  # Returning to earlier topic


class TopicChangeDetector:
    """
    Detects topic changes in conversation using semantic similarity.
    Helps system smoothly transition between topics.
    """

    def __init__(self, embedding_function):
        """
        Initialize topic change detector.

        Args:
            embedding_function: Function to embed text (returns List[float])
        """
        self.embedding_function = embedding_function

        # Thresholds for topic change detection
        self.major_change_threshold = 0.4  # Similarity < 0.4 = major change
        self.slight_shift_threshold = 0.7  # Similarity < 0.7 = slight shift

        # Topic keywords for quick detection
        self.hr_topics = {
            "leave": ["leave", "vacation", "time off", "annual leave", "sick leave", "maternity"],
            "insurance": ["insurance", "medical", "health", "coverage", "benefits"],
            "salary": ["salary", "pay", "compensation", "bonus", "allowance"],
            "policy": ["policy", "procedure", "rule", "guideline", "regulation"],
            "onboarding": ["onboarding", "joining", "new hire", "orientation", "induction"],
            "performance": ["performance", "appraisal", "review", "evaluation", "rating"],
            "training": ["training", "development", "learning", "course", "workshop"],
            "benefits": ["benefits", "perks", "entitlements", "privileges"],
            "termination": ["termination", "resignation", "notice period", "exit", "offboarding"],
            "attendance": ["attendance", "working hours", "shift", "schedule", "timesheet"],
        }

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _detect_topic_keywords(self, text: str) -> List[str]:
        """Detect topics using keyword matching (fast path)."""
        text_lower = text.lower()
        detected = []

        for topic, keywords in self.hr_topics.items():
            if any(keyword in text_lower for keyword in keywords):
                detected.append(topic)

        return detected

    def detect_topic_change(
        self,
        current_query: str,
        recent_context: List[str],
        topic_history: Optional[List[str]] = None
    ) -> Tuple[TopicChangeType, float, Optional[str]]:
        """
        Detect if current query represents a topic change.

        Args:
            current_query: Current user query
            recent_context: Recent conversation messages (last 3-5)
            topic_history: Optional list of topics discussed

        Returns:
            Tuple of (change_type, similarity_score, detected_topic)
        """
        if not recent_context or len(recent_context) == 0:
            return TopicChangeType.NO_CHANGE, 1.0, None

        # Fast path: Detect topics using keywords
        current_topics = self._detect_topic_keywords(current_query)

        if topic_history and current_topics:
            # Check if returning to a previous topic
            for topic in current_topics:
                if topic in topic_history[:-1]:  # Exclude most recent
                    logger.info(f"Detected return to previous topic: {topic}")
                    return TopicChangeType.RETURN_TO_PREVIOUS, 0.8, topic

        # Semantic similarity check using embeddings
        try:
            # Embed current query
            current_embedding = self.embedding_function(current_query)
            current_vec = np.array(current_embedding)

            # Compute similarity with recent context
            similarities = []
            for context_msg in recent_context[-3:]:  # Last 3 messages
                if not context_msg.strip():
                    continue

                context_embedding = self.embedding_function(context_msg)
                context_vec = np.array(context_embedding)

                similarity = self._cosine_similarity(current_vec, context_vec)
                similarities.append(similarity)

            if not similarities:
                return TopicChangeType.NO_CHANGE, 1.0, None

            # Use average similarity
            avg_similarity = np.mean(similarities)

            # Determine change type
            detected_topic = current_topics[0] if current_topics else None

            if avg_similarity < self.major_change_threshold:
                logger.info(f"Major topic change detected (similarity: {avg_similarity:.3f})")
                return TopicChangeType.MAJOR_CHANGE, avg_similarity, detected_topic
            elif avg_similarity < self.slight_shift_threshold:
                logger.info(f"Slight topic shift detected (similarity: {avg_similarity:.3f})")
                return TopicChangeType.SLIGHT_SHIFT, avg_similarity, detected_topic
            else:
                return TopicChangeType.NO_CHANGE, avg_similarity, detected_topic

        except Exception as e:
            logger.error(f"Error in topic change detection: {e}")
            # Fallback to keyword-based detection
            if len(current_topics) > 0:
                recent_topics = []
                for msg in recent_context[-2:]:
                    recent_topics.extend(self._detect_topic_keywords(msg))

                if not any(topic in recent_topics for topic in current_topics):
                    return TopicChangeType.MAJOR_CHANGE, 0.3, current_topics[0]

            return TopicChangeType.NO_CHANGE, 1.0, None

    def should_abandon_clarification(
        self,
        change_type: TopicChangeType,
        similarity: float
    ) -> bool:
        """
        Determine if clarification session should be abandoned due to topic change.

        Args:
            change_type: Type of topic change
            similarity: Similarity score

        Returns:
            True if clarification should be abandoned
        """
        # Abandon on major change
        if change_type == TopicChangeType.MAJOR_CHANGE:
            logger.info("Abandoning clarification due to major topic change")
            return True

        # Abandon on significant shift
        if change_type == TopicChangeType.SLIGHT_SHIFT and similarity < 0.5:
            logger.info("Abandoning clarification due to significant topic shift")
            return True

        return False

    def generate_transition_message(
        self,
        change_type: TopicChangeType,
        new_topic: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate smooth transition message for topic changes.

        Args:
            change_type: Type of topic change
            new_topic: Optional detected new topic

        Returns:
            Transition message or None
        """
        if change_type == TopicChangeType.MAJOR_CHANGE:
            if new_topic:
                return f"Sure, let's talk about {new_topic} instead."
            else:
                return "Sure, let me help you with that."

        elif change_type == TopicChangeType.RETURN_TO_PREVIOUS:
            if new_topic:
                return f"Going back to {new_topic}."
            else:
                return "Returning to your earlier question."

        elif change_type == TopicChangeType.SLIGHT_SHIFT:
            return None  # No explicit transition needed

        return None


# Global instance
_topic_change_detector: Optional[TopicChangeDetector] = None


def get_topic_change_detector() -> Optional[TopicChangeDetector]:
    """Get global topic change detector instance."""
    return _topic_change_detector


def init_topic_change_detector(embedding_function):
    """
    Initialize global topic change detector.

    Args:
        embedding_function: Function to embed text
    """
    global _topic_change_detector
    _topic_change_detector = TopicChangeDetector(embedding_function)
    logger.info("Initialized topic change detector")
