"""
General Query Handler

Handles general conversational queries (greetings, expressions, small talk)
directly with LLM without going through RAG retrieval pipeline.

Uses LLM-based classification - NO hardcoded patterns.
"""

from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
import logging
from openai import AzureOpenAI
import json

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Type of user query"""
    GENERAL_CONVERSATIONAL = "general_conversational"  # Greetings, expressions, small talk
    KNOWLEDGE_BASED = "knowledge_based"  # Requires RAG retrieval


@dataclass
class QueryClassification:
    """Result of query classification"""
    query_type: QueryType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    suggested_response: Optional[str] = None  # Only for general queries


class GeneralQueryHandler:
    """
    Handles general conversational queries directly with LLM.

    Features:
    - LLM-based classification (not hardcoded patterns)
    - Context-aware responses
    - Fast direct responses without RAG overhead
    """

    def __init__(
        self,
        llm_client: AzureOpenAI,
        deployment_name: str,
        classification_model: Optional[str] = None
    ):
        """
        Initialize handler.

        Args:
            llm_client: Azure OpenAI client
            deployment_name: Deployment name for main responses
            classification_model: Optional separate model for classification (defaults to same)
        """
        self.llm_client = llm_client
        self.deployment_name = deployment_name
        self.classification_model = classification_model or deployment_name

        logger.info("GeneralQueryHandler initialized")

    def classify_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> QueryClassification:
        """
        Classify query using LLM.

        Determines if query is:
        - General conversational (greetings, expressions, small talk)
        - Knowledge-based (requires document retrieval)

        Args:
            query: User query
            conversation_history: Optional conversation context

        Returns:
            QueryClassification with type and confidence
        """
        try:
            # Build context from history
            history_context = ""
            if conversation_history and len(conversation_history) > 0:
                recent_history = conversation_history[-4:]  # Last 2 turns
                history_context = "\n".join([
                    f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                    for msg in recent_history
                ])

            # Classification prompt
            classification_prompt = f"""You are a query classifier for an HR/employee knowledge base system.

Your task: Determine if the user's query is GENERAL CONVERSATIONAL or KNOWLEDGE-BASED.

**GENERAL CONVERSATIONAL** queries include:
- Greetings: "hi", "hello", "good morning", "hey there"
- Expressions: "I love you", "you're amazing", "wow", "awesome"
- Small talk: "how are you", "what's up", "how's it going"
- Gratitude: "thanks", "thank you so much", "appreciate it"
- Acknowledgments: "ok", "sure", "got it", "understood"
- Farewells: "bye", "goodbye", "see you later"
- Casual questions about YOU: "who are you", "what can you do", "are you AI"
- Emotional expressions: "I'm happy", "I'm sad", "feeling great"

**KNOWLEDGE-BASED** queries include:
- HR policy questions: "maternity leave policy", "vacation days", "sick leave"
- Employee benefits: "health insurance", "dental coverage", "retirement"
- Procedures: "how do I apply for leave", "request time off"
- Company info: "office locations", "working hours", "company policies"
- Specific information requests requiring document lookup

**Context:**
{history_context if history_context else "No previous conversation"}

**User Query:** "{query}"

Analyze the query and respond in JSON format:
{{
    "query_type": "general_conversational" or "knowledge_based",
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation of why>",
    "is_follow_up": <true if this is a follow-up to previous knowledge query>
}}

**Guidelines:**
- If query is a direct answer to a previous question (e.g., "Lebanon" after being asked for country), classify as knowledge_based
- If query has context from previous knowledge discussion, classify as knowledge_based
- Single words or very short phrases may be general OR knowledge-based depending on context
- When in doubt about conversational intent, prefer general_conversational
- Confidence > 0.8 means very sure, < 0.6 means uncertain

