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

        # Classification prompt with Chain of Thought
        prompt = f"""Analyze this user query and classify it comprehensively using step-by-step reasoning.

Query: "{query}"

{context_str}

Active clarification session: {active_clarification}

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through these questions step-by-step:

1. What is the user trying to do with this query?
   - Are they greeting? (hi, hello, thanks, bye)
   - Are they asking for information? (what, how, when, where)
   - Are they giving an answer? (short response in clarification context)
   - Are they making a statement or command?

2. Context analysis:
   - Is there an active clarification session? If yes, is this an answer to it or a new question?
   - Look for question words (what, how, when) → likely a NEW question, not a clarification answer
   - If query is 1-5 words with no question words and clarification is active → likely answering

3. Complexity assessment:
   - How many topics/aspects does this query have?
   - Does it require comparison, aggregation, or multi-step reasoning?
   - Is it straightforward or ambiguous?

4. Missing information:
   - Does answering this query require knowing: country, position, department, leave type, etc.?
   - Would the answer be SIGNIFICANTLY different based on these factors?
   - Can we make reasonable default assumptions?

5. Default assumptions:
   - If country is missing → assume "Lebanon (headquarters)"
   - If position is missing → assume "staff-level"
   - If leave type is missing → provide general overview

**STEP 2 - FINAL CLASSIFICATION:**
Based on your reasoning above, provide a complete analysis in JSON format:

{{
  "query_type": "greeting|question|command|statement|clarification_answer|casual",
  "complexity": "simple|moderate|complex",
  "confidence": 0.0-1.0,
  "is_greeting": true/false,
  "is_question": true/false,
  "is_clarification_answer": true/false,
  "requires_clarification": true/false,
  "missing_context": ["country", "position", ...] or [],
  "reasoning": "Brief explanation of your step-by-step thinking",
  "suggested_assumptions": {{"field": "default value"}}
}}

CRITICAL Rules:
- If active_clarification=True and query is short (1-5 words) and doesn't start with question words → likely "clarification_answer"
- If query starts with "What", "How", "When", etc. → it's a "question", NOT a clarification answer
- Only flag missing_context if the answer would be SIGNIFICANTLY different
- Always suggest reasonable defaults for missing context

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing and classifying user queries. Use step-by-step reasoning to think through each decision. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800
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

        prompt = f"""Extract user profile information from this query using step-by-step reasoning.

Query: "{query}"

{context_str}

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through the extraction step-by-step:

1. Role/Position indicators:
   - Look for job titles: manager, director, staff, senior, coordinator, lead, etc.
   - Look for role descriptions: "I work as...", "I'm a...", "my position is..."
   - Normalize titles: "senior manager" → "Senior Manager"

2. Country/Location indicators:
   - Look for countries: Lebanon, UAE, Saudi Arabia, Egypt, etc.
   - Look for cities and map to countries: Dubai/Abu Dhabi → UAE, Beirut → Lebanon, Riyadh → Saudi Arabia
   - Look for phrases: "in Lebanon", "at our Dubai office", "based in..."
   - Format consistently: "UAE/Dubai" for city mentions

3. Department indicators:
   - Look for departments: HR, IT, Finance, Sales, Marketing, Operations, etc.
   - Look for phrases: "work in HR", "IT department", "from finance"

4. Brand indicators:
   - Look for brand names: Azadea, Zara, Mango, Starbucks, etc.
   - Look for phrases: "at Zara", "work for Mango", "Azadea group"

5. Employment type indicators:
   - Look for: full-time, part-time, contract, temporary, permanent
   - Infer from context if not explicitly stated

**STEP 2 - EXTRACTION:**
Based on your analysis, extract profile information.

Examples:
- "I'm a manager in Dubai" → {{"role": "Manager", "country": "UAE/Dubai"}}
- "I work at Zara in Lebanon" → {{"brand": "Zara", "country": "Lebanon"}}
- "Senior HR director based in Beirut" → {{"role": "Senior HR Director", "country": "Lebanon/Beirut", "department": "HR"}}

Return JSON with extracted fields. Use null for fields not mentioned:

