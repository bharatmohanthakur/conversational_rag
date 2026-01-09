"""
LLM Classifier - Zero Hardcoding Approach
Uses LLM for ALL classification tasks with Chain of Thought reasoning.
No regex patterns, no hardcoded lists - pure LLM intelligence.
"""

import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from openai import AzureOpenAI
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger("LLMClassifier")


class ConfidenceLevel(Enum):
    """Confidence levels for answers."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QueryClassificationResult:
    """Comprehensive result from LLM query classification."""
    # Primary classification
    query_type: str  # greeting, question, command, clarification_answer, casual
    complexity: str  # simple, moderate, complex
    confidence: float  # 0-1
    
    # Boolean flags
    is_greeting: bool = False
    is_question: bool = False
    is_clarification_answer: bool = False
    is_casual: bool = False
    is_frustrated: bool = False
    
    # Clarification context
    requires_clarification: bool = False
    missing_context: List[str] = field(default_factory=list)
    suggested_assumptions: Dict[str, str] = field(default_factory=dict)
    
    # CoT reasoning
    reasoning: str = ""


@dataclass
class UserProfileInfo:
    """Extracted user profile information."""
    role: Optional[str] = None
    country: Optional[str] = None
    department: Optional[str] = None
    brand: Optional[str] = None
    employment_type: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class TopicChangeResult:
    """Result from topic change detection."""
    is_major_change: bool = False
    is_minor_shift: bool = False
    similarity: float = 1.0
    new_topic: Optional[str] = None
    old_topic: Optional[str] = None
    should_acknowledge: bool = False
    acknowledgment: Optional[str] = None
    reasoning: str = ""


@dataclass
class AnswerConfidenceResult:
    """Result from answer confidence assessment."""
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    confidence_score: float = 0.5
    source_quality: str = "unknown"
    has_sufficient_context: bool = True
    missing_info: List[str] = field(default_factory=list)
    suggested_assumptions: Dict[str, str] = field(default_factory=dict)
    should_show_warning: bool = False
    warning_message: Optional[str] = None
    reasoning: str = ""


class LLMClassifier:
    """
    LLM-based classifier for all classification tasks.
    Zero hardcoding - uses LLM for all decisions.
    """
    
    def __init__(
        self,
        aoai_client: AzureOpenAI,
        deployment_name: str,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600
    ):
        """
        Initialize LLM classifier.
        
        Args:
            aoai_client: Azure OpenAI client
            deployment_name: Model deployment name
            cache_enabled: Enable caching for repeated queries
            cache_ttl_seconds: Cache time-to-live
        """
        self.client = aoai_client
        self.deployment = deployment_name
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        
        logger.info("Initialized LLM Classifier with zero hardcoding approach")
    
    def _get_cache_key(self, *args) -> str:
        """Generate cache key from arguments."""
        key_str = json.dumps(args, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached result if valid."""
        if not self.cache_enabled:
            return None
        
        if key in self._cache:
            result, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return result
            else:
                del self._cache[key]
        return None
    
    def _set_cached(self, key: str, value: Any):
        """Cache a result."""
        if self.cache_enabled:
            self._cache[key] = (value, datetime.now())
    
    def classify_query(
        self,
        query: str,
        conversation_context: Optional[List[Dict]] = None,
        active_clarification: bool = False,
        clarification_question: Optional[str] = None,
        original_query: Optional[str] = None
    ) -> QueryClassificationResult:
        """
        Comprehensive query classification using LLM.
        
        Args:
            query: User's current query
            conversation_context: Recent conversation history
            active_clarification: Is there an active clarification session?
            clarification_question: The clarification question asked (if any)
            original_query: The original query (if in clarification flow)
            
        Returns:
            QueryClassificationResult with all classification details
        """
        cache_key = self._get_cache_key("classify", query, active_clarification, clarification_question)
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        context_str = ""
        if conversation_context:
            context_str = "\n".join([
                f"[{m.get('role', 'unknown').upper()}]: {m.get('content', '')[:150]}"
                for m in conversation_context[-5:]
            ])
        
        clarification_context = ""
        if active_clarification:
            clarification_context = f"""
ACTIVE CLARIFICATION SESSION:
- Original Question: {original_query or 'Unknown'}
- Clarification Asked: {clarification_question or 'Unknown'}
- User's Current Response: {query}
"""
        
        prompt = f"""You are an intelligent query classifier. Analyze the user's input and classify it comprehensively.

<input>
USER QUERY: "{query}"

CONVERSATION CONTEXT:
{context_str or "(No prior context)"}
{clarification_context}
</input>

<task>
Think step by step (Chain of Thought):

1. IDENTIFY QUERY TYPE:
   - greeting: User is greeting (hi, hello, hey, good morning, etc.)
   - casual: Non-HR casual message (thanks, ok, bye, etc.)
   - question: User is asking for information
   - command: User is requesting an action
   - clarification_answer: User is answering a clarification question

2. ASSESS COMPLEXITY:
   - simple: Can be answered directly
   - moderate: May need some context
   - complex: Multi-part, needs research

3. CHECK FOR CLARIFICATION:
   - If active_clarification is True and the response seems to answer the question: is_clarification_answer=True
   - Short responses (1-3 words) during clarification are usually answers
   - Unless the response is clearly a new question or topic change

4. DETECT FRUSTRATION:
   - Words like "just", "any", "whatever", "doesn't matter" indicate frustration
   - Impatient or dismissive tone

5. IDENTIFY MISSING CONTEXT:
   - What information would help answer this query?
   - Country, role, employment type, specific policy area?
</task>

<output>
Respond with JSON:
{{
    "query_type": "greeting|question|command|clarification_answer|casual",
    "complexity": "simple|moderate|complex",
    "confidence": 0.0-1.0,
    "is_greeting": true/false,
    "is_question": true/false,
    "is_clarification_answer": true/false,
    "is_casual": true/false,
    "is_frustrated": true/false,
    "requires_clarification": true/false,
    "missing_context": ["list", "of", "missing", "info"],
    "suggested_assumptions": {{"key": "value"}},
    "reasoning": "Step by step reasoning..."
}}
</output>"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are an expert query classifier. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(result_text)
            
            result = QueryClassificationResult(
                query_type=data.get("query_type", "question"),
                complexity=data.get("complexity", "simple"),
                confidence=data.get("confidence", 0.8),
                is_greeting=data.get("is_greeting", False),
                is_question=data.get("is_question", False),
                is_clarification_answer=data.get("is_clarification_answer", False),
                is_casual=data.get("is_casual", False),
                is_frustrated=data.get("is_frustrated", False),
                requires_clarification=data.get("requires_clarification", False),
                missing_context=data.get("missing_context", []),
                suggested_assumptions=data.get("suggested_assumptions", {}),
                reasoning=data.get("reasoning", "")
            )
            
            logger.info(f"🧠 LLM Classification: type={result.query_type}, "
                       f"greeting={result.is_greeting}, clarification_answer={result.is_clarification_answer}, "
                       f"complexity={result.complexity}")
            
            self._set_cached(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in LLM classification: {e}")
            # Safe fallback
            return QueryClassificationResult(
                query_type="question",
                complexity="simple",
                confidence=0.5,
                is_question=True,
                reasoning=f"Error occurred: {e}"
            )
    
    def detect_user_profile_info(
        self,
        text: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> UserProfileInfo:
        """
        Extract user profile information using LLM.
        No hardcoded patterns - LLM understands natural language.
        
        Args:
            text: Text to extract profile info from
            conversation_history: Recent conversation for context
            
        Returns:
            UserProfileInfo with extracted details
        """
        cache_key = self._get_cache_key("profile", text)
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        history_context = ""
        if conversation_history:
            history_context = "\n".join([
                f"[{m.get('role', 'unknown').upper()}]: {m.get('content', '')[:100]}"
                for m in conversation_history[-5:]
            ])
        
        prompt = f"""Extract user profile information from this text. Be intelligent about understanding context.