Respond ONLY with valid JSON, no other text.
"""

            response = self.llm_client.chat.completions.create(
                model=self.classification_model,
                messages=[
                    {"role": "system", "content": "You are a precise query classifier. Always respond with valid JSON."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=200
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                # Fallback: try to extract JSON from markdown code block
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                    result = json.loads(result_text)
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                    result = json.loads(result_text)
                else:
                    raise

            query_type = QueryType.GENERAL_CONVERSATIONAL if result["query_type"] == "general_conversational" else QueryType.KNOWLEDGE_BASED
            confidence = float(result["confidence"])
            reasoning = result["reasoning"]
            is_follow_up = result.get("is_follow_up", False)

            # If it's a follow-up to knowledge query, override to knowledge_based
            if is_follow_up and query_type == QueryType.GENERAL_CONVERSATIONAL:
                query_type = QueryType.KNOWLEDGE_BASED
                reasoning += " (Follow-up to previous knowledge query)"

            logger.info(f"Query classified as {query_type.value} (confidence: {confidence:.2f}): {reasoning}")

            return QueryClassification(
                query_type=query_type,
                confidence=confidence,
                reasoning=reasoning
            )

        except Exception as e:
            logger.error(f"Error classifying query: {e}")
            # Fallback: assume knowledge-based to be safe
            return QueryClassification(
                query_type=QueryType.KNOWLEDGE_BASED,
                confidence=0.5,
                reasoning=f"Classification failed, defaulting to knowledge-based: {str(e)}"
            )

    def generate_conversational_response(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generate a natural conversational response using LLM.

        Args:
            query: User query (already classified as general)
            conversation_history: Optional conversation context

        Returns:
            Natural conversational response
        """
        try:
            # Build conversation context
            messages = [
                {
                    "role": "system",
                    "content": """You are a friendly, helpful HR assistant for an employee knowledge base.

You are responding to a general conversational query (greeting, expression, small talk), NOT a knowledge question.

Guidelines:
- Be warm, friendly, and professional
- Keep responses brief and natural (1-3 sentences)
- For greetings: Respond warmly and offer to help
- For expressions: Acknowledge appropriately and stay professional
- For "how are you": Respond briefly and redirect to helping them
- For "who are you": Explain you're an HR assistant helping with policies/benefits
- For thanks: Acknowledge graciously and offer further help
- Always end by inviting them to ask about HR policies, benefits, or procedures

Examples:
- "hi" → "Hello! I'm here to help you with HR policies, benefits, and procedures. What can I assist you with today?"
- "I love you" → "That's very kind of you! I'm here to help with your HR and policy questions. What would you like to know?"
- "how are you" → "I'm doing great, thank you for asking! I'm here to help with your HR questions. What can I help you with?"
- "thanks" → "You're very welcome! Let me know if you need anything else about policies or benefits."

Stay in character as an HR assistant, not a general chatbot.
"""
                }
            ]

            # Add conversation history if available
            if conversation_history:
                recent_history = conversation_history[-6:]  # Last 3 turns
                for msg in recent_history:
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", "")
                    })

            # Add current query
            messages.append({
                "role": "user",
                "content": query
            })

            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                temperature=0.7,  # Slightly higher for natural conversation
                max_tokens=150
            )

            response_text = response.choices[0].message.content.strip()

            logger.info(f"Generated conversational response for: '{query[:50]}...'")

            return response_text

        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            # Fallback response
            return "Hello! I'm here to help you with HR policies, benefits, and procedures. What can I assist you with today?"

    def handle_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        confidence_threshold: float = 0.7
    ) -> Optional[str]:
        """
        Main entry point: Classify and handle query if general.

        Args:
            query: User query
            conversation_history: Optional conversation context
            confidence_threshold: Minimum confidence to handle as general (default 0.7)

        Returns:
            Response string if handled as general query, None if should go to RAG
        """
        # Classify query
        classification = self.classify_query(query, conversation_history)

        # If general conversational with high confidence, handle directly
        if (classification.query_type == QueryType.GENERAL_CONVERSATIONAL and
            classification.confidence >= confidence_threshold):

            logger.info(f"Handling as general conversational query (confidence: {classification.confidence:.2f})")

            response = self.generate_conversational_response(query, conversation_history)

            return response

        # If knowledge-based or low confidence, return None to trigger RAG pipeline
        logger.info(f"Passing to RAG pipeline: {classification.query_type.value} (confidence: {classification.confidence:.2f})")
        return None

    def is_general_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        confidence_threshold: float = 0.7
    ) -> bool:
        """
        Check if query is general conversational (without generating response).

        Useful for routing decisions.

        Args:
            query: User query
            conversation_history: Optional conversation context
            confidence_threshold: Minimum confidence threshold

        Returns:
            True if general conversational, False if knowledge-based
        """
        classification = self.classify_query(query, conversation_history)

        return (classification.query_type == QueryType.GENERAL_CONVERSATIONAL and
                classification.confidence >= confidence_threshold)


# Example usage and testing
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Initialize client
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-08-01-preview",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    handler = GeneralQueryHandler(
        llm_client=client,
        deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    )

    # Test cases
    test_queries = [
        "hi",
        "hello there!",
        "I love you",
        "how are you?",
        "thanks so much",
        "what is maternity leave policy?",
        "Lebanon",  # Could be answer to previous question
        "how do I apply for vacation?",
        "you're amazing!",
        "who are you?",
        "what can you help me with?",
    ]

    print("\n=== Testing General Query Handler ===\n")

    for query in test_queries:
        print(f"\n📝 Query: \"{query}\"")

        # Classify
        classification = handler.classify_query(query)
        print(f"   Type: {classification.query_type.value}")
        print(f"   Confidence: {classification.confidence:.2f}")
        print(f"   Reasoning: {classification.reasoning}")

        # Generate response if general
        if classification.query_type == QueryType.GENERAL_CONVERSATIONAL:
            response = handler.generate_conversational_response(query)
            print(f"   Response: {response}")

        print("-" * 80)