{{
  "role": "string or null",
  "country": "string or null",
  "department": "string or null",
  "brand": "string or null",
  "employment_type": "string or null"
}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured information from text. Use step-by-step reasoning to analyze the text carefully. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=400
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

        prompt = f"""Analyze if the current query represents a topic change using step-by-step reasoning.

Recent queries:
{recent_str}

Current query: "{current_query}"

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through the topic change step-by-step:

1. Topic extraction:
   - What is the main topic of recent queries? (leave, insurance, salary, benefits, etc.)
   - What is the main topic of the current query?
   - Are these topics in the same domain/category?

2. Semantic similarity assessment:
   - Do the queries share common keywords or concepts?
   - Are they asking about the same policy area?
   - Is the current query a follow-up or a completely new question?

3. Examples for reference:
   - "leave policy" → "how to apply for leave" = SAME TOPIC (similarity: 0.9)
   - "leave policy" → "insurance coverage" = MAJOR CHANGE (similarity: 0.2)
   - "annual leave" → "sick leave" = SLIGHT SHIFT (similarity: 0.7, same domain)
   - "maternity leave" → "salary structure" = MAJOR CHANGE (similarity: 0.3)

4. Change classification:
   - Similarity > 0.7 → SAME TOPIC (no major change)
   - Similarity 0.4-0.7 → RELATED TOPIC (slight shift, no major change)
   - Similarity < 0.4 → MAJOR CHANGE (completely different topic)

**STEP 2 - CLASSIFICATION:**
Based on your analysis, determine:

{{
  "is_major_change": true/false,
  "similarity_score": 0.0-1.0 (float),
  "new_topic": "brief name of new topic if major change, else null",
  "reasoning": "brief explanation of your step-by-step thinking"
}}

Guidelines:
- is_major_change: true only if similarity < 0.4
- similarity_score: 0.0 (completely different) to 1.0 (identical/highly related)
- new_topic: only populate if is_major_change=true

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding conversation flow and topic changes. Use step-by-step reasoning to analyze semantic similarity. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=400
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
        prompt = f"""Analyze if this user message shows frustration using step-by-step reasoning.

Message: "{query}"

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through the frustration detection step-by-step:

1. Tone analysis:
   - Is the language polite or impatient?
   - Are there exclamation marks or capital letters indicating emotion?
   - Is the message curt/short in a way that suggests frustration?

2. Frustration indicators:
   - Impatient language: "just tell me", "just give me", "come on"
   - Indifference: "any", "whatever", "doesn't matter", "I don't care", "anything"
   - Skip signals: "skip", "proceed", "continue", "move on", "forget it"
   - Dismissive: "fine", "okay whatever", "nevermind", "enough"
   - Direct demands: "just answer!", "tell me now!"

3. Context consideration:
   - Is "any" used in frustration ("any is fine!") or genuine choice ("any of these options")?
   - Is "whatever" dismissive ("whatever, just answer") or agreeable ("whatever works for you")?
   - Single word answers like "any!", "whatever!" are usually frustrated

4. Confidence assessment:
   - Clear frustration signals (multiple indicators) → 0.8-1.0
   - Some frustration signals (one strong indicator) → 0.5-0.8
   - Ambiguous (could be interpreted either way) → 0.3-0.5
   - No frustration (polite, patient) → 0.0-0.3

**STEP 2 - CLASSIFICATION:**
Based on your analysis, determine:

{{
  "is_frustrated": true/false,
  "confidence": 0.0-1.0 (float),
  "reasoning": "brief explanation of your step-by-step thinking"
}}

Examples:
- "just give me any answer" → {{"is_frustrated": true, "confidence": 0.9}}
- "whatever works is fine" → {{"is_frustrated": false, "confidence": 0.8}}
- "any!" → {{"is_frustrated": true, "confidence": 0.95}}
- "I'd like to know more about this" → {{"is_frustrated": false, "confidence": 1.0}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding user emotions and intent. Use step-by-step reasoning to analyze tone and context carefully. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=350
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
        prompt = f"""Assess confidence in answering this query using step-by-step reasoning.

Query: "{query}"

Available context: {len(available_context)} characters of retrieved information

Missing information: {missing_info if missing_info else "None"}

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through the confidence assessment step-by-step:

1. Context completeness:
   - How much relevant information is available? ({len(available_context)} characters)
   - Does the context directly address the query?
   - Are there gaps in the information?

2. Missing information impact:
   - What information is missing: {missing_info if missing_info else "None"}
   - Would the answer be SIGNIFICANTLY different with this information?
   - Can we make reasonable default assumptions?

3. Assumption reasonableness:
   - If country is missing → assume "Lebanon (headquarters)" is reasonable
   - If position is missing → assume "staff-level" as default
   - If leave type is missing → provide general overview of all types
   - If department is missing → provide company-wide policy

4. Confidence level decision:
   - HIGH (0.8-1.0): Context is complete, no critical gaps, can answer accurately
   - MEDIUM (0.5-0.8): Some gaps exist but reasonable assumptions can fill them
   - LOW (0.3-0.5): Significant gaps, answer requires multiple assumptions
   - VERY_LOW (0.0-0.3): Critical information missing, cannot provide accurate answer

5. Clarification necessity:
   - Should ask clarification if confidence is VERY_LOW or LOW
   - Can answer with assumptions if confidence is MEDIUM or HIGH

**STEP 2 - ASSESSMENT:**
Based on your analysis, determine:

{{
  "confidence_level": "high|medium|low|very_low",
  "suggested_assumptions": {{
    "country": "Lebanon (headquarters)",
    "position": "staff-level",
    "other_field": "default_value"
  }},
  "reasoning": "brief explanation of your step-by-step thinking",
  "should_ask_clarification": true/false
}}

Examples:
- Query: "What's the leave policy?", Missing: ["country"]
  → {{"confidence_level": "medium", "suggested_assumptions": {{"country": "Lebanon"}}, "should_ask_clarification": false}}

- Query: "What's my specific salary?", Missing: ["role", "country", "years"]
  → {{"confidence_level": "very_low", "suggested_assumptions": {{}}, "should_ask_clarification": true}}

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at assessing information completeness. Use step-by-step reasoning to evaluate context quality and determine confidence levels. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
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