<input>
TEXT: "{text}"

CONVERSATION CONTEXT:
{history_context or "(No prior context)"}
</input>

<task>
Extract ANY of the following if mentioned or implied:
- role: Job title/position (Manager, Director, Staff, etc.)
- country: Country or location (Lebanon, UAE, Saudi Arabia, etc.)
- department: Department (HR, IT, Finance, Operations, etc.)
- brand: Company brand (Zara, H&M, etc.)
- employment_type: Full-time, Part-time, Contract, etc.

RULES:
- Infer from city names: "Dubai" → country: "UAE", "Beirut" → country: "Lebanon"
- Understand variations: "I'm a manager" → role: "Manager"
- Be flexible with phrasing
- Only extract if reasonably certain
</task>

<output>
Respond with JSON:
{{
    "role": "extracted role or null",
    "country": "extracted country or null",
    "department": "extracted department or null",
    "brand": "extracted brand or null",
    "employment_type": "extracted type or null",
    "confidence": 0.0-1.0,
    "reasoning": "explanation..."
}}
</output>"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting user profile information. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=400
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(result_text)
            
            result = UserProfileInfo(
                role=data.get("role") if data.get("role") and data.get("role") != "null" else None,
                country=data.get("country") if data.get("country") and data.get("country") != "null" else None,
                department=data.get("department") if data.get("department") and data.get("department") != "null" else None,
                brand=data.get("brand") if data.get("brand") and data.get("brand") != "null" else None,
                employment_type=data.get("employment_type") if data.get("employment_type") and data.get("employment_type") != "null" else None,
                confidence=data.get("confidence", 0.8),
                reasoning=data.get("reasoning", "")
            )
            
            extracted = [f for f in ["role", "country", "department", "brand"] 
                        if getattr(result, f)]
            if extracted:
                logger.info(f"👤 LLM Profile Extraction: {', '.join(extracted)}")
            
            self._set_cached(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in profile extraction: {e}")
            return UserProfileInfo(reasoning=f"Error: {e}")
    
    def detect_topic_change(
        self,
        current_query: str,
        recent_queries: List[str],
        current_topic: Optional[str] = None
    ) -> TopicChangeResult:
        """
        Detect topic changes using LLM semantic understanding.
        
        Args:
            current_query: Current user query
            recent_queries: Recent user queries for context
            current_topic: Currently tracked topic (if any)
            
        Returns:
            TopicChangeResult with change details
        """
        cache_key = self._get_cache_key("topic", current_query, str(recent_queries[:3]))
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        recent_str = "\n".join([f"- {q}" for q in recent_queries[-3:]]) if recent_queries else "(None)"
        
        prompt = f"""Analyze if the user changed topics in this conversation.

<input>
CURRENT QUERY: "{current_query}"

RECENT QUERIES:
{recent_str}

PREVIOUSLY TRACKED TOPIC: {current_topic or "(None)"}
</input>

<task>
Determine:
1. Is this a MAJOR topic change? (Completely different subject)
2. Is this a MINOR shift? (Related but slightly different)
3. Is this the same topic? (Continuing same discussion)
4. What's the new topic if changed?
5. Should we acknowledge the topic change?
</task>

<output>
Respond with JSON:
{{
    "is_major_change": true/false,
    "is_minor_shift": true/false,
    "similarity": 0.0-1.0,
    "new_topic": "detected topic or null",
    "old_topic": "previous topic or null",
    "should_acknowledge": true/false,
    "acknowledgment": "Acknowledgment message if needed",
    "reasoning": "explanation..."
}}
</output>"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding conversation flow. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=400
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(result_text)
            
            result = TopicChangeResult(
                is_major_change=data.get("is_major_change", False),
                is_minor_shift=data.get("is_minor_shift", False),
                similarity=data.get("similarity", 1.0),
                new_topic=data.get("new_topic"),
                old_topic=data.get("old_topic"),
                should_acknowledge=data.get("should_acknowledge", False),
                acknowledgment=data.get("acknowledgment"),
                reasoning=data.get("reasoning", "")
            )
            
            if result.is_major_change:
                logger.info(f"🔄 LLM Topic Change: {result.old_topic} → {result.new_topic}")
            
            self._set_cached(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in topic change detection: {e}")
            return TopicChangeResult(reasoning=f"Error: {e}")
    
    def detect_frustration(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Tuple[bool, float, str]:
        """
        Detect user frustration using LLM understanding.
        
        Args:
            query: User's current query
            conversation_history: Recent conversation for context
            
        Returns:
            Tuple of (is_frustrated, confidence, reasoning)
        """
        cache_key = self._get_cache_key("frustration", query)
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        history_context = ""
        if conversation_history:
            history_context = "\n".join([
                f"[{m.get('role', 'unknown').upper()}]: {m.get('content', '')[:100]}"
                for m in conversation_history[-5:]
            ])
        
        prompt = f"""Analyze if the user is showing frustration in their message.

<input>
USER MESSAGE: "{query}"

CONVERSATION CONTEXT:
{history_context or "(No prior context)"}
</input>

<task>
Look for signals of frustration:
- Impatient language ("just give me", "any", "whatever")
- Dismissive tone ("doesn't matter", "skip", "forget it")
- Repetition or emphasis ("I SAID", "again")
- Short, curt responses in context of long conversation
</task>

<output>
Respond with JSON:
{{
    "is_frustrated": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation..."
}}
</output>"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at understanding user emotions. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(result_text)
            
            is_frustrated = data.get("is_frustrated", False)
            confidence = data.get("confidence", 0.5)
            reasoning = data.get("reasoning", "")
            
            if is_frustrated:
                logger.info(f"😤 LLM Frustration Detected: {reasoning[:100]}")
            
            result = (is_frustrated, confidence, reasoning)
            self._set_cached(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error in frustration detection: {e}")
            return (False, 0.0, f"Error: {e}")
    
    def assess_answer_confidence(
        self,
        query: str,
        answer: str,
        sources: List[Dict],
        context: str
    ) -> AnswerConfidenceResult:
        """
        Assess confidence in the generated answer using LLM.
        
        Args:
            query: User's original query
            answer: Generated answer
            sources: Source documents used
            context: Retrieved context
            
        Returns:
            AnswerConfidenceResult with confidence assessment
        """
        source_names = [s.get("source", "Unknown") for s in sources[:5]] if sources else ["No sources"]
        
        prompt = f"""Assess the confidence level of this answer.

<input>
USER QUESTION: "{query}"

ANSWER PROVIDED:
{answer[:500]}

SOURCES USED:
{', '.join(source_names)}

CONTEXT USED:
{context[:500]}
</input>

<task>
Evaluate:
1. Does the answer directly address the question?
2. Is the answer well-supported by the sources?
3. Is there any missing critical information?
4. Should the user be warned about anything?
</task>

<output>
Respond with JSON:
{{
    "confidence_level": "high|medium|low",
    "confidence_score": 0.0-1.0,
    "source_quality": "excellent|good|fair|poor",
    "has_sufficient_context": true/false,
    "missing_info": ["list", "of", "missing"],
    "suggested_assumptions": {{"key": "value"}},
    "should_show_warning": true/false,
    "warning_message": "warning if needed or null",
    "reasoning": "explanation..."
}}
</output>"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "You are an expert at evaluating answer quality. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=400
            )
            
            result_text = response.choices[0].message.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(result_text)
            
            confidence_level_str = data.get("confidence_level", "medium")
            confidence_level = ConfidenceLevel.MEDIUM
            if confidence_level_str == "high":
                confidence_level = ConfidenceLevel.HIGH
            elif confidence_level_str == "low":
                confidence_level = ConfidenceLevel.LOW
            
            result = AnswerConfidenceResult(
                confidence_level=confidence_level,
                confidence_score=data.get("confidence_score", 0.5),
                source_quality=data.get("source_quality", "fair"),
                has_sufficient_context=data.get("has_sufficient_context", True),
                missing_info=data.get("missing_info", []),
                suggested_assumptions=data.get("suggested_assumptions", {}),
                should_show_warning=data.get("should_show_warning", False),
                warning_message=data.get("warning_message"),
                reasoning=data.get("reasoning", "")
            )
            
            logger.info(f"📊 LLM Confidence: {result.confidence_level.value} ({result.confidence_score:.0%})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in confidence assessment: {e}")
            return AnswerConfidenceResult(reasoning=f"Error: {e}")
    
    def format_answer_with_confidence(
        self,
        answer: str,
        confidence: AnswerConfidenceResult,
        sources: List[Dict]
    ) -> str:
        """
        Format answer with confidence display and source references.
        
        Args:
            answer: Generated answer
            confidence: Confidence assessment result
            sources: Source documents
            
        Returns:
            Formatted answer with confidence info
        """
        # Get unique source names (top 5 unique sources, sorted by score)
        source_names = []
        if sources:
            # Sort by score (highest first) to prioritize best sources
            sorted_sources = sorted(sources, key=lambda x: x.get("score", 0), reverse=True)
            seen = set()
            for s in sorted_sources[:10]:  # Check top 10 for diversity
                source_name = s.get("source", "Unknown").replace(".md", "").replace("HRD - ", "").strip()
                if source_name and source_name not in seen:
                    source_names.append(source_name)
                    seen.add(source_name)
                    if len(source_names) >= 5:  # Top 5 unique sources
                        break
        if not source_names:
            source_names = ["General Knowledge Base"]
        
        # Build confidence display
        if confidence.confidence_level == ConfidenceLevel.HIGH:
            confidence_emoji = "📊"
            confidence_text = f"HIGH ({confidence.confidence_score:.0%})"
        elif confidence.confidence_level == ConfidenceLevel.MEDIUM:
            confidence_emoji = "📊"
            confidence_text = f"MEDIUM ({confidence.confidence_score:.0%})"
        else:
            confidence_emoji = "⚠️"
            confidence_text = f"LOW ({confidence.confidence_score:.0%})"
        
        # Build footer
        footer_parts = [
            f"\n\n---",
            f"{confidence_emoji} **Confidence:** {confidence_text}",
            f"📚 **Sources:** {', '.join(source_names)}"
        ]
        
        if confidence.should_show_warning and confidence.warning_message:
            footer_parts.append(f"⚠️ **Note:** {confidence.warning_message}")
        
        if confidence.confidence_level == ConfidenceLevel.LOW:
            footer_parts.append("💡 **Tip:** Consider contacting HR for verification")
        
        footer = "\n".join(footer_parts)
        
        return answer + footer


# Global instance
_llm_classifier: Optional[LLMClassifier] = None


def init_llm_classifier(
    aoai_client: AzureOpenAI,
    deployment_name: str,
    cache_enabled: bool = True
):
    """Initialize global LLM classifier."""
    global _llm_classifier
    _llm_classifier = LLMClassifier(
        aoai_client=aoai_client,
        deployment_name=deployment_name,
        cache_enabled=cache_enabled
    )
    logger.info("Initialized global LLM classifier with zero hardcoding approach")


def get_llm_classifier() -> Optional[LLMClassifier]:
    """Get global LLM classifier instance."""
    return _llm_classifier
