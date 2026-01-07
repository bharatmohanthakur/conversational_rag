"""
LLM-based Intelligent Classifier - Zero hardcoding approach.
Uses LLM's natural language understanding instead of hardcoded regex patterns.

This replaces ALL hardcoded patterns with intelligent LLM-based classification.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger("LLMClassifier")


class QueryType(Enum):
    """Query type classification."""
    GREETING = "greeting"
    THANKS = "thanks"
    CASUAL = "casual"
    QUESTION = "question"
    STATEMENT = "statement"
    COMMAND = "command"
    CLARIFICATION_ANSWER = "clarification_answer"


class QueryComplexity(Enum):
    """Query complexity classification."""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ConfidenceLevel(Enum):
    """Confidence in answering query."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class ClassificationResult:
    """Result of LLM classification."""
    query_type: QueryType
    complexity: QueryComplexity
    confidence: float  # 0.0 to 1.0
    is_greeting: bool
    is_question: bool
    is_clarification_answer: bool
    requires_clarification: bool
    missing_context: List[str]  # What context is missing (e.g., "country", "position")
    reasoning: str
    suggested_assumptions: Dict[str, str]  # Suggested default assumptions


class LLMClassifier:
    """
    LLM-based classifier that uses natural language understanding
    instead of hardcoded patterns.

    Philosophy: Let the LLM do what it does best - understand language.
    No regex, no hardcoded lists, no magic patterns.
    """

    def __init__(self, llm_client, deployment_name: str, cache_enabled: bool = True):
        """
        Initialize LLM classifier.

        Args:
            llm_client: LLM client for classification
            deployment_name: Azure deployment name
            cache_enabled: Enable caching for repeated classifications
        """
        self.llm_client = llm_client
        self.deployment_name = deployment_name
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, ClassificationResult] = {}

    def classify_query(
        self,
        query: str,
        conversation_context: Optional[List[str]] = None,
        active_clarification: bool = False
    ) -> ClassificationResult:
        """
        Classify query using LLM's natural language understanding.

        Args:
            query: User query
            conversation_context: Recent conversation messages
            active_clarification: Whether there's an active clarification session

        Returns:
            ClassificationResult with full analysis
        """
        # Check cache first
        cache_key = f"{query}_{active_clarification}"
        if self.cache_enabled and cache_key in self._cache:
            logger.debug(f"Cache hit for query: {query[:50]}")
            return self._cache[cache_key]

        # Build context string
        context_str = ""
        if conversation_context:
            context_str = "Recent conversation:\n" + "\n".join(conversation_context[-3:])

        # Classification prompt
        prompt = f"""Analyze this user query and classify it comprehensively.

Query: "{query}"

{context_str}

Active clarification session: {active_clarification}

Provide a complete analysis in JSON format with these fields:

1. **query_type**: One of:
   - "greeting": Hi, hello, thanks, bye, casual acknowledgment
   - "question": Asking for information
   - "command": Requesting an action (list, show, explain)
   - "statement": Making a statement
   - "clarification_answer": Answering a clarification question
   - "casual": Casual response (ok, sure, yes, no)

2. **complexity**: One of:
   - "simple": Single, straightforward question
   - "moderate": Multiple aspects or some ambiguity
   - "complex": Multi-part, comparison, aggregation needed

3. **confidence**: Float 0-1 for classification confidence

4. **is_greeting**: Boolean - is this a greeting/thanks/casual?

5. **is_question**: Boolean - is this asking for information?

6. **is_clarification_answer**: Boolean - answering a clarification question?
   (Only true if active_clarification=True AND query looks like an answer, not a new question)

7. **requires_clarification**: Boolean - does answering this need more context?

8. **missing_context**: Array of strings - what's missing?
   Examples: ["country", "position", "leave type", "specific brand"]
   Empty array if nothing missing.

9. **reasoning**: Brief explanation of classification

10. **suggested_assumptions**: Object with default assumptions if missing_context exists
    Examples: {{"country": "Lebanon (headquarters)", "position": "staff-level"}}

IMPORTANT Rules:
- If active_clarification=True and query is short (1-5 words) and doesn't start with question words, it's likely a "clarification_answer"
- If query starts with "What", "How", "When", etc., it's a new "question", not a clarification answer
- Be smart about missing context - only flag it if the answer TRULY varies significantly
- Suggest reasonable defaults for missing context

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing and classifying user queries. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            # Parse JSON response
            result_dict = json.loads(response.choices[0].message.content)

            # Create result object
            result = ClassificationResult(
                query_type=QueryType(result_dict.get("query_type", "question")),
                complexity=QueryComplexity(result_dict.get("complexity", "simple")),
                confidence=result_dict.get("confidence", 0.5),
                is_greeting=result_dict.get("is_greeting", False),
                is_question=result_dict.get("is_question", True),
                is_clarification_answer=result_dict.get("is_clarification_answer", False),
                requires_clarification=result_dict.get("requires_clarification", False),
                missing_context=result_dict.get("missing_context", []),
                reasoning=result_dict.get("reasoning", ""),
                suggested_assumptions=result_dict.get("suggested_assumptions", {})
            )

            # Cache result
            if self.cache_enabled:
                self._cache[cache_key] = result

            logger.info(f"Classified query: type={result.query_type.value}, "
                       f"complexity={result.complexity.value}, "
                       f"requires_clarification={result.requires_clarification}")

            return result

        except Exception as e:
            logger.error(f"Error in LLM classification: {e}")
            # Fallback to safe defaults
            return ClassificationResult(
                query_type=QueryType.QUESTION,
                complexity=QueryComplexity.SIMPLE,
                confidence=0.5,
                is_greeting=False,
                is_question=True,
                is_clarification_answer=False,
                requires_clarification=False,
                missing_context=[],
                reasoning=f"Error: {str(e)}",
                suggested_assumptions={}
            )

    def detect_user_profile_info(
        self,
        query: str,
        conversation_history: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Extract user profile information from query using LLM.
        No hardcoded patterns - LLM understands context.

        Args:
            query: User query or statement
            conversation_history: Recent conversation

        Returns:
            Dictionary of extracted profile attributes
        """
        context_str = ""
        if conversation_history:
            context_str = "Conversation history:\n" + "\n".join(conversation_history[-5:])

        prompt = f"""Extract any user profile information from this query.

Query: "{query}"

{context_str}

Look for:
- Role/Position (manager, staff, senior, director, etc.)
- Country/Location (Lebanon, UAE, Saudi Arabia, etc.)
- Department (HR, IT, Finance, Sales, etc.)
- Brand (Azadea, Zara, Mango, etc.)
- Employment type (full-time, part-time, contract)

Return JSON with extracted fields. Use null for fields not mentioned.

Example:
{{
  "role": "Senior Manager",
  "country": "Lebanon",
  "department": null,
  "brand": null,
  "employment_type": "full-time"
}}

If the user says "I'm a manager in Dubai", extract role="Manager" and country="UAE/Dubai".
If they say "I work at Zara in Lebanon", extract brand="Zara" and country="Lebanon".

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured information from text. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=200
            )

            result = json.loads(response.choices[0].message.content)

            # Filter out null values
            extracted = {k: v for k, v in result.items() if v is not None}

            if extracted:
                logger.info(f"Extracted profile info: {extracted}")

            return extracted

        except Exception as e:
            logger.error(f"Error extracting profile info: {e}")
            return {}

    def detect_topic_change(
        self,
        current_query: str,
        recent_queries: List[str]
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Detect topic change using LLM understanding.
        No hardcoded topic keywords.

        Args:
            current_query: Current user query
            recent_queries: Recent queries from conversation

        Returns:
            Tuple of (is_major_change, similarity_score, new_topic)
        """
        if not recent_queries:
            return False, 1.0, None

        recent_str = "\n".join([f"- {q}" for q in recent_queries[-3:]])

        prompt = f"""Analyze if the current query represents a topic change from recent conversation.

Recent queries:
{recent_str}

Current query: "{current_query}"

Determine:
1. Is this a MAJOR topic change? (completely different subject)
2. Similarity score (0-1): How related is this to recent queries?
3. New topic (if changed): Brief name of the new topic

Examples:
- Recent: "What's the leave policy?" Current: "How do I apply for leave?" → SAME TOPIC (similarity: 0.9)
- Recent: "Tell me about leave" Current: "What's the insurance coverage?" → MAJOR CHANGE (similarity: 0.2, new topic: "insurance")

Respond in JSON:
{{
  "is_major_change": true/false,
  "similarity_score": 0.0-1.0,
  "new_topic": "string or null",
  "reasoning": "brief explanation"
}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding conversation flow and topic changes. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )

            result = json.loads(response.choices[0].message.content)

            is_major = result.get("is_major_change", False)
            similarity = result.get("similarity_score", 0.5)
            topic = result.get("new_topic")

            if is_major:
                logger.info(f"Major topic change detected: {topic} (similarity: {similarity})")

            return is_major, similarity, topic

        except Exception as e:
            logger.error(f"Error detecting topic change: {e}")
            return False, 0.5, None

    def detect_frustration(self, query: str) -> Tuple[bool, float]:
        """
        Detect user frustration using LLM understanding.
        No hardcoded frustration phrases.

        Args:
            query: User query

        Returns:
            Tuple of (is_frustrated, confidence)
        """
        prompt = f"""Analyze if this user message shows frustration, impatience, or wanting to skip clarification.

Message: "{query}"

Signs of frustration:
- Impatient language: "just tell me", "just give me"
- Indifference: "any", "whatever", "doesn't matter", "I don't care"
- Wanting to skip: "skip", "proceed", "continue", "move on"
- Dismissive: "fine", "okay whatever", "nevermind"
- Short frustrated responses: "any!", "just answer!"

Respond in JSON:
{{
  "is_frustrated": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding user emotions and intent. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=150
            )

            result = json.loads(response.choices[0].message.content)

            is_frustrated = result.get("is_frustrated", False)
            confidence = result.get("confidence", 0.5)

            if is_frustrated:
                logger.info(f"Frustration detected: {query[:50]} (confidence: {confidence})")

            return is_frustrated, confidence

        except Exception as e:
            logger.error(f"Error detecting frustration: {e}")
            return False, 0.0

    def assess_answer_confidence(
        self,
        query: str,
        available_context: str,
        missing_info: List[str]
    ) -> Tuple[ConfidenceLevel, Dict[str, str]]:
        """
        Assess confidence in answering query given context.
        Suggests intelligent defaults for missing information.

        Args:
            query: User query
            available_context: Retrieved context
            missing_info: List of missing information

        Returns:
            Tuple of (confidence_level, suggested_assumptions)
        """
        prompt = f"""Assess confidence in answering this query given the available context.

Query: "{query}"

Available context: {len(available_context)} characters of retrieved information

Missing information: {missing_info if missing_info else "None"}

Determine:
1. Confidence level: "high", "medium", "low", or "very_low"
   - high: Can answer accurately without assumptions
   - medium: Can answer with reasonable assumptions
   - low: Answer requires some guessing
   - very_low: Cannot answer without critical information

2. Suggested assumptions: If information is missing, suggest intelligent defaults
   Example: If country is missing, suggest "Lebanon (headquarters)" as default

Respond in JSON:
{{
  "confidence_level": "high/medium/low/very_low",
  "suggested_assumptions": {{"field": "value"}},
  "reasoning": "brief explanation",
  "should_ask_clarification": true/false
}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at assessing information completeness. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )

            result = json.loads(response.choices[0].message.content)

            confidence = ConfidenceLevel(result.get("confidence_level", "medium"))
            assumptions = result.get("suggested_assumptions", {})

            logger.info(f"Answer confidence: {confidence.value}, assumptions: {assumptions}")

            return confidence, assumptions

        except Exception as e:
            logger.error(f"Error assessing confidence: {e}")
            return ConfidenceLevel.MEDIUM, {}

    def clear_cache(self):
        """Clear classification cache."""
        self._cache.clear()
        logger.info("Classification cache cleared")


# Global instance
_llm_classifier: Optional[LLMClassifier] = None


def get_llm_classifier() -> Optional[LLMClassifier]:
    """Get global LLM classifier instance."""
    return _llm_classifier


def init_llm_classifier(llm_client, deployment_name: str, cache_enabled: bool = True):
    """
    Initialize global LLM classifier.

    Args:
        llm_client: LLM client
        deployment_name: Azure deployment name
        cache_enabled: Enable caching
    """
    global _llm_classifier
    _llm_classifier = LLMClassifier(
        llm_client=llm_client,
        deployment_name=deployment_name,
        cache_enabled=cache_enabled
    )
    logger.info("Initialized LLM-based classifier (zero hardcoding approach)")
