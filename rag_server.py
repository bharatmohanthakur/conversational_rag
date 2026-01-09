#!/usr/bin/env python3
"""
RAG API Service with Graphiti Memory Integration
matches signature of api_server.py: 
POST /query {query: str} -> {response: str, metadata: dict}

Features:
- Hybrid retrieval: Qdrant (document chunks) + Graphiti (knowledge graph memory)
- Persistent memory: Saves conversations as episodes to Graphiti
- Temporal awareness: Facts include validity timestamps
- Comprehensive logging with request tracking
"""

import os
import sys
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from openai import AzureOpenAI, AsyncAzureOpenAI, AsyncOpenAI

# Use existing search logic
import azure_doc_intelligence_qdrant as rag_impl

# GFM Markdown formatting
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

# Enhanced modules
from conversation_manager import get_conversation_manager
from resilience import retry_with_backoff, with_timeout, get_qdrant_circuit, get_graphiti_circuit, get_llm_circuit
from answer_quality import AnswerQuality, ConfidenceLevel
from clarification_tracker import ClarificationTracker, ClarificationStatus
from conversation_summarizer import ConversationSummarizer
from self_evaluator import SelfEvaluator, TerminationDecision, TerminationReason
from adaptive_retrieval import AdaptiveRetriever
from answer_quality_gate import AnswerQualityGate
from conversation_summarizer import ConversationSummarizer
from contextual_compressor import ContextualCompressor
from reranker import Reranker
from corrective_rag import CorrectiveRAG
from general_query_handler import GeneralQueryHandler, QueryType
from conversational_excellence import ConversationalExcellence

# Optimization modules
from config import get_config, get_query_processing_config
from query_cache import init_query_cache, get_query_cache
from pattern_matcher import get_pattern_matcher
from best_guess_answering import BestGuessAnswering
from user_profile_tracker import UserProfileTracker
from topic_change_detector import TopicChangeDetector
from conversation_state_machine import ConversationStateMachine, ConversationState
from clarification_handler import ClarificationHandler
from llm_context_classifier import init_llm_context_classifier, get_llm_context_classifier
from llm_classifier import init_llm_classifier, get_llm_classifier, LLMClassifier, AnswerConfidenceResult, ConfidenceLevel
from optimized_query_processor import init_query_processor, get_query_processor

# Graphiti imports
from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client import LLMConfig
from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

# ---------------------------------------------------------------------
# Logging Setup - File + Console with Rotation
# ---------------------------------------------------------------------
from logging.handlers import RotatingFileHandler

# Create logs directory
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "rag_server.log")

# Setup logger
logger = logging.getLogger("RAG-Server")
logger.setLevel(logging.INFO)

# Formatter
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

# File handler with rotation (10MB per file, keep 5 backups)
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_formatter)

# Add handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

logger.info(f"📁 Logging to file: {LOG_FILE}")

def log_request(request_id: str, step: str, data: Any, level: str = "info"):
    """Structured logging with request ID tracking."""
    msg = f"[{request_id}] {step}"
    if data:
        if isinstance(data, dict):
            msg += f" | {json.dumps(data, ensure_ascii=False, default=str)[:500]}"
        else:
            msg += f" | {str(data)[:500]}"
    
    if level == "error":
        logger.error(msg)
    elif level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)

# Initialize markdown-it with GFM-like features
md = MarkdownIt("gfm-like").use(tasklists_plugin)

def format_gfm_to_html(text: str) -> str:
    """Convert markdown text to HTML using GFM-like formatting."""
    if not text or not text.strip():
        return text
    return md.render(text)

load_dotenv()

app = FastAPI(title="RAG API Service with Graphiti Memory")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small")

# Neo4j for Graphiti
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")  # Custom database name

# Feature flags
GRAPHITI_ENABLED = os.getenv("GRAPHITI_ENABLED", "true").lower() == "true"
GRAPHITI_GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "azadea")  # Multi-tenant group ID

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# Use the multimodal collection with figure descriptions from GPT-4 Vision
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "docs_hybrid_azure_azadea_multimodal")

# Initialize Clients
aoai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version="2024-02-01",
)

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

# Initialize enhanced components (will be used later)
_conv_manager = None
_clarification_tracker = None
_conversation_summarizer = None
_self_evaluator = None
_adaptive_retriever = None
_quality_gate = None
_contextual_compressor = None
_reranker = None
_corrective_rag = None
_general_query_handler = None
_conversational_excellence = None

# Optimization modules
_best_guess_answering = None
_user_profile_tracker = None
_topic_change_detector = None
_conversation_state_machine = None
_unified_clarification_handler = None
_llm_context_classifier = None
_llm_classifier = None

def get_enhanced_components():
    """Get or initialize enhanced components."""
    global _conv_manager, _clarification_tracker, _conversation_summarizer
    global _self_evaluator, _adaptive_retriever, _quality_gate
    global _contextual_compressor, _reranker, _corrective_rag, _general_query_handler, _conversational_excellence
    global _best_guess_answering, _user_profile_tracker, _topic_change_detector
    global _conversation_state_machine, _unified_clarification_handler, _llm_context_classifier, _llm_classifier
    if _conv_manager is None:
        _conv_manager = get_conversation_manager()
        _clarification_tracker = ClarificationTracker(_conv_manager)
        _conversation_summarizer = ConversationSummarizer(aoai_client, deployment_name=AZURE_CHAT_DEPLOYMENT)
        _self_evaluator = SelfEvaluator(aoai_client)
        _quality_gate = AnswerQualityGate(_self_evaluator)
        # Initialize RAG technique modules
        _contextual_compressor = ContextualCompressor(aoai_client, deployment_name=AZURE_CHAT_DEPLOYMENT)
        _reranker = Reranker(aoai_client, deployment_name=AZURE_CHAT_DEPLOYMENT)
        _corrective_rag = CorrectiveRAG(aoai_client, deployment_name=AZURE_CHAT_DEPLOYMENT)
        # Initialize general query handler for conversational queries
        _general_query_handler = GeneralQueryHandler(
            llm_client=aoai_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT
        )
        # Initialize conversational excellence for natural responses
        _conversational_excellence = ConversationalExcellence(
            llm_client=aoai_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT,
            personality="warm_professional"
        )
        # Initialize adaptive retriever with run_search_for_deep_agent as retrieval function
        async def retrieval_func(query: str, user_id: str):
            return await run_search_for_deep_agent(query, user_id, use_adaptive=False)
        _adaptive_retriever = AdaptiveRetriever(retrieval_function=retrieval_func)

        # Initialize optimization modules
        # 1. Initialize global singletons (query_cache, query_processor)
        # Note: pattern_matcher auto-initializes through get_pattern_matcher()

        # Simple embedding function for cache (using Azure OpenAI)
        def embed_query(text: str):
            response = aoai_client.embeddings.create(
                model=AZURE_EMBEDDING_DEPLOYMENT,
                input=text
            )
            return response.data[0].embedding

        init_query_cache(
            embedding_function=embed_query,
            ttl_seconds=3600,
            max_size=1000,
            similarity_threshold=0.95
        )

        init_query_processor(
            llm_client=aoai_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT
        )

        # 2. Initialize optimization components
        _best_guess_answering = BestGuessAnswering(
            llm_client=aoai_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT
        )

        _user_profile_tracker = UserProfileTracker(
            conversation_manager=_conv_manager
        )

        _topic_change_detector = TopicChangeDetector(
            embedding_function=embed_query
        )

        _conversation_state_machine = ConversationStateMachine()

        _unified_clarification_handler = ClarificationHandler(
            llm_client=aoai_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT,
            clarification_tracker=_clarification_tracker
        )

        # Initialize LLM Context Classifier with CoT reasoning
        init_llm_context_classifier(aoai_client, AZURE_CHAT_DEPLOYMENT)
        _llm_context_classifier = get_llm_context_classifier()

        # Initialize comprehensive LLM Classifier (zero hardcoding)
        init_llm_classifier(aoai_client, AZURE_CHAT_DEPLOYMENT, cache_enabled=True)
        _llm_classifier = get_llm_classifier()

    return (_conv_manager, _clarification_tracker, _conversation_summarizer, _self_evaluator,
            _quality_gate, _adaptive_retriever, _contextual_compressor,
            _reranker, _corrective_rag, _general_query_handler, _conversational_excellence,
            _best_guess_answering, _user_profile_tracker, _topic_change_detector,
            _conversation_state_machine, _unified_clarification_handler, _llm_context_classifier, _llm_classifier)

# ---------------------------------------------------------------------
# Graphiti Memory System
# ---------------------------------------------------------------------
graphiti_instance: Optional[Graphiti] = None
graphiti_lock = asyncio.Lock()

async def get_graphiti() -> Optional[Graphiti]:
    """Get or initialize the Graphiti instance."""
    global graphiti_instance
    
    if not GRAPHITI_ENABLED:
        return None
        
    async with graphiti_lock:
        if graphiti_instance is not None:
            return graphiti_instance
            
        try:
            print("🔄 Initializing Graphiti memory system...")
            
            # Azure OpenAI clients for Graphiti
            llm_client_v1 = AsyncOpenAI(
                api_key=AZURE_OPENAI_API_KEY,
                base_url=f"{AZURE_OPENAI_ENDPOINT}openai/v1/",
            )
            
            llm_client_azure = AsyncAzureOpenAI(
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
            )
            
            embedding_client_azure = AsyncAzureOpenAI(
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
            )
            
            azure_llm_config = LLMConfig(
                model=AZURE_CHAT_DEPLOYMENT,
                small_model=AZURE_CHAT_DEPLOYMENT,
            )
            
            # Create Neo4j driver with custom database name
            neo4j_driver = Neo4jDriver(
                uri=NEO4J_URI,
                user=NEO4J_USER,
                password=NEO4J_PASSWORD,
                database=NEO4J_DATABASE,
            )
            logger.info(f"🔗 Connecting to Neo4j: {NEO4J_URI} (database: {NEO4J_DATABASE})")
            
            # Use custom driver with AzureOpenAILLMClient
            graphiti_instance = Graphiti(
                graph_driver=neo4j_driver,
                llm_client=AzureOpenAILLMClient(
                    azure_client=llm_client_azure,
                    config=azure_llm_config,
                    reasoning=None,  # Azure OpenAI doesn't support reasoning.effort
                    verbosity=None,
                ),
                embedder=OpenAIEmbedder(
                    config=OpenAIEmbedderConfig(
                        embedding_model=AZURE_EMBEDDING_DEPLOYMENT
                    ),
                    client=embedding_client_azure,
                ),
                cross_encoder=OpenAIRerankerClient(
                    config=LLMConfig(model=azure_llm_config.small_model),
                    client=llm_client_azure,
                ),
            )
            
            # Build indices (idempotent)
            await graphiti_instance.build_indices_and_constraints()
            logger.info(f"✅ Graphiti memory system initialized (database: {NEO4J_DATABASE})")
            return graphiti_instance
            
        except Exception as e:
            print(f"⚠️ Failed to initialize Graphiti: {e}")
            print("   Continuing without Graphiti memory...")
            return None


@retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(Exception,))
@with_timeout(timeout_seconds=10.0)
async def search_graphiti_memory(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Search the Graphiti knowledge graph for relevant facts using group_id for isolation."""
    graphiti = await get_graphiti()
    if not graphiti:
        return []
    
    circuit = get_graphiti_circuit()
    try:
        results = await circuit.acall(
            graphiti.search,
            query, 
            num_results=num_results,
            group_ids=[GRAPHITI_GROUP_ID],  # Filter by group_id for data isolation
        )
        facts = []
        for r in results:
            facts.append({
                "uuid": getattr(r, "uuid", None),
                "fact": getattr(r, "fact", ""),
                "valid_at": str(getattr(r, "valid_at", None)),
                "invalid_at": str(getattr(r, "invalid_at", None)),
                "source_node_uuid": getattr(r, "source_node_uuid", None),
                "group_id": GRAPHITI_GROUP_ID,
            })
        logger.info(f"🧠 Graphiti search with group_id={GRAPHITI_GROUP_ID} returned {len(facts)} facts")
        return facts
    except Exception as e:
        logger.error(f"⚠️ Graphiti search error: {e}")
        return []


async def save_to_graphiti_memory(user_id: str, query: str, answer: str) -> bool:
    """Save a Q&A interaction as an episode to Graphiti for long-term memory with group_id."""
    graphiti = await get_graphiti()
    if not graphiti:
        return False
    
    try:
        episode_content = f"""User ({user_id}) asked: {query}

Assistant answered: {answer}"""
        
        await graphiti.add_episode(
            name=f"conversation_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            episode_body=episode_content,
            source=EpisodeType.text,
            source_description=f"RAG conversation with user {user_id}",
            reference_time=datetime.now(timezone.utc),
            group_id=GRAPHITI_GROUP_ID,  # Assign to group_id for isolation
        )
        logger.info(f"💾 Saved conversation to Graphiti (group_id={GRAPHITI_GROUP_ID}) for user: {user_id}")
        return True
    except Exception as e:
        logger.error(f"⚠️ Failed to save to Graphiti: {e}")
        return False


# ---------------------------------------------------------------------
# Models (Matching api_server.py)
# ---------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str
    user_id: str = "default_user"

class QueryResponse(BaseModel):
    response: str
    metadata: Dict[str, Any] = {}

# ---------------------------------------------------------------------
# Conversation Management (Persistent Storage)
# ---------------------------------------------------------------------
# Get enhanced components
(conv_manager, clarification_tracker, conversation_summarizer, self_evaluator,
        quality_gate, adaptive_retriever, contextual_compressor,
        reranker, corrective_rag, general_query_handler, conversational_excellence,
        best_guess_answering, user_profile_tracker, topic_change_detector,
        conversation_state_machine, unified_clarification_handler, llm_context_classifier, llm_classifier) = get_enhanced_components()

def get_user_history(user_id: str, use_summarization: bool = True) -> List[Dict[str, str]]:
    """
    Get user conversation history from persistent storage.
    Optionally uses summarization for long histories.
    """
    if use_summarization:
        history_data = conv_manager.get_conversation_with_summary(user_id, max_turns=10)
        if history_data.get("old_messages") and len(history_data["old_messages"]) > 5:
            # Use compressed history with summary
            full_history = conv_manager.get_history(user_id)
            compressed = conversation_summarizer.get_compressed_history(
                full_history,
                include_summary=True
            )
            return [{"role": msg.get("role"), "content": msg.get("content")} for msg in compressed]
    
    history = conv_manager.get_history(user_id, limit=20)  # Limit to last 20 messages
    # Convert to old format for compatibility
    return [{"role": msg.get("role"), "content": msg.get("content")} for msg in history]

class ResetRequest(BaseModel):
    user_id: str = ""

# ---------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------
SYSTEM_PROMPT = """You are a helpful assistant for Azadea HR policies and procedures.

You have access to multiple knowledge sources:
1. **Document Text**: Retrieved from HR policy documents
2. **Visual Content Descriptions**: AI-generated descriptions of charts, diagrams, workflows, and figures from documents (marked as "Visual Content" sections)
3. **Memory Facts**: Previous conversations and learned facts

When answering:
- Use information from both text and visual content descriptions
- If the answer is not in the context, politely say you don't know based on the available documents
- Keep the answer professional and concise
"""

def rewrite_query_with_history(history: List[Dict[str, str]], latest_query: str, user_id: str = None) -> str:
    """
    Rewrites the latest query based on conversation history to make it standalone.
    Enhanced to handle clarification context and preserve original question intent.
    """
    # Check for active clarification session first
    if user_id:
        active_session = clarification_tracker.get_active_session(user_id)
        if active_session:
            # User is answering clarifying questions
            if clarification_tracker.is_clarification_response(user_id, latest_query):
                # Don't add answer here - let clarification_answer_handler_node do it
                # Don't complete session here - let clarification handler manage it based on turn count
                # Just return the query as-is, it will be handled by clarification_answer_handler_node
                logger.info(f"Query rewrite: Detected clarification response, keeping query as-is for clarification handler")
                return latest_query  # Keep as-is, will be handled by clarification handler

    if not history:
        return latest_query

    # Extract original question from conversation history
    original_question = None
    if user_id:
        conv_mgr = get_conversation_manager()
        original_question = conv_mgr.get_original_question(user_id, within_last_n=15)

    # Filter out greetings and casual messages from history
    # Only include messages that are actual HR questions/answers
    filtered_history = []
    greeting_patterns = ["hi", "hello", "hey", "thanks", "thank you", "okay", "ok", "sure", "great", "awesome", "perfect"]

    for msg in history[-10:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip().lower()

        # Skip greetings and casual messages
        if role == "user":
            # Check if it's a greeting/casual message
            is_greeting = any(pattern in content for pattern in greeting_patterns) and len(content.split()) <= 5
            if is_greeting:
                continue  # Skip greetings

        # Include assistant responses and actual user questions
        filtered_history.append(msg)

    if not filtered_history:
        return latest_query

    # Format filtered history
    history_str = ""
    for msg in filtered_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        history_str += f"{role}: {content}\n"

    # Build prompt with original question context if available
    original_context = f"\n**IMPORTANT - Original Question**: {original_question}\n" if original_question else ""

    prompt = f"""You are an AI assistant. Your task is to rewrite the latest user question into a standalone question.
{original_context}
Rules:
1. **Preserve Original Intent**: If there is an original question provided above, ALWAYS maintain its core intent. The latest query is likely a follow-up or clarification answer related to this original question.
2. **Ignore Greetings**: Do NOT include greetings (hi, hello, thanks) in the rewritten query. Only use actual HR questions.
3. **Handle Clarification Answers**: If the user is answering a clarifying question, combine their answer with the ORIGINAL QUESTION (not just the immediate clarification).
4. **Maintain Core Topic**: If the user asks a follow-up (e.g., "What about..."), apply it to the ORIGINAL QUESTION's topic.
5. **Resolve Pronouns**: Resolve 'it', 'they', 'that' to their referents from the ORIGINAL QUESTION.
6. **Context Over Recency**: Prioritize the original question's context over the immediate recent exchange.
7. **Do Not Hallucinate**: Only use info present in the history.

Conversation History (greetings filtered out):
{history_str}

Latest User Input: {latest_query}

Standalone Question (maintaining original intent):"""

    try:
        response = aoai_client.chat.completions.create(
            model=AZURE_CHAT_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200
        )
        rewritten = response.choices[0].message.content.strip()
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1]

        # If we have an original question and the rewritten query lost the context, add it back
        if original_question and len(rewritten.split()) < 5:
            logger.warning(f"Query rewrite seems too short, using original question as base")
            # Combine the short answer with the original question
            rewritten = f"{original_question} - {latest_query}"

        return rewritten
    except Exception as e:
        logger.error(f"Error rewriting query: {e}")
        return latest_query

@app.post("/reset")
async def reset_history(request: ResetRequest):
    """Reset conversation history using persistent storage."""
    if request.user_id:
        conv_manager.clear_history(request.user_id)
        return {"status": f"History cleared for user {request.user_id}"}
    else:
        conv_manager.clear_history()
        return {"status": "History cleared for ALL users"}

@app.get("/reset")
async def reset_history_get(user_id: Optional[str] = None):
    """Reset conversation history (GET endpoint for convenience)."""
    if user_id:
        conv_manager.clear_history(user_id)
        return {"status": f"History cleared for user {user_id}"}
    else:
        conv_manager.clear_history()
        return {"status": "History cleared for ALL users"}

@app.get("/health")
async def health_check():
    """Health check endpoint with Graphiti status."""
    graphiti = await get_graphiti()
    return {
        "status": "healthy",
        "qdrant": "connected",
        "graphiti": "connected" if graphiti else "disabled",
        "graphiti_enabled": GRAPHITI_ENABLED,
    }

@app.post("/query_backup", response_model=QueryResponse)
async def query_backup_endpoint(request: QueryRequest):
    # Generate unique request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    try:
        query_text = request.query.strip()
        if not query_text:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        user_id = request.user_id or "default_user"
        history = get_user_history(user_id)
        
        # Log incoming request
        log_request(request_id, "📥 REQUEST", {
            "user_id": user_id,
            "query": query_text,
            "history_length": len(history)
        })
        
        # 0. Rewrite Query
        search_query = rewrite_query_with_history(history, query_text)
        log_request(request_id, "🔄 QUERY_REWRITE", {
            "original": query_text,
            "rewritten": search_query
        })

        # 1. Retrieve from Qdrant (document chunks)
        qdrant_start = datetime.now()
        dense_q = rag_impl.embed_dense_azure([search_query])[0]
        sparse_q = rag_impl.build_sparse_query_vector(search_query)
        
        from qdrant_client import models as qm
        
        search_result = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                qm.Prefetch(query=dense_q,  using=rag_impl.DENSE_NAME,  limit=50),
                qm.Prefetch(query=sparse_q, using=rag_impl.SPARSE_NAME, limit=50),
            ],
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=5,
        )
        qdrant_elapsed = (datetime.now() - qdrant_start).total_seconds()
        
        sources = []
        full_context_list = []
        retrieved_images = []  # Collect images for multimodal inference
        
        for p in search_result.points:
            pl = p.payload or {}
            text_content = pl.get("text", "")
            src = pl.get("source_file", "unknown")
            page = pl.get("chunk_index", "?")
            
            full_context_list.append(f"Source: {src} (Chunk {page})\nContent: {text_content}")
            
            sources.append({
                "id": p.id,
                "score": p.score,
                "source": src,
                "text_snippet": text_content[:200],
                "has_images": pl.get("has_images", False)
            })
            
            # Extract images from payload for multimodal inference
            if pl.get("has_images") and pl.get("images"):
                for img in pl.get("images", [])[:2]:  # Limit to 2 images per chunk
                    if img.get("image_b64") and len(retrieved_images) < 3:  # Max 3 total
                        retrieved_images.append({
                            "b64": img["image_b64"],
                            "caption": img.get("caption", ""),
                            "source": src
                        })
        
        log_request(request_id, "📚 QDRANT_RESPONSE", {
            "chunks_found": len(sources),
            "images_found": len(retrieved_images),
            "elapsed_sec": round(qdrant_elapsed, 3),
            "sources": [s["source"] for s in sources]
        })
        
        # 2. Retrieve from Graphiti (knowledge graph memory)
        graphiti_start = datetime.now()
        graphiti_facts = await search_graphiti_memory(search_query, num_results=5)
        graphiti_elapsed = (datetime.now() - graphiti_start).total_seconds()
        
        log_request(request_id, "🧠 GRAPHITI_RESPONSE", {
            "facts_found": len(graphiti_facts),
            "elapsed_sec": round(graphiti_elapsed, 3),
            "facts": [f.get("fact", "")[:100] for f in graphiti_facts]
        })
        
        # Build combined context
        context_str = "\n\n".join(full_context_list)
        
        # Add Graphiti facts if available
        memory_context = ""
        if graphiti_facts:
            memory_facts_str = "\n".join(f"- {f['fact']}" for f in graphiti_facts if f.get('fact'))
            if memory_facts_str:
                memory_context = f"\n\n--- Memory Facts from Knowledge Graph ---\n{memory_facts_str}"
        
        combined_context = context_str + memory_context
        
        log_request(request_id, "🔗 COMBINED_CONTEXT", {
            "qdrant_chars": len(context_str),
            "graphiti_chars": len(memory_context),
            "total_chars": len(combined_context)
        })
        
        # 3. Generate Answer (with multimodal support)
        llm_start = datetime.now()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        # Inject History
        for msg in history[-5:]:
            messages.append(msg)
        
        # Build user message content (text + images for multimodal)
        if retrieved_images:
            # Multimodal message with text and images
            user_content = [
                {"type": "text", "text": f"Context:\n{combined_context}\n\nQuestion: {query_text}"}
            ]
            for img_data in retrieved_images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_data['b64']}"}
                })
            messages.append({"role": "user", "content": user_content})
            log_request(request_id, "🖼️ MULTIMODAL_INFERENCE", {
                "images_included": len(retrieved_images),
                "captions": [img.get("caption", "")[:30] for img in retrieved_images]
            })
        else:
            # Text-only message
            messages.append({"role": "user", "content": f"Context:\n{combined_context}\n\nQuestion: {query_text}"})
        
        completion = aoai_client.chat.completions.create(
            model=AZURE_CHAT_DEPLOYMENT,
            messages=messages,
            temperature=0.0,
            max_tokens=1500,
        )
        llm_elapsed = (datetime.now() - llm_start).total_seconds()
        
        answer_text = completion.choices[0].message.content
        
        log_request(request_id, "💬 LLM_RESPONSE", {
            "answer_chars": len(answer_text),
            "elapsed_sec": round(llm_elapsed, 3),
            "model": AZURE_CHAT_DEPLOYMENT,
            "multimodal": len(retrieved_images) > 0
        })
        
        # 4. Save to History (in-memory)
        history.append({"role": "user", "content": query_text})
        history.append({"role": "assistant", "content": answer_text})
        
        # 5. Save to Graphiti Memory (persistent, async - don't block response)
        asyncio.create_task(save_to_graphiti_memory(user_id, query_text, answer_text))
        
        # Format response using GFM to HTML
        formatted_response = format_gfm_to_html(answer_text)
        
        total_elapsed = (datetime.now() - start_time).total_seconds()
        log_request(request_id, "📤 RESPONSE", {
            "total_elapsed_sec": round(total_elapsed, 3),
            "response_chars": len(formatted_response),
            "qdrant_chunks": len(sources),
            "graphiti_facts": len(graphiti_facts)
        })
        
        return QueryResponse(
            response=formatted_response,
            metadata={
                "request_id": request_id,
                "sources": sources,
                "graphiti_facts_count": len(graphiti_facts),
                "memory_enabled": GRAPHITI_ENABLED,
                "elapsed_sec": round(total_elapsed, 3),
            }
        )

    except Exception as e:
        log_request(request_id, "❌ ERROR", {"error": str(e)}, level="error")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



# ---------------------------------------------------------------------
# LangGraph / Query Decomposition Integration
# ---------------------------------------------------------------------
from typing import Annotated, Literal, TypedDict, List, Optional, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

# --- Reusable RAG Search Function ---
@retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(Exception,))
@with_timeout(timeout_seconds=30.0)
async def run_search_for_deep_agent(query: str, user_id: str, use_advanced_rag: bool = True) -> Dict[str, Any]:
    """
    Executes enhanced RAG search with advanced techniques:
    - Reranking for better relevance
    - Contextual Compression to reduce tokens
    - Corrective RAG for quality evaluation
    
    Returns: {"context": str, "sources": List[Dict], "images": List}
"""
    sources = []
    try:
        # Standard single-query retrieval
        return await _retrieve_single_query(query, user_id, use_advanced_rag)
        
    except Exception as e:
        logger.error(f"Error in enhanced RAG search: {e}")
        return {"context": f"Error searching knowledge base for '{query}': {str(e)}", "sources": [], "images": []}


async def _retrieve_single_query(query: str, user_id: str, use_advanced_rag: bool = True, correction_depth: int = 0) -> Dict[str, Any]:
    """
    Internal function to retrieve for a single query.
    Enhanced with reranking and corrective RAG.
    
    Args:
        query: Query to retrieve
        user_id: User ID
        use_advanced_rag: Whether to use advanced RAG techniques
        correction_depth: Depth of correction recursion (max 1 to prevent infinite loops)
    """
    sources = []
    try:
        from qdrant_client import models as qm
        import numpy as np
        
        # 1. Embed the query (synchronous, fast)
        rag_impl.embed_dense_azure([query])  # warmth
        dense_q = rag_impl.embed_dense_azure([query])[0]
        sparse_q = rag_impl.build_sparse_query_vector(query)
        
        # 2. Run Qdrant search and Graphiti search in PARALLEL
        circuit = get_qdrant_circuit()
        logger.info(f"🔍 Starting parallel Qdrant + Graphiti search for query: {query[:50]}")
        
        async def qdrant_search():
            """Qdrant search task - run in executor to make it async."""
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: circuit.call(
                        lambda: qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                                qm.Prefetch(query=dense_q,  using=rag_impl.DENSE_NAME,  limit=15),
                                qm.Prefetch(query=sparse_q, using=rag_impl.SPARSE_NAME, limit=15),
            ],
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                            limit=7,  # Reduced to 7 documents for faster processing
                        )
                    )
                )
                logger.info(f"✅ Qdrant search completed: {len(result.points) if result.points else 0} points found")
                return result, None
            except Exception as e:
                logger.error(f"Qdrant search failed: {e}")
                return None, e
        
        async def graphiti_search():
            """Graphiti search task."""
            try:
                facts = await search_graphiti_memory(query, num_results=5)
                logger.info(f"✅ Graphiti search completed: {len(facts)} facts found")
                return facts, None
            except Exception as e:
                logger.error(f"Graphiti search failed: {e}")
                return [], e
        
        # Run both searches in parallel
        qdrant_result, graphiti_result = await asyncio.gather(
            qdrant_search(),
            graphiti_search(),
            return_exceptions=False
        )
        
        content_search, qdrant_error = qdrant_result
        facts, graphiti_error = graphiti_result
        
        # Handle Qdrant errors
        if qdrant_error or not content_search:
            if graphiti_error:
                context = f"**Context for '{query}':**\n\n**Error**: Both Qdrant and Graphiti searches failed."
                return {"context": context, "sources": [], "images": []}
            facts_text = "\n".join([f"- {f.get('fact')}" for f in facts])
            context = f"**Context for '{query}':**\n\n**Error**: Qdrant search failed: {str(qdrant_error) if qdrant_error else 'Unknown error'}\n\n**Memory Facts:**\n{facts_text}"
            return {"context": context, "sources": [], "images": []}
        
        # Check if Qdrant returned any results
        if not content_search.points or len(content_search.points) == 0:
            logger.warning(f"Qdrant returned no results for query: {query}")
            facts_text = "\n".join([f"- {f.get('fact')}" for f in facts])
            context = f"**Context for '{query}':**\n\n**Note**: No documents found in knowledge base.\n\n**Memory Facts:**\n{facts_text}"
            return {"context": context, "sources": [], "images": []}
        
        # 3. Extract unique source files and calculate filename similarity (can run while processing)
        filename_scores = {}
        unique_files = set()
        for p in content_search.points:
            src_file = (p.payload or {}).get('source_file', 'unknown')
            unique_files.add(src_file)
        
        # Embed filenames and calculate similarity to query
        if unique_files:
            filenames_list = list(unique_files)
            # Use normalized filename text (remove extensions, replace separators)
            normalized_names = [f.replace('.md', '').replace('-', ' ').replace('_', ' ') for f in filenames_list]
            
            # Embed filenames (synchronous, but fast)
            try:
                filename_embeddings = rag_impl.embed_dense_azure(normalized_names)
                query_vec = np.array(dense_q)
                
                for i, fname in enumerate(filenames_list):
                    fname_vec = np.array(filename_embeddings[i])
                    # Cosine similarity
                    similarity = np.dot(query_vec, fname_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(fname_vec) + 1e-8)
                    filename_scores[fname] = float(similarity)
            except Exception:
                # If embedding fails, use simple keyword matching as fallback
                query_lower = query.lower()
                for fname in filenames_list:
                    fname_lower = fname.lower()
                    match_score = sum(1 for word in query_lower.split() if word in fname_lower)
                    filename_scores[fname] = match_score * 0.1  # Scale to [0, ~1]
        
        # 4. Prepare documents for reranking (if enabled)
        documents_for_rerank = []
        original_scores = []
        for p in content_search.points:
            pl = p.payload or {}
            src_file = pl.get('source_file', 'unknown')
            content_score = p.score or 0
            fname_boost = filename_scores.get(src_file, 0) * 0.3
            combined_score = content_score + fname_boost
            
            documents_for_rerank.append({
                "content": pl.get('text', ''),
                "metadata": {
                    "source_file": src_file,
                    "id": p.id,
                    "has_images": pl.get("has_images", False),
                    "images": pl.get("images", [])
                }
            })
            original_scores.append(combined_score)
        
        # 5. Apply reranking if enabled (run in parallel with document processing prep)
        if use_advanced_rag and reranker and len(documents_for_rerank) > 0:
            # Run reranking in executor to not block
            loop = asyncio.get_event_loop()
            ranked_docs = await loop.run_in_executor(
                None,
                lambda: reranker.rerank(query, documents_for_rerank, original_scores)
            )
            top_results = ranked_docs[:7]  # Take top 7 after reranking
            logger.info(f"Applied reranking: {len(ranked_docs)} documents reranked")
        else:
            # Fallback: simple ranking by combined score
            ranked_results = list(zip(original_scores, documents_for_rerank))
            ranked_results.sort(key=lambda x: x[0], reverse=True)
            top_results = [{"content": doc["content"], "metadata": doc["metadata"], "original_score": score, "rerank_score": score, "final_score": score, "rank": i+1} for i, (score, doc) in enumerate(ranked_results[:7])]
        
        # 6. Build output from ranked results
        docs_text = ""
        retrieved_images = []
        context_chunks = []
        
        for ranked_doc in top_results:
            # Handle both RankedDocument objects and dicts
            if hasattr(ranked_doc, 'content'):
                # RankedDocument object
                doc_content = ranked_doc.content
                doc_metadata = ranked_doc.metadata
                final_score = ranked_doc.final_score
            else:
                # Dict format
                doc_content = ranked_doc.get("content", "")
                doc_metadata = ranked_doc.get("metadata", {})
                final_score = ranked_doc.get("final_score", 0.5)
            
            src_file = doc_metadata.get('source_file', 'unknown')
            text_snippet = doc_content[:600]
            context_chunks.append(text_snippet)
            docs_text += f"\n- [{src_file}]: {text_snippet}..."
            
            sources.append({
                "id": doc_metadata.get('id', ''),
                "score": round(final_score, 4),
                "source": src_file,
                "text_snippet": text_snippet[:200],
                "has_images": doc_metadata.get("has_images", False)
            })
            
            # Extract images
            if doc_metadata.get("has_images") and doc_metadata.get("images"):
                for img in doc_metadata.get("images", [])[:2]:
                    if img.get("image_b64") and len(retrieved_images) < 3:
                        retrieved_images.append({
                            "b64": img["image_b64"],
                            "caption": img.get("caption", ""),
                            "source": src_file
                        })
            
        # 7. Graphiti (already retrieved in parallel above, just format it)
        facts_text = "\n".join([f"- {f.get('fact')}" for f in facts])
        
        # Build initial context
        initial_context = f"**Context for '{query}':**\n\n**Documents:**{docs_text}\n\n**Memory Facts:**\n{facts_text}"
        
        # 8. Apply Corrective RAG if enabled (only once to prevent infinite loops)
        # Run evaluation in executor to not block
        # Skip corrective RAG if correction_depth > 0 (prevents recursive corrections and turn 3 corrections)
        if use_advanced_rag and corrective_rag and correction_depth == 0:
            loop = asyncio.get_event_loop()
            evaluation = await loop.run_in_executor(
                None,
                lambda: corrective_rag.evaluate_retrieval(query, initial_context, sources)
            )
            logger.info(f"Retrieval evaluation: {evaluation.quality.value} (relevance: {evaluation.relevance_score:.2f}, completeness: {evaluation.completeness_score:.2f})")
            
            # Only correct if quality is poor (not fair, good, or excellent) and we haven't already corrected
            # Skip correction for "good" or "excellent" quality - they don't need correction
            if evaluation.quality.value == "poor" and corrective_rag.should_correct(evaluation):
                logger.info(f"Retrieval quality is POOR - correction needed")
            elif evaluation.quality.value in ["good", "excellent"]:
                logger.info(f"Retrieval quality is {evaluation.quality.value.upper()} - skipping correction (no improvement needed)")
                logger.info(f"Retrieval needs correction. Gaps: {evaluation.gaps[:2]}")  # Log only first 2
                # Filter irrelevant content
                if evaluation.irrelevant_parts:
                    initial_context = corrective_rag.filter_irrelevant(initial_context, evaluation.irrelevant_parts)
                
                # Only attempt re-retrieval if quality is poor and we have refined queries
                if evaluation.refined_queries and len(evaluation.gaps) > 0:
                    logger.info(f"Attempting re-retrieval with refined query: {evaluation.refined_queries[0]}")
                    try:
                        # Use a shorter timeout for re-retrieval and disable advanced RAG to prevent recursion
                        refined_result = await asyncio.wait_for(
                            _retrieve_single_query(evaluation.refined_queries[0], user_id, use_advanced_rag=False, correction_depth=1),
                            timeout=10.0  # Shorter timeout for re-retrieval
                        )
                        if refined_result.get("context"):
                            # Merge with original (limit additional context size)
                            additional_context = refined_result['context'][:2000]  # Limit to 2000 chars
                            initial_context = f"{initial_context}\n\n**Additional Context:**\n{additional_context}"
                            sources.extend(refined_result.get("sources", [])[:3])  # Limit to 3 additional sources
                    except asyncio.TimeoutError:
                        logger.warning("Re-retrieval timed out, proceeding with original context")
                    except Exception as e:
                        logger.warning(f"Re-retrieval failed: {e}, proceeding with original context")
        
        # 9. Apply contextual compression if context is too long
        if use_advanced_rag and contextual_compressor and contextual_compressor.should_compress(initial_context):
            compressed = contextual_compressor.compress(initial_context, query)
            context = compressed.content
            logger.info(f"Context compressed: {compressed.compression_ratio:.2%}")
        else:
            context = initial_context
        
        return {"context": context, "sources": sources, "images": retrieved_images}
        
    except Exception as e:
        return {"context": f"Error searching knowledge base for '{query}': {str(e)}", "sources": [], "images": []}


# --- LLM Client for Agent ---
agent_llm = AzureChatOpenAI(
    azure_deployment=AZURE_CHAT_DEPLOYMENT,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    temperature=0
)

# --- State Definition ---
class AgentState(TypedDict):
    original_query: str
    user_id: str
    complexity: Literal["SIMPLE", "COMPLEX", "FORMAT", "GENERIC", "DOC_PREFERENCE", "CLARIFICATION_ANSWER"]
    sub_queries: List[str]
    sub_answers: List[str]
    final_answer: str
    previous_response: str  # For FORMAT path
    sources: List[Dict[str, Any]]  # Track referenced documents
    images: List[Dict[str, Any]]  # Retrieved images for multimodal inference
    # Clarification flow fields
    clarifying_questions: List[str]  # Questions to ask user for GENERIC queries
    awaiting_clarification: bool  # Flag to indicate we need user input
    user_responses: List[str]  # User's answers to clarifying questions
    rag_context_for_clarification: str  # Initial RAG context used to generate questions
    original_user_query: str  # The actual user query before doc type preference was asked
    # Self-reflection and quality gate fields
    reflection_iteration: Optional[int]  # Current reflection iteration count
    termination_decision: Optional[Dict[str, Any]]  # Termination decision from self-evaluator
    validation_result: Optional[Dict[str, Any]]  # Validation result from quality gate
    # Greeting detection fields
    is_greeting: Optional[bool]  # True if query is a greeting/casual message
    greeting_type: Optional[str]  # Type of greeting: 'greeting', 'casual', 'emotional', or None

# --- Nodes ---

# 0. Greeting Detection Node
class GreetingDetectionOutput(BaseModel):
    is_greeting: bool = Field(description="True if the query is a greeting, casual message, or emotional expression")
    greeting_type: Optional[str] = Field(description="Type of greeting if detected: 'greeting', 'casual', 'emotional', or None")

async def greeting_detection_node(state: AgentState):
    """
    Detect if the user query is a greeting, casual message, or emotional expression.
    Uses fast pattern matching for obvious greetings, then LLM classifier for context-aware detection.
    """
    query = state["original_query"]
    user_id = state["user_id"]
    
    # Fast path: Check for obvious greetings first (before checking clarification sessions)
    query_lower = query.lower().strip()
    obvious_greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", 
                         "thanks", "thank you", "okay", "ok", "sure", "great", "awesome", "perfect"]
    is_obvious_greeting = any(greeting == query_lower or query_lower.startswith(greeting + " ") 
                             for greeting in obvious_greetings) and len(query.split()) <= 5
    
    # If it's an obvious greeting, abandon any clarification session and return immediately
    if is_obvious_greeting:
        active_session = clarification_tracker.get_active_session(user_id)
        if active_session:
            clarification_tracker.abandon_session(user_id)
            logger.info(f"Greeting detection: Abandoned clarification session for obvious greeting")
        logger.info(f"Greeting detection: Fast path - obvious greeting detected")
        greeting_type = "greeting" if any(g in query_lower for g in ["hi", "hello", "hey", "good"]) else "casual"
        return {
            "is_greeting": True,
            "greeting_type": greeting_type
        }
    
    # Skip if there's an active clarification session (don't treat clarification answers as greetings)
    # But only if it's NOT an obvious greeting (we already handled that above)
    active_session = clarification_tracker.get_active_session(user_id)
    if active_session:
        logger.info(f"Greeting detection: Active clarification session, skipping greeting check")
        return {"is_greeting": False}
    
    # Use LLM classifier primarily for natural, context-aware greeting detection
    from llm_classifier import get_llm_classifier
    llm_classifier = get_llm_classifier()
    
    if llm_classifier:
        try:
            # Get conversation history for context
            conversation_history = []
            if user_id:
                history = get_user_history(user_id, use_summarization=False)
                conversation_history = history[-5:]  # Last 5 messages for context
            
            # Use LLM classifier with conversation history
            result = llm_classifier.classify_query(
                query=query,
                conversation_context=conversation_history,
                active_clarification=False
            )
            
            is_greeting = result.is_greeting or result.is_casual
            greeting_type = "greeting" if result.is_greeting else ("casual" if result.is_casual else None)
            
            logger.info(f"🧠 LLM Greeting Detection: is_greeting={is_greeting}, type={result.query_type} "
                       f"(reasoning: {result.reasoning[:100]})")
            
            return {
                "is_greeting": is_greeting,
                "greeting_type": greeting_type or "greeting"
            }
        except Exception as e:
            logger.warning(f"LLM classifier failed for greeting detection, using fallback: {e}")
    
    # Fallback: Use pattern matching if LLM classifier not available or fails
    # Get conversation history for fallback too
    conversation_history = []
    if user_id:
        try:
            history = get_user_history(user_id, use_summarization=False)
            conversation_history = history[-5:]
        except:
            pass
    
    is_greeting_pattern = is_greeting_or_casual(query, conversation_history)
    if is_greeting_pattern:
        logger.info(f"Greeting detection: Pattern matching detected greeting")
        return {"is_greeting": True, "greeting_type": "greeting"}
    
    # Final fallback: Try structured LLM if available
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a greeting detection expert. Determine if the user's message is:\n"
                       "- A greeting (hello, hi, good morning, etc.)\n"
                       "- A casual message (thanks, okay, sure, etc.)\n"
                       "- An emotional expression (thank you, great, awesome, etc.)\n"
                       "- OR an actual HR question/query that needs to be answered\n\n"
                       "Examples of greetings/casual:\n"
                       "- 'Hello', 'Hi', 'Good morning', 'Hey'\n"
                       "- 'Thanks', 'Thank you', 'Okay', 'Sure'\n"
                       "- 'Great', 'Awesome', 'Perfect'\n\n"
                       "Examples of HR queries (NOT greetings):\n"
                       "- 'What is the leave policy?', 'How do I apply for leave?', 'Tell me about insurance'\n"
                       "- Even if they start with 'Hi, what is...' - this is an HR query, not just a greeting"),
            ("user", "{query}")
        ])
        
        chain = prompt | agent_llm.with_structured_output(GreetingDetectionOutput)
        result = await chain.ainvoke({"query": query})
        
        logger.info(f"Greeting detection: Structured LLM result - is_greeting={result.is_greeting}, type={result.greeting_type}")
        return {
            "is_greeting": result.is_greeting,
            "greeting_type": result.greeting_type
        }
    except Exception as e:
        logger.error(f"Error in structured greeting detection: {e}")
        # Final fallback: use pattern matching
        is_greeting = is_greeting_or_casual(query, conversation_history)
        return {"is_greeting": is_greeting}

# 0b. Greeting Response Node
async def greeting_response_node(state: AgentState):
    """
    Generate a friendly greeting response for greetings, casual messages, or emotional expressions.
    Greetings should NEVER create clarification sessions.
    Uses LLM for ALL greetings with conversation context for personalized, context-aware responses.
    """
    query = state["original_query"]
    user_id = state["user_id"]
    greeting_type = state.get("greeting_type", "greeting")
    
    # Explicitly abandon any active clarification session for greetings
    # Greetings are not clarification answers and should not create sessions
    active_session = clarification_tracker.get_active_session(user_id)
    if active_session:
        clarification_tracker.abandon_session(user_id)
        logger.info(f"Abandoned clarification session for {user_id} - greeting detected")
    
    # Get conversation history for personalized, context-aware responses
    conversation_history = []
    if user_id:
        try:
            history = get_user_history(user_id, use_summarization=False)
            conversation_history = history[-10:]  # Last 10 messages for context
        except Exception as e:
            logger.warning(f"Could not retrieve conversation history for greeting: {e}")
    
    # Build conversation context string for LLM
    context_str = ""
    if conversation_history:
        context_parts = []
        for msg in conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content and role in ["user", "assistant"]:
                context_parts.append(f"{role.capitalize()}: {content}")
        if context_parts:
            context_str = "\n".join(context_parts[-5:])  # Last 5 messages for context
    
    # Use LLM for ALL greetings with conversation context for personalization
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a friendly, professional HR assistant chatbot. Respond warmly and naturally to greetings, casual messages, or emotional expressions.

Guidelines:
- Be warm, friendly, and professional
- Keep responses brief (1-2 sentences)
- Personalize based on conversation history when available
- If the user has asked questions before, acknowledge continuity naturally
- If the user says thank you or expresses appreciation, acknowledge it warmly
- If it's a greeting, greet them back and offer to help with HR questions
- Vary your responses naturally - don't repeat the same phrase every time
- Consider the time of day for greetings (good morning/afternoon/evening)
- If conversation history shows previous topics, you can briefly reference them naturally

Examples:
- First greeting: "Hello! I'm here to help you with HR policies, benefits, and procedures. What can I assist you with today?"
- Returning user: "Hello again! How can I help you with your HR questions today?"
- After helping: "You're very welcome! Let me know if you need anything else about policies or benefits."
- Good morning: "Good morning! I'm here to help with your HR questions. What can I assist you with today?"
- Thank you: "You're welcome! I'm glad I could help. Is there anything else you'd like to know?"

Stay in character as an HR assistant, not a general chatbot."""),
        ("user", """User's current message: {query}

{context}""")
    ])
    
    try:
        # Build messages with context
        messages = [
            ("system", prompt.messages[0].content),
            ("user", prompt.messages[1].content.format(
                query=query,
                context=f"Recent conversation history:\n{context_str}" if context_str else "This appears to be the start of the conversation."
            ))
        ]
        
        response = await agent_llm.ainvoke(messages)
        greeting_response = response.content.strip()
        
        logger.info(f"🧠 LLM Generated Personalized Greeting Response: {greeting_response[:100]}... "
                   f"(context: {len(conversation_history)} messages)")
        
    except Exception as e:
        logger.error(f"Error generating personalized greeting response via LLM: {e}")
        # Fallback to simple template if LLM fails
        query_lower = query.lower().strip()
        if "good morning" in query_lower:
            greeting_response = "Good morning! How can I assist you with your HR questions today?"
        elif "good afternoon" in query_lower:
            greeting_response = "Good afternoon! How can I help you with your HR questions today?"
        elif "good evening" in query_lower:
            greeting_response = "Good evening! How can I assist you with your HR questions today?"
        elif "thanks" in query_lower or "thank you" in query_lower:
            greeting_response = "You're welcome! Is there anything else I can help you with?"
        else:
            greeting_response = "Hello! How can I help you with your HR questions today?"
        logger.info(f"Used fallback greeting response due to LLM error")
    
    return {
        "final_answer": greeting_response,
        "sources": [],
        "awaiting_clarification": False,
        "complexity": "SIMPLE"
    }

# 1. Router Node
class RouterOutput(BaseModel):
    complexity: Literal["SIMPLE", "COMPLEX", "FORMAT", "GENERIC", "DOC_PREFERENCE", "CLARIFICATION_ANSWER"] = Field(description="Classification of the query")

async def router_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    previous_response = state.get("previous_response", "")
    
    # Check if user is responding to a document preference question
    preference_keywords = ["workflow", "policy", "guideline", "both", "1", "2", "3"]
    is_preference_response = (
        "Which type would you prefer" in previous_response and
        any(kw in query.lower() for kw in preference_keywords)
    )
    
    if is_preference_response:
        return {"complexity": "DOC_PREFERENCE"}
    
    # Check if user is answering clarifying questions (CHECK FIRST, before LLM routing)
    active_session = clarification_tracker.get_active_session(user_id)
    if active_session:
        if clarification_tracker.is_clarification_response(user_id, query):
            # User is answering a clarifying question
            logger.info(f"Router: Detected clarification answer for {user_id}: {query[:50]}")
            return {"complexity": "CLARIFICATION_ANSWER"}
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert at routing user queries. \n"
                   "Classify the query as:\n"
                   "- 'SIMPLE' if it is specific, factual, and can be answered with a single lookup (e.g., 'What is the dress code?', 'How do I apply for leave?', 'What is the notice period?').\n"
                   "- 'COMPLEX' if it implies multiple steps, comparisons, aggregating information from different sections, or requires a comprehensive guide (e.g., 'Compare the leave policy for sick leave vs annual leave').\n"
                   "- 'FORMAT' if the user is asking to reformat, summarize differently, or change the presentation of the previous response WITHOUT needing new information (e.g., 'Put that in a table', 'Make it bullet points').\n"
                   "- 'GENERIC' if the query is ambiguous, too broad, or MISSES CRITICAL CONTEXT (like Country/Location) causing the answer to vary (e.g., 'How many days maternity leave?', 'What are the travel allowances?', 'How can I benefit from insurance?'). These need clarification."),
        ("user", "{query}")
    ])
    chain = prompt | agent_llm.with_structured_output(RouterOutput)
    result = await chain.ainvoke({"query": query})
    return {"complexity": result.complexity}

# 2. Simple Handler (Direct RAG)
class SimpleRAGOutput(BaseModel):
    answer: str = Field(description="The answer to the user query")
    status: Literal["ANSWERED", "NEEDS_CLARIFICATION"] = Field(description="Set to NEEDS_CLARIFICATION if the answer depends on missing variables (e.g. Position, Country) that the user didn't provide.")
    missing_variables: List[str] = Field(description="List of missing variables if status is NEEDS_CLARIFICATION (e.g. ['Job Position', 'Country'])")

async def simple_rag_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    search_result = await run_search_for_deep_agent(query, user_id)
    context = search_result["context"]
    sources = search_result["sources"]
    retrieved_images = search_result.get("images", [])
    
    # Check if we have both workflow (- W) and normal documents
    workflow_sources = [s for s in sources if " - W " in s.get("source", "") or " - W-" in s.get("source", "")]
    normal_sources = [s for s in sources if s not in workflow_sources]
    
    has_workflow = len(workflow_sources) > 0
    has_normal = len(normal_sources) > 0
    
    # If we have BOTH types, ask user for preference
    if has_workflow and has_normal:
        workflow_docs = list(set([s["source"] for s in workflow_sources]))
        normal_docs = list(set([s["source"] for s in normal_sources]))
        
        response_text = (
            "I found relevant information from both **workflow documents** and **policy/guideline documents**.\n\n"
            f"**Workflow Documents** (step-by-step procedures):\n" + 
            "\n".join([f"- {doc}" for doc in workflow_docs[:3]]) + "\n\n"
            f"**Policy/Guideline Documents**:\n" + 
            "\n".join([f"- {doc}" for doc in normal_docs[:3]]) + "\n\n"
            "Which type would you prefer?\n"
            "1. **Workflow** - Detailed step-by-step process\n"
            "2. **Policy/Guideline** - General rules and information\n"
            "3. **Both** - Combined information from all sources\n\n"
            "Please reply with your preference (e.g., 'workflow', 'policy', or 'both')."
        )
        return {
            "final_answer": response_text, 
            "sources": sources,
            "images": retrieved_images,
            "awaiting_clarification": True,
            "clarifying_questions": ["Document type preference: workflow, policy, or both?"]
        }
    
    # Build messages with multimodal support if images are present
    if has_workflow and not has_normal:
        system_prompt = ("You are a helpful HR assistant. The user's query matched WORKFLOW documents which contain step-by-step procedures. "
                        "Provide a detailed, structured answer following the workflow steps. Use numbered steps where appropriate. "
                        "If images/diagrams are provided, reference them in your explanation.")
    else:
        system_prompt = ("You are a helpful HR assistant. Answer the user request based STRICTLY on the context provided from the knowledge base documents. "
                        "CRITICAL RULES:\n"
                        "1. ONLY use information that is explicitly stated in the provided context.\n"
                        "2. Do NOT make up, infer, or add information not present in the context.\n"
                        "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                        "4. If the context does not contain enough information to answer the question, state that clearly.\n"
                        "5. Quote specific details, numbers, dates, or procedures directly from the context when available.\n"
                        "6. If images/diagrams are provided, reference them in your explanation.\n\n"
                        "TABLE PARSING: Be extremely robust to malformed markdown tables. "
                        "1. HEADERS SPLIT: If a column header looks cut off (e.g., ends in '&' or starts with a lowercase letter), it belongs to the previous column. Merge them. "
                        "2. VALUES SHIFTED: If columns are split, their values might be shifted. Align them logically. "
                        "3. COMBINED HEADERS: If a header mentions multiple entities (e.g. 'Brand A & Brand B' or 'OYSHO Pull & Bear'), the values in that column apply to ALL listed entities. "
                        "4. EXTRACT VALUES: Do not complain about formatting. Use your best judgement to reconstruct the table and return the requested value.\n\n"
                        "**DYNAMIC CLARIFICATION**:\n"
                        "If the retrieved context shows that the answer varies based on specific criteria (e.g., Job Position, Country, Seniority) that the user HAS NOT provided, do **not** try to list every possible option.\n"
                        "Instead, set status to 'NEEDS_CLARIFICATION' and list the missing variables (e.g. ['Job Position']).\n"
                        "Only set this if the answer is TRULY ambiguous without that info.")
    
    # Multimodal inference if images are present
    messages = []
    messages.append(("system", system_prompt))
    
    if retrieved_images:
        # Build multimodal message with text and images
        user_content = [
            {"type": "text", "text": f"Context:\n{context}\n\nQuestion: {query}"}
        ]
        for img_data in retrieved_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_data['b64']}"}
            })
        messages.append(("user", user_content))
    else:
        messages.append(("user", f"Context:\n{context}\n\nQuestion: {query}"))
        
    chain = agent_llm.with_structured_output(SimpleRAGOutput)
    result = await chain.ainvoke(messages)
    
    if result.status == "NEEDS_CLARIFICATION":
        # Pass control to Clarifier node
        return {
            "final_answer": result.answer, # Can be empty or a transitional phrase
            "sources": sources,
            "images": retrieved_images,
            "awaiting_clarification": True,
            "rag_context_for_clarification": context, # Pass context so clarifier doesn't re-search
            "complexity": "GENERIC" # Shift complexity to GENERIC (Clarification)
        }
    else:
        return {
            "final_answer": result.answer,
            "sources": sources,
            "images": retrieved_images
        }

# 3. Decomposer (Complex Path)
class DecompositionOutput(BaseModel):
    sub_queries: List[str] = Field(description="List of 2-4 sub-questions to answer the main query.")

async def decomposer_node(state: AgentState):
    query = state["original_query"]
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert planner. Break down the complex query into 2-4 distinct, simpler sub-queries that, when answered, will allow you to answer the main query comprehensively. Return ONLY the list of strings."),
        ("user", "{query}")
    ])
    chain = prompt | agent_llm.with_structured_output(DecompositionOutput)
    result = await chain.ainvoke({"query": query})
    return {"sub_queries": result.sub_queries}

# 4. Executor (Complex Path)
async def executor_node(state: AgentState):
    sub_queries = state["sub_queries"]
    user_id = state["user_id"]

    # Run all sub-query searches in parallel for maximum performance
    logger.info(f"Executing {len(sub_queries)} sub-queries in parallel")

    # Create tasks for parallel execution
    search_tasks = [
        run_search_for_deep_agent(q, user_id)
        for q in sub_queries
    ]

    # Execute all searches concurrently
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Process results
    answers = []
    all_sources = []

    for i, (sub_query, result) in enumerate(zip(sub_queries, search_results)):
        # Handle exceptions gracefully
        if isinstance(result, Exception):
            logger.error(f"Error in sub-query {i+1} '{sub_query}': {result}")
            answers.append(f"### Q: {sub_query}\n[Error retrieving information for this query]")
            continue

        context_str = result["context"]
        all_sources.extend(result["sources"])
        answers.append(f"### Q: {sub_query}\n{context_str}")

    logger.info(f"Completed {len(answers)}/{len(sub_queries)} sub-queries successfully")

    return {"sub_answers": answers, "sources": all_sources}

# 5. Synthesizer (Complex Path)
async def synthesizer_node(state: AgentState):
    original_query = state["original_query"]
    sub_answers = state["sub_answers"]
    
    combined_context = "\n\n".join(sub_answers)
    
    messages = [
        ("system", "You are a helpful HR expert. You have gathered information for a complex user request. "
                   "Synthesize the provided sub-answers into a cohesive final report.\n\n"
                   "CRITICAL RULES:\n"
                   "1. ONLY use information that is explicitly stated in the provided sub-answers (which come from knowledge base documents).\n"
                   "2. Do NOT make up, infer, or add information not present in the sub-answers.\n"
                   "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                   "4. If the sub-answers do not contain enough information, state that clearly.\n\n"
                   "**CRITICAL INSTRUCTION**:\n"
                   "1. **Direct Answer First**: Start by directly answering the user's ORIGINAL request using the synthesized information.\n"
                   "2. **Supporting Details**: Then, provide the detailed breakdown based on the sub-queries investigating specific aspects.\n"
                   "3. Do not explicitly mention 'sub-queries' or 'step 1', just weave the information together naturally."),
        ("user", f"Original Request: {original_query}\n\nGathered Information from Knowledge Base:\n{combined_context}\n\n"
                f"Based STRICTLY on the information above, synthesize a comprehensive answer. If information is missing, say so explicitly.")
    ]
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content}

# 6. Format Handler (FORMAT Path - No RAG, just reformat previous response)
async def format_handler_node(state: AgentState):
    query = state["original_query"]
    previous_response = state.get("previous_response", "")
    
    if not previous_response:
        return {"final_answer": "I don't have a previous response to reformat. Please ask a question first."}
    
    messages = [
        ("system", "You are a helpful assistant. The user wants you to reformat or re-present a previous response. "
                   "Apply the requested formatting changes to the content provided. Keep the same information, just change how it's presented.\n\n"
                   "CRITICAL: Only reformat the information that was already in the previous response. Do NOT add new information or make up details."),
        ("user", f"Previous Response:\n{previous_response}\n\nUser Request: {query}")
    ]
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content}

# 7. Clarifier Node (GENERIC Path - Ask clarifying questions based on RAG data)
class ClarificationOutput(BaseModel):
    questions: List[str] = Field(description="List of 2-4 clarifying questions to ask the user")
    categories_found: List[str] = Field(description="Categories/options found in the knowledge base")

async def clarifier_node(state: AgentState):
    """
    For GENERIC queries: Fetch initial RAG data, analyze what options/categories exist,
    and generate targeted clarifying questions based on available data.
    Now creates a clarification session to track context.

    IMPORTANT: Questions are generated ONCE and stored in session. If session already exists,
    we reuse the existing questions instead of regenerating.

    GOLDEN RULE: Enforced by conversation_state_machine - max 1 clarification per conversation.
    """
    query = state["original_query"]
    user_id = state["user_id"]

    # Check conversation state machine - enforce golden rules
    # If we've already asked clarification before, skip and answer directly
    if conversation_state_machine.has_clarified(user_id):
        logger.info(f"⚠️ Golden rule enforced: Already clarified once for {user_id}, answering directly without clarification")
        # Answer directly without clarification - use best-guess answering
        search_result = await run_search_for_deep_agent(query, user_id)
        context = search_result.get("context", "")
        sources = search_result.get("sources", [])

        messages = [
            ("system", "You are a helpful HR assistant. Answer the user's question based on the context provided."),
            ("user", f"Question: {query}\n\nContext:\n{context}\n\nProvide a comprehensive answer.")
        ]
        response = await agent_llm.ainvoke(messages)
        answer_text = response.content

        return {
            "final_answer": answer_text,
            "sources": sources,
            "awaiting_clarification": False
        }

    # Update state machine - transitioning to clarification
    conversation_state_machine.transition_to_clarifying(user_id)

    # Check if there's already an active clarification session
    existing_session = clarification_tracker.get_active_session(user_id)
    if existing_session:
        # Check if we're at turn 3 - if so, force completion with document search
        if existing_session.turn_count >= 2:  # After 2 turns, we're at turn 3 (0-indexed: 0, 1, 2 = 3 turns)
            logger.info(f"Clarification at turn 3 for {user_id}, doing final document search and generating answer")
            # Force completion - do ONE document search with combined query
            combined_query = existing_session.get_combined_query() if existing_session.user_answers else existing_session.original_query
            search_result = await run_search_for_deep_agent(combined_query, user_id)
            context = search_result.get("context", existing_session.rag_context)
            sources = search_result.get("sources", existing_session.sources)
            
            # Build clarification summary
            clarification_summary = ""
            if existing_session.user_answers:
                clarification_summary = "\n".join([
                    f"Q{i+1}: {q}\nA: {existing_session.user_answers.get(i, 'Not answered')}" 
                    for i, q in enumerate(existing_session.questions_asked)
                ])
            
            messages = [
                ("system", "You are a helpful HR assistant. Answer the user's question based STRICTLY on the context provided from the knowledge base documents. "
                          "CRITICAL RULES:\n"
                          "1. ONLY use information that is explicitly stated in the provided context.\n"
                          "2. Do NOT make up, infer, or add information not present in the context.\n"
                          "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                          "4. If the context does not contain enough information to answer the question, state that clearly.\n"
                          "5. Quote specific details, numbers, dates, or procedures directly from the context when available."),
                ("user", f"Original Question: {existing_session.original_query}\n\n"
                        + (f"Clarification Answers Provided:\n{clarification_summary}\n\n" if clarification_summary else "")
                        + f"Context from Knowledge Base:\n{context}\n\n"
                        + f"Based STRICTLY on the context above, provide a comprehensive answer to: {existing_session.original_query}\n"
                        + f"If the context does not contain sufficient information, say so explicitly.")
            ]
            response = await agent_llm.ainvoke(messages)
            answer_text = response.content

            clarification_tracker.complete_session(user_id)
            # Mark clarification as completed in state machine (for golden rule enforcement)
            conversation_state_machine.mark_clarification_done(user_id)
            conversation_state_machine.transition_to_answering(user_id)

            return {
                "final_answer": answer_text,
                "sources": sources,
                "awaiting_clarification": False
            }
        
        # Check if we're at turn 3 - if so, force completion immediately
        if existing_session.turn_count >= 2:  # After 2 turns, we're at turn 3 (0-indexed: 0, 1, 2 = 3 turns)
            logger.info(f"Clarification at turn {existing_session.turn_count + 1} (max 3), forcing completion with available information")
            # Force completion - use whatever information we have
            combined_query = existing_session.get_combined_query() if existing_session.user_answers else existing_session.original_query
            
            # Do ONE document search with combined query
            search_result = await run_search_for_deep_agent(combined_query, user_id)
            context = search_result.get("context", existing_session.rag_context)
            sources = search_result.get("sources", existing_session.sources)
            
            # Build clarification summary
            clarification_summary = ""
            if existing_session.user_answers:
                clarification_summary = "\n".join([
                    f"Q{i+1}: {q}\nA: {existing_session.user_answers.get(i, 'Not answered')}" 
                    for i, q in enumerate(existing_session.questions_asked)
                ])
            
            messages = [
                ("system", "You are a helpful HR assistant. Answer the user's question based STRICTLY on the context provided from the knowledge base documents. "
                          "CRITICAL RULES:\n"
                          "1. ONLY use information that is explicitly stated in the provided context.\n"
                          "2. Do NOT make up, infer, or add information not present in the context.\n"
                          "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                          "4. If the context does not contain enough information to answer the question, state that clearly.\n"
                          "5. Quote specific details, numbers, dates, or procedures directly from the context when available."),
                ("user", f"Original Question: {existing_session.original_query}\n\n"
                        + (f"Clarification Answers Provided:\n{clarification_summary}\n\n" if clarification_summary else "")
                        + f"Context from Knowledge Base:\n{context}\n\n"
                        + f"Based STRICTLY on the context above, provide a comprehensive answer to: {existing_session.original_query}\n"
                        + f"If the context does not contain sufficient information, say so explicitly.")
            ]
            response = await agent_llm.ainvoke(messages)
            answer_text = response.content

            clarification_tracker.complete_session(user_id)
            # Mark clarification as completed in state machine (for golden rule enforcement)
            conversation_state_machine.mark_clarification_done(user_id)
            conversation_state_machine.transition_to_answering(user_id)

            return {
                "final_answer": answer_text,
                "sources": sources,
                "awaiting_clarification": False
            }
        
        # Session already exists - reuse existing questions (don't regenerate!)
        logger.info(f"Reusing existing clarification session for {user_id} (turn {existing_session.turn_count + 1})")
        questions = existing_session.questions_asked
        missing = existing_session.get_missing_questions()
        
        if missing:
            # Show remaining questions
            remaining_questions = [questions[i] for i in missing]
            questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(remaining_questions, start=1)])
            response_text = (
                f"I still need a bit more information:\n\n{questions_text}\n\n"
                f"Please provide your answers."
            )
        else:
            # All questions answered but session not complete - shouldn't happen, but handle it
            response_text = "Thank you for the information. Processing your request..."
        
        return {
            "final_answer": response_text,
            "clarifying_questions": remaining_questions if missing else questions,
            "awaiting_clarification": True,
            "rag_context_for_clarification": existing_session.rag_context,
            "sources": existing_session.sources,
            "clarification_session_id": existing_session.session_id
        }
    
    # No existing session - create new one (FIRST TIME ONLY)
    # Check if we already have context (passed from simple_rag_node fallback)
    context = state.get("rag_context_for_clarification")
    sources = state.get("sources", [])
    
    # If not, Fetch initial RAG data (standard GENERIC path)
    if not context:
        search_result = await run_search_for_deep_agent(query, user_id)
        context = search_result["context"]
        sources = search_result["sources"]
    
    # Generate clarifying questions based on what's in the data (ONCE)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an HR assistant helping to clarify a user's generic question.

Based on the retrieved context from our knowledge base, generate 2-4 targeted clarifying questions.

IMPORTANT RULES:
1. Questions should be based on ACTUAL OPTIONS/CATEGORIES found in the context
2. Questions should help narrow down exactly what the user needs
3. Format questions as a numbered list
4. Be specific - use real category names from the context (e.g., "health insurance", "life insurance", "dental")
5. Keep questions concise and clear
6. Ask questions in a logical order (e.g., country first, then position, then specific details)

Example: If user asks "How can I benefit from insurance?" and context mentions health, life, and dental insurance:
- What type of insurance are you interested in: health insurance, life insurance, or dental insurance?
- Are you asking about coverage limits, enrollment process, or claim procedures?"""),
        ("user", f"User's generic question: {query}\n\nAvailable context from knowledge base:\n{context}\n\nGenerate clarifying questions:")
    ])
    
    chain = prompt | agent_llm.with_structured_output(ClarificationOutput)
    result = await chain.ainvoke({"query": query, "context": context})
    
    # Create clarification session to track this (ONCE - questions are fixed now)
    session = clarification_tracker.create_session(
        user_id=user_id,
        original_query=query,
        questions=result.questions,  # These questions are now FIXED for this session
        rag_context=context,
        sources=sources,
        metadata={"request_id": state.get("request_id")}
    )
    
    # Format ALL clarifying questions as the response (first time)
    questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.questions, start=1)])
    response_text = f"To help you better, I need a bit more information:\n\n{questions_text}\n\nPlease provide your answers and I'll give you a detailed response."
    
    logger.info(f"Created NEW clarification session for {user_id} with {len(result.questions)} questions")
    
    return {
        "final_answer": response_text,
        "clarifying_questions": result.questions,
        "awaiting_clarification": True,
        "rag_context_for_clarification": context,
        "sources": sources,
        "clarification_session_id": session.session_id
    }

# 7b. Clarification Answer Handler (CLARIFICATION_ANSWER Path) - Simple Logic
async def clarification_answer_handler_node(state: AgentState):
    """
    Handle user's answers to clarifying questions.
    Simple logic:
    - Turn 3: Always collate all responses, rephrase question, search documents, generate answer
    - Other turns: If we have enough info, generate answer. Otherwise, ask remaining questions.
    """
    query = state["original_query"]
    user_id = state["user_id"]
    
    # Get active clarification session
    session = clarification_tracker.get_active_session(user_id)
    if not session:
        logger.warning(f"No active clarification session for {user_id}, treating as new query")
        return {"complexity": "SIMPLE"}
    
    # Add current answer to session
    query_lower = query.lower()
    has_multiple_parts = "," in query or " and " in query_lower or len(query.split()) > 5
    
    if has_multiple_parts:
        parts = [p.strip() for p in query.replace(" and ", ",").split(",") if p.strip()]
        missing = session.get_missing_questions()
        if missing and len(parts) >= 2:
            for i, part in enumerate(parts):
                if i < len(missing):
                    session = clarification_tracker.add_answer(user_id, part, question_index=missing[i])
        else:
            session = clarification_tracker.add_answer(user_id, query)
    else:
        session = clarification_tracker.add_answer(user_id, query)
    
    # Refresh session
    session = clarification_tracker.get_active_session(user_id)
    if not session:
        return {"complexity": "SIMPLE"}
    
    # Check if this is turn 3 (turn_count: 0=turn1, 1=turn2, 2=turn3)
    is_turn_3 = session.turn_count >= 2
    
    # TURN 3: Always collate all responses, rephrase question, search documents, generate answer
    if is_turn_3:
        logger.info(f"Turn 3 for {user_id}: Collating all responses and generating final answer")
        
        # Use original query for search to preserve intent, but include clarification context
        # The original query is what the user really wants answered
        search_query = session.original_query
        if session.user_answers:
            # Add key clarification terms to help search, but keep original query as primary
            answer_keywords = []
            for i, answer in session.user_answers.items():
                # Extract key terms (first 2-3 words of each answer)
                words = answer.split()[:3]
                answer_keywords.extend(words)
            if answer_keywords:
                search_query = f"{session.original_query} {' '.join(answer_keywords)}"
        logger.info(f"Turn 3 search query (preserving original intent): {search_query}")
        
        # Search documents with query that preserves original intent
        search_result = await _retrieve_single_query(search_query, user_id, use_advanced_rag=False, correction_depth=1)
        context = search_result.get("context", session.rag_context)
        sources = search_result.get("sources", session.sources)
        
        # Build clarification summary with user answers only
        clarification_answers = []
        for i, q in enumerate(session.questions_asked):
            if i in session.user_answers:
                clarification_answers.append(f"- {session.user_answers[i]}")
        
        clarification_summary = "\n".join(clarification_answers) if clarification_answers else "No clarification answers provided."
        
        # Generate answer - emphasize original question and intent
        original_question = session.original_query
        messages = [
            ("system", f"You are a helpful HR assistant. Answer the user's ORIGINAL question based STRICTLY on the context provided from the knowledge base documents. "
                      f"CRITICAL RULES:\n"
                      f"1. The user's ORIGINAL question is: \"{original_question}\" - THIS IS THE MAIN QUESTION TO ANSWER.\n"
                      f"2. The user provided clarification answers to help narrow down the question, but the ORIGINAL question remains the focus.\n"
                      f"3. ONLY use information that is explicitly stated in the provided context.\n"
                      f"4. Do NOT make up, infer, or add information not present in the context.\n"
                      f"5. Do NOT use general knowledge or assumptions outside the documents.\n"
                      f"6. If the context does not contain enough information to answer the question, state that clearly.\n"
                      f"7. Quote specific details, numbers, dates, or procedures directly from the context when available.\n"
                      f"8. ALWAYS answer the ORIGINAL question: \"{original_question}\" - use the clarification context only to focus and narrow your answer."),
            ("user", f"ORIGINAL QUESTION (THIS IS WHAT THE USER WANTS ANSWERED - THIS IS THE MAIN FOCUS):\n{original_question}\n\n"
                    f"CLARIFICATION CONTEXT (user provided these details to help answer the original question - use these to focus your answer):\n{clarification_summary}\n\n"
                    f"CONTEXT FROM KNOWLEDGE BASE:\n{context}\n\n"
                    f"TASK: Based STRICTLY on the context above, provide a comprehensive answer to the ORIGINAL QUESTION: \"{original_question}\"\n"
                    f"Use the clarification context to focus and narrow your answer, but ALWAYS answer the original question.\n"
                    f"If the context does not contain sufficient information, say so explicitly.")
        ]
        response = await agent_llm.ainvoke(messages)
        answer_text = response.content

        # Complete session
        clarification_tracker.complete_session(user_id)
        # Mark clarification as completed in state machine (for golden rule enforcement)
        conversation_state_machine.mark_clarification_done(user_id)
        conversation_state_machine.transition_to_answering(user_id)

        return {
            "final_answer": answer_text,
            "sources": sources,
            "awaiting_clarification": False
        }
    
    # NOT TURN 3: Check if we have enough info to generate answer
    # If all questions answered OR at least 2 answers provided, generate answer
    if session.is_complete() or len(session.user_answers) >= 2:
        logger.info(f"Turn {session.turn_count + 1}: Have enough info, generating answer")
        
        # Do a new search with clarification context to get focused results
        # Build search query that includes original question + clarification keywords
        search_query = session.original_query
        if session.user_answers:
            answer_keywords = []
            for i, answer in session.user_answers.items():
                words = answer.split()[:3]  # Take first 3 words of each answer
                answer_keywords.extend(words)
            if answer_keywords:
                search_query = f"{session.original_query} {' '.join(answer_keywords)}"
        
        logger.info(f"Turn {session.turn_count + 1} search query (with clarification): {search_query}")
        search_result = await _retrieve_single_query(search_query, user_id, use_advanced_rag=False, correction_depth=1)
        context = search_result.get("context", session.rag_context)
        sources = search_result.get("sources", session.sources)
        
        # Build clarification summary with user answers only
        clarification_answers = []
        for i, q in enumerate(session.questions_asked):
            if i in session.user_answers:
                clarification_answers.append(f"- {session.user_answers[i]}")
        
        clarification_summary = "\n".join(clarification_answers) if clarification_answers else "No clarification answers provided."
        original_question = session.original_query
        
        # Generate answer - emphasize original question and use clarification to focus
        messages = [
            ("system", f"You are a helpful HR assistant. Answer the user's ORIGINAL question based STRICTLY on the context provided from the knowledge base documents. "
                      f"CRITICAL RULES:\n"
                      f"1. The user's ORIGINAL question is: \"{original_question}\" - THIS IS THE MAIN QUESTION TO ANSWER.\n"
                      f"2. The user provided clarification answers to help narrow down the question: {clarification_summary}\n"
                      f"3. Use the clarification answers to FOCUS your answer - if the user specified something (e.g., 'personal travel'), focus on that aspect.\n"
                      f"4. ONLY use information that is explicitly stated in the provided context.\n"
                      f"5. Do NOT make up, infer, or add information not present in the context.\n"
                      f"6. Do NOT use general knowledge or assumptions outside the documents.\n"
                      f"7. If the context does not contain enough information to answer the question, state that clearly.\n"
                      f"8. Quote specific details, numbers, dates, or procedures directly from the context when available.\n"
                      f"9. ALWAYS answer the ORIGINAL question, but use the clarification context to focus your answer appropriately."),
            ("user", f"ORIGINAL QUESTION (THIS IS WHAT THE USER WANTS ANSWERED - THIS IS THE MAIN FOCUS):\n{original_question}\n\n"
                    f"CLARIFICATION CONTEXT (user provided these details - USE THESE TO FOCUS YOUR ANSWER):\n{clarification_summary}\n\n"
                    f"CONTEXT FROM KNOWLEDGE BASE:\n{context}\n\n"
                    f"TASK: Based STRICTLY on the context above, provide a comprehensive answer to the ORIGINAL QUESTION: \"{original_question}\"\n"
                    f"IMPORTANT: Use the clarification context to focus your answer. For example, if the user specified 'personal travel', focus on personal travel aspects, not business travel.\n"
                    f"If the context does not contain sufficient information, say so explicitly.")
        ]
        response = await agent_llm.ainvoke(messages)
        answer_text = response.content
        
        # Keep session active (don't complete until turn 3)
        return {
            "final_answer": answer_text,
            "sources": sources,
            "awaiting_clarification": False
        }
    
    # Not enough info yet - ask remaining questions
    missing = session.get_missing_questions()
    remaining_questions = [(i, session.questions_asked[i]) for i in missing]

    if remaining_questions:
        # Use actual indices (i+1) instead of re-numbering from 1
        questions_text = "\n".join([f"{idx+1}. {q}" for idx, q in remaining_questions])
        response_text = f"To help you better, I need a bit more information:\n\n{questions_text}\n\nPlease provide your answers and I'll give you a detailed response."
        
        return {
            "final_answer": response_text,
            "clarifying_questions": [q for idx, q in remaining_questions],
            "awaiting_clarification": True,
            "sources": session.sources
        }
    
    # Fallback
    return {"complexity": "SIMPLE"}

# 9. Document Preference Handler (DOC_PREFERENCE Path)
async def doc_preference_handler_node(state: AgentState):
    """
    Handle user's response to document type preference question.
    Extract original query from history and answer based on preferred doc type.
    """
    preference = state["original_query"].lower()
    user_id = state["user_id"]
    original_user_query = state.get("original_user_query", "")
    
    # Determine which doc types to use
    use_workflow = "workflow" in preference or "1" in preference
    use_policy = "policy" in preference or "guideline" in preference or "2" in preference
    use_both = "both" in preference or "3" in preference
    
    # Re-search with the original query
    search_result = await run_search_for_deep_agent(original_user_query, user_id)
    context = search_result["context"]
    sources = search_result["sources"]
    
    # Filter sources based on preference
    if use_workflow and not use_both:
        filtered_sources = [s for s in sources if " - W " in s.get("source", "") or " - W-" in s.get("source", "")]
        doc_type_instruction = "Focus on WORKFLOW documents which contain step-by-step procedures. Provide detailed steps."
    elif use_policy and not use_both:
        filtered_sources = [s for s in sources if " - W " not in s.get("source", "") and " - W-" not in s.get("source", "")]
        doc_type_instruction = "Focus on POLICY/GUIDELINE documents. Provide general rules and information."
    else:  # both
        filtered_sources = sources
        doc_type_instruction = "Use ALL available documents. Provide comprehensive information including both procedures and policies."
    
    # Generate answer
    messages = [
        ("system", f"You are a helpful HR assistant. {doc_type_instruction}\n\n"
                  "CRITICAL RULES:\n"
                  "1. ONLY use information that is explicitly stated in the provided context.\n"
                  "2. Do NOT make up, infer, or add information not present in the context.\n"
                  "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                  "4. If the context does not contain enough information to answer the question, state that clearly.\n"
                  "5. Quote specific details, numbers, dates, or procedures directly from the context when available."),
        ("user", f"Context from Knowledge Base:\n{context}\n\n"
                f"Question: {original_user_query}\n\n"
                f"Based STRICTLY on the context above, provide an answer. If the context does not contain sufficient information, say so explicitly.")
    ]
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content, "sources": filtered_sources}

# --- Graph Construction ---
workflow = StateGraph(AgentState)
class SelfReflectionOutput(BaseModel):
    needs_improvement: bool = Field(description="True if answer needs improvement, False if good enough")
    gaps_identified: List[str] = Field(description="List of gaps or issues identified in the answer")
    should_retrieve_more: bool = Field(description="True if should retrieve more context")
    improved_answer: Optional[str] = Field(description="Improved answer if needs_improvement is True")

async def self_reflection_node(state: AgentState):
    """
    Self-reflection: Agent evaluates its own answer and decides if improvement is needed.
    Max 2-3 iterations to prevent infinite loops.
    """
    final_answer = state.get("final_answer", "")
    original_query = state.get("original_query", "")
    sources = state.get("sources", [])
    user_id = state.get("user_id", "")
    iteration_count = state.get("reflection_iteration", 0)
    max_iterations = 2  # Limit to 2 reflection iterations
    awaiting_clarification = state.get("awaiting_clarification", False)
    skip_reflection = state.get("skip_reflection", False)
    
    # Skip if explicitly requested (e.g., turn 3 already did document search)
    if skip_reflection:
        logger.info("Self-reflection: Skipping - explicitly requested (turn 3 final answer)")
        return state
    
    # Skip if no answer or max iterations reached
    if not final_answer or iteration_count >= max_iterations:
        return state
    
    # Get clarification session if exists
    clarification_session = clarification_tracker.get_active_session(user_id)
    
    # Skip self-reflection if still awaiting clarification (not generating final answer yet)
    if awaiting_clarification and clarification_session:
        logger.info("Self-reflection: Skipping - still awaiting clarification answers")
        return state
    
    # Evaluate answer
    termination_decision = self_evaluator.make_termination_decision(
        answer=final_answer,
        query=original_query,
        retrieved_chunks=sources,
        clarification_session=clarification_session,
        iteration_count=iteration_count
    )
    
    # If should terminate, proceed
    if termination_decision.should_terminate:
        logger.info(f"Self-reflection: Answer is good enough (confidence: {termination_decision.confidence_score:.2f})")
        return {
            **state,
            "reflection_iteration": iteration_count + 1,
            "termination_decision": termination_decision.to_dict()
        }
    
    # Needs improvement - check if we can improve
    if termination_decision.reason == TerminationReason.INSUFFICIENT_CONTEXT.value:
        # Check if this is turn 3 clarification completion (already did document search)
        clarification_context = state.get("clarification_context")
        clarification_turn_3 = state.get("clarification_turn_3_complete", False)
        
        # Check if we just completed a clarification session (early answer generation)
        awaiting_clarification = state.get("awaiting_clarification", False)
        
        if clarification_turn_3 and clarification_context:
            logger.info("Self-reflection: Turn 3 clarification - using context from turn 3 search (no new search)")
            new_context = clarification_context
            new_sources = sources  # Use sources from state (already from turn 3 search)
            all_sources = sources
        elif clarification_session and not awaiting_clarification:
            # Clarification session exists but we just generated an answer - use stored context
            logger.info("Self-reflection: Clarification session detected - using stored context (no new search)")
            new_context = clarification_session.rag_context
            new_sources = clarification_session.sources
            all_sources = sources + [s for s in new_sources if s not in sources]
        elif not awaiting_clarification and clarification_session:
            # Session exists but answer was generated - use stored context
            logger.info("Self-reflection: Using stored clarification context (no new search)")
            new_context = clarification_session.rag_context
            new_sources = clarification_session.sources
            all_sources = sources + [s for s in new_sources if s not in sources]
        else:
            # No active clarification - can do new search
            logger.info("Self-reflection: Insufficient context, retrieving more...")
            search_result = await run_search_for_deep_agent(original_query, user_id)
            new_sources = search_result.get("sources", [])
            new_context = search_result.get("context", "")
            all_sources = sources + [s for s in new_sources if s not in sources]
        
        # Regenerate answer with more context
        if new_context:
            messages = [
                ("system", "You are a helpful HR assistant. Improve the following answer by incorporating additional context."),
                ("user", f"Original Query: {original_query}\n\n"
                        f"Previous Answer (needs improvement):\n{final_answer}\n\n"
                        f"Additional Context:\n{new_context}\n\n"
                        f"Please provide an improved, more complete answer.")
            ]
            response = await agent_llm.ainvoke(messages)
            improved_answer = response.content
            
            return {
                **state,
                "final_answer": improved_answer,
                "sources": all_sources,
                "reflection_iteration": iteration_count + 1,
                "termination_decision": termination_decision.to_dict()
            }
    
    # Can't improve further or improvement not needed
    logger.info(f"Self-reflection: Proceeding with current answer (iteration {iteration_count + 1})")
    return {
        **state,
        "reflection_iteration": iteration_count + 1,
        "termination_decision": termination_decision.to_dict()
    }

# 7d. Answer Quality Gate Node (Final validation before termination)
async def answer_quality_gate_node(state: AgentState):
    """
    Answer Quality Gate: Multi-stage validation before returning answer to user.
    Validates completeness, accuracy, relevance, and grounding.
    """
    final_answer = state.get("final_answer", "")
    original_query = state.get("original_query", "")
    sources = state.get("sources", [])
    user_id = state.get("user_id", "")
    reflection_iteration = state.get("reflection_iteration", 0)
    awaiting_clarification = state.get("awaiting_clarification", False)
    skip_quality_gate = state.get("skip_quality_gate", False)
    
    # Skip if explicitly requested (e.g., turn 3 already did document search)
    if skip_quality_gate:
        logger.info("Quality gate: Skipping - explicitly requested (turn 3 final answer)")
        return state
    
    if not final_answer:
        return state
    
    # Get clarification session if exists
    clarification_session = clarification_tracker.get_active_session(user_id)
    
    # Skip quality gate if still awaiting clarification (not generating final answer yet)
    if awaiting_clarification and clarification_session:
        logger.info("Quality gate: Skipping - still awaiting clarification answers")
        return state
    
    # Validate answer
    validation_result = quality_gate.validate_answer(
        answer=final_answer,
        query=original_query,
        retrieved_chunks=sources,
        graphiti_facts=[],  # Will be populated if Graphiti is used
        clarification_session=clarification_session,
        iteration_count=reflection_iteration
    )
    
    # Check if should terminate
    if quality_gate.should_terminate(validation_result):
        # Add confidence indicator or disclaimer if needed
        confidence_indicator = validation_result.get("confidence_indicator")
        disclaimer = validation_result.get("disclaimer")
        
        if disclaimer:
            final_answer = f"{final_answer}\n\n*Note: {disclaimer}*"
        elif confidence_indicator == "low":
            final_answer = f"{final_answer}\n\n*Note: This answer is based on limited information.*"
        
        return {
            **state,
            "final_answer": final_answer,
            "validation_result": validation_result,
            "awaiting_clarification": False
        }
    
    # Action needed
    action = validation_result.get("action", "continue")
    
    if action == "retrieve_more" and reflection_iteration < 2:
        # Check if this is turn 3 clarification completion (already did document search)
        clarification_context = state.get("clarification_context")
        clarification_turn_3 = state.get("clarification_turn_3_complete", False)
        
        # Check if we just completed a clarification session (early answer generation)
        awaiting_clarification = state.get("awaiting_clarification", False)
        
        if clarification_turn_3 and clarification_context:
            logger.info("Quality gate: Turn 3 clarification - using context from turn 3 search (no new search, skipping retrieve_more)")
            # Don't do any retrieval - just use the context we already have
            return {
                **state,
                "validation_result": {**validation_result, "action": "continue"}  # Change action to continue to prevent further searches
            }
        elif clarification_session and not awaiting_clarification:
            # Clarification session exists but we just generated an answer - use stored context, don't search
            logger.info("Quality gate: Clarification session detected - using stored context (no new search, skipping retrieve_more)")
            return {
                **state,
                "validation_result": {**validation_result, "action": "continue"}  # Change action to continue to prevent further searches
            }
        elif clarification_session:
            logger.info("Quality gate: Active clarification session detected - using stored context (no new search)")
            # Use stored context from clarification session
            new_context = clarification_session.rag_context
            new_sources = clarification_session.sources
            all_sources = sources + [s for s in new_sources if s not in sources]
        else:
            # No active clarification - can do new search
            logger.info("Quality gate: Retrieving more context for improvement")
            search_result = await run_search_for_deep_agent(original_query, user_id)
            new_sources = search_result.get("sources", [])
            new_context = search_result.get("context", "")
            all_sources = sources + [s for s in new_sources if s not in sources]
        
        if new_context:
            improved_prompt = quality_gate.get_improved_answer_prompt(
                final_answer, original_query, validation_result
            )
            
            messages = [
                ("system", "You are a helpful HR assistant. Improve the answer based on the feedback."),
                ("user", f"{improved_prompt}\n\nAdditional Context:\n{new_context}")
            ]
            response = await agent_llm.ainvoke(messages)
            
            return {
                **state,
                "final_answer": response.content,
                "sources": all_sources,
                "reflection_iteration": reflection_iteration + 1,
                "validation_result": validation_result
            }
    
    elif action == "ask_clarification":
        # Route to clarification
        return {
            **state,
            "complexity": "GENERIC",
            "awaiting_clarification": True,
            "validation_result": validation_result
        }
    
    # Default: return with validation info
    return {
        **state,
        "validation_result": validation_result
    }

# 8. Answer Relevance Layer - Aligns response to user intent
class AnswerRelevanceOutput(BaseModel):
    is_relevant: bool = Field(description="True if the answer already addresses the user's question/intent, False if it needs refinement")
    refined_answer: str = Field(description="The refined answer if is_relevant is False, otherwise the original answer unchanged")
    relevance_reason: str = Field(description="Brief explanation of the relevance assessment")

# Common greetings and casual messages that should get friendly responses, not clarifying questions
GREETING_PATTERNS = [
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening", 
    "howdy", "greetings", "what's up", "sup", "yo", "hiya"
]
CASUAL_PATTERNS = [
    "thanks", "thank you", "ok", "okay", "bye", "goodbye", "see you", 
    "great", "cool", "nice", "awesome", "perfect", "got it"
]
EMOTIONAL_PATTERNS = [
    "lonely", "sad", "depressed", "stressed", "anxious", "worried", "upset",
    "happy", "excited", "confused", "frustrated", "tired", "bored"
]

def is_greeting_or_casual(query: str, conversation_history: Optional[List[Dict]] = None) -> bool:
    """
    Check if the query is a greeting, casual message, or emotional expression.
    Uses LLM classifier with conversation history for natural, context-aware detection.
    """
    # Try to use LLM classifier if available
    llm_classifier = get_llm_classifier()
    if llm_classifier:
        try:
            result = llm_classifier.classify_query(
                query=query,
                conversation_context=conversation_history,
                active_clarification=False
            )
            # Return True if it's a greeting or casual message
            is_greeting_or_casual_result = result.is_greeting or result.is_casual
            if is_greeting_or_casual_result:
                logger.info(f"🧠 LLM detected greeting/casual: {result.query_type} (reasoning: {result.reasoning[:100]})")
            return is_greeting_or_casual_result
        except Exception as e:
            logger.warning(f"LLM classifier failed for greeting detection, using fallback: {e}")
    
    # Fallback to pattern matching if LLM classifier not available or fails
    query_lower = query.lower().strip()
    
    # Check greetings
    for pattern in GREETING_PATTERNS:
        if query_lower == pattern or query_lower.startswith(pattern + " ") or query_lower.startswith(pattern + ","):
            return True
    
    # Check casual messages
    for pattern in CASUAL_PATTERNS:
        if pattern in query_lower:
            return True
    
    # Check emotional expressions
    for pattern in EMOTIONAL_PATTERNS:
        if pattern in query_lower:
            return True
    
    # Very short messages without HR keywords are likely casual
    if len(query_lower.split()) <= 3:
        hr_keywords = ["leave", "policy", "salary", "bonus", "insurance", "benefits", "vacation", 
                       "maternity", "paternity", "sick", "annual", "hr", "employee", "work", "job"]
        if not any(kw in query_lower for kw in hr_keywords):
            return True
    
    return False

async def answer_relevance_node(state: AgentState):
    """
    Answer Relevance Layer: Evaluates if the final response aligns with user intent.
    - For greetings/casual messages -> refine to friendly response (skip clarifying questions)
    - For actual HR queries needing clarification -> preserve clarifying questions
    - For complete answers -> validate relevance
    """
    original_query = state.get("original_query", "")
    final_answer = state.get("final_answer", "")
    awaiting_clarification = state.get("awaiting_clarification", False)
    
    # Skip if no answer to evaluate
    if not final_answer:
        return state
    
    # For CLARIFICATION_ANSWER: Provide full context to LLM for intelligent evaluation
    # The LLM should see the original question + clarification context, not just the short answer
    complexity = state.get("complexity", "")
    user_id = state.get("user_id", "")
    
    if complexity == "CLARIFICATION_ANSWER":
        # Get the clarification session for full context
        session = clarification_tracker.get_active_session(user_id)
        if session:
            # Build full context for LLM
            original_question = session.original_query
            clarification_context = []
            for i, q in enumerate(session.questions_asked):
                answer = session.user_answers.get(i, "(not answered)")
                clarification_context.append(f"Q: {q}\nA: {answer}")
            
            context_summary = "\n".join(clarification_context) if clarification_context else "No clarification context"
            
            # Use context-aware prompt for CLARIFICATION_ANSWER
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an intelligent Answer Relevance Evaluator with full conversation context.

You have access to the FULL conversation context including:
1. The ORIGINAL question the user asked
2. The clarification questions and user's answers
3. The current user response being evaluated

EVALUATE if the provided answer properly addresses the ORIGINAL question considering ALL context.

IMPORTANT RULES:
- If the answer properly uses the clarification context to answer the original question: is_relevant=True
- If the user seems to be changing topics (asking about something completely different): you may refine
- Preserve answers that are genuinely relevant to the original question + clarification context
- The user's short response (like 'UAE') is an ANSWER to a clarification question, NOT a new query"""),
                ("user", f"""ORIGINAL QUESTION: {original_question}

CLARIFICATION CONTEXT:
{context_summary}

USER'S CURRENT RESPONSE: {original_query}

ANSWER BEING EVALUATED:
{final_answer}

Evaluate if this answer properly addresses the original question using the clarification context.""")
            ])
            
            try:
                chain = prompt | agent_llm.with_structured_output(AnswerRelevanceOutput)
                result = await chain.ainvoke({})
                
                if result.is_relevant:
                    logger.info(f"✅ Answer relevance (CLARIFICATION): ALIGNED - {result.relevance_reason[:100]}")
                    return state
                else:
                    logger.info(f"🔄 Answer relevance (CLARIFICATION): REFINED - {result.relevance_reason[:100]}")
                    return {"final_answer": result.refined_answer, "awaiting_clarification": False}
            except Exception as e:
                logger.warning(f"⚠️ Answer relevance check failed for CLARIFICATION, using original: {e}")
                return state
        else:
            # No session found, skip check
            logger.info("✅ Answer relevance: No clarification session found, skipping")
            return state
    
    # IMPORTANT: Only refine if the query is a greeting/casual message
    # For actual HR queries that need clarification, preserve the clarifying questions
    # Get conversation history for context-aware detection
    user_id = state.get("user_id", "default_user")
    history = get_user_history(user_id, use_summarization=False)
    conversation_history = history[-5:] if history else []
    
    if not is_greeting_or_casual(original_query, conversation_history):
        # This is an actual HR query - don't interfere with clarification
        if awaiting_clarification:
            logger.info(f"✅ Answer relevance: Preserving clarification for HR query")
            return state
        
        # For non-clarification HR answers, do a quick relevance check
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an Answer Relevance Evaluator for an HR knowledge base.

Check if the answer properly addresses the HR question.

RULES:
- If the answer addresses the user's HR question well: is_relevant=True, return answer UNCHANGED
- If the answer is completely off-topic: is_relevant=False, provide a refined answer
- Do NOT change answers that are already relevant
- Preserve all factual HR information"""),
            ("user", f"""User Question: {original_query}

Answer: {final_answer}

Is this answer relevant to the question?""")
        ])
    else:
        # This is a greeting/casual message - refine to appropriate response
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an Answer Relevance Evaluator.

The user sent a greeting or casual message. Check if the response is appropriate.

RULES:
- GREETINGS (hi, hello, hey): Should get a friendly greeting back, NOT clarifying questions
- CASUAL (thanks, ok, bye): Should get natural conversational response
- EMOTIONAL (feeling lonely, stressed): Should get empathetic response

If the response is clarifying questions for a simple greeting, that is NOT relevant - fix it."""),
            ("user", f"""User Message: {original_query}

Response: {final_answer}

If this gave clarifying questions for a simple greeting, fix it with an appropriate response.""")
        ])
    
    try:
        chain = prompt | agent_llm.with_structured_output(AnswerRelevanceOutput)
        result = await chain.ainvoke({"query": original_query, "answer": final_answer})
        
        if result.is_relevant:
            logger.info(f"✅ Answer relevance check: ALIGNED - {result.relevance_reason[:100]}")
            return state
        else:
            logger.info(f"🔄 Answer relevance check: REFINED - {result.relevance_reason[:100]}")
            return {"final_answer": result.refined_answer, "awaiting_clarification": False}
            
    except Exception as e:
        logger.warning(f"⚠️ Answer relevance check failed, using original: {e}")
        return state


# 9. Document Preference Handler (DOC_PREFERENCE Path)
async def doc_preference_handler_node(state: AgentState):
    """
    Handle user's response to document type preference question.
    Extract original query from history and answer based on preferred doc type.
    """
    preference = state["original_query"].lower()
    user_id = state["user_id"]
    original_user_query = state.get("original_user_query", "")
    
    # Determine which doc types to use
    use_workflow = "workflow" in preference or "1" in preference
    use_policy = "policy" in preference or "guideline" in preference or "2" in preference
    use_both = "both" in preference or "3" in preference
    
    # Re-search with the original query
    search_result = await run_search_for_deep_agent(original_user_query, user_id)
    context = search_result["context"]
    sources = search_result["sources"]
    
    # Filter sources based on preference
    if use_workflow and not use_both:
        filtered_sources = [s for s in sources if " - W " in s.get("source", "") or " - W-" in s.get("source", "")]
        doc_type_instruction = "Focus on WORKFLOW documents which contain step-by-step procedures. Provide detailed steps."
    elif use_policy and not use_both:
        filtered_sources = [s for s in sources if " - W " not in s.get("source", "") and " - W-" not in s.get("source", "")]
        doc_type_instruction = "Focus on POLICY/GUIDELINE documents. Provide general rules and information."
    else:  # both
        filtered_sources = sources
        doc_type_instruction = "Use ALL available documents. Provide comprehensive information including both procedures and policies."
    
    # Generate answer
    messages = [
        ("system", f"You are a helpful HR assistant. {doc_type_instruction}\n\n"
                  "CRITICAL RULES:\n"
                  "1. ONLY use information that is explicitly stated in the provided context.\n"
                  "2. Do NOT make up, infer, or add information not present in the context.\n"
                  "3. Do NOT use general knowledge or assumptions outside the documents.\n"
                  "4. If the context does not contain enough information to answer the question, state that clearly.\n"
                  "5. Quote specific details, numbers, dates, or procedures directly from the context when available."),
        ("user", f"Context from Knowledge Base:\n{context}\n\n"
                f"Question: {original_user_query}\n\n"
                f"Based STRICTLY on the context above, provide an answer. If the context does not contain sufficient information, say so explicitly.")
    ]
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content, "sources": filtered_sources}

# --- Graph Contruction ---
workflow = StateGraph(AgentState)

# Add greeting detection and response nodes first
workflow.add_node("greeting_detection", greeting_detection_node)
workflow.add_node("greeting_response", greeting_response_node)

workflow.add_node("router", router_node)
workflow.add_node("simple_rag", simple_rag_node)
workflow.add_node("decomposer", decomposer_node)
workflow.add_node("executor", executor_node)
workflow.add_node("synthesizer", synthesizer_node)
workflow.add_node("format_handler", format_handler_node)
workflow.add_node("clarifier", clarifier_node)
workflow.add_node("clarification_answer_handler", clarification_answer_handler_node)
workflow.add_node("doc_preference_handler", doc_preference_handler_node)
# Self-reflection and quality gate removed - routing directly to answer_relevance
workflow.add_node("answer_relevance", answer_relevance_node)  # Answer relevance layer

# Start with greeting detection (FIRST NODE - all queries go through greeting detection first)
workflow.add_edge(START, "greeting_detection")

# Route from greeting detection: if greeting -> greeting_response, else -> router
def route_after_greeting_detection(state: AgentState):
    if state.get("is_greeting", False):
        return "greeting_response"
    return "router"

workflow.add_conditional_edges("greeting_detection", route_after_greeting_detection)

# Greeting response goes directly to END (skip answer_relevance for speed)
workflow.add_edge("greeting_response", END)

def route_logic(state: AgentState):
    if state["complexity"] == "COMPLEX":
        return "decomposer"
    elif state["complexity"] == "FORMAT":
        return "format_handler"
    elif state["complexity"] == "GENERIC":
        return "clarifier"
    elif state["complexity"] == "CLARIFICATION_ANSWER":
        return "clarification_answer_handler"
    elif state["complexity"] == "DOC_PREFERENCE":
        return "doc_preference_handler"
    return "simple_rag"

workflow.add_conditional_edges("router", route_logic)

workflow.add_edge("decomposer", "executor")
workflow.add_edge("executor", "synthesizer")
# Route synthesizer directly to answer relevance (self-reflection and quality gate removed)
workflow.add_edge("synthesizer", "answer_relevance")

# Route format_handler directly to answer relevance (self-reflection and quality gate removed)
workflow.add_edge("format_handler", "answer_relevance")

# Route clarifier through answer relevance layer (to catch greetings/casual messages)
# Clarifier doesn't need self-reflection as it's asking questions
workflow.add_edge("clarifier", "answer_relevance")

# Route clarification answer handler directly to answer relevance (self-reflection and quality gate removed)
workflow.add_edge("clarification_answer_handler", "answer_relevance")

# Route doc_preference_handler directly to answer relevance (self-reflection and quality gate removed)
workflow.add_edge("doc_preference_handler", "answer_relevance")

# Answer relevance layer goes to END
workflow.add_edge("answer_relevance", END)

def check_simple_rag_status(state: AgentState):
    """Check if simple_rag decided it needs clarification."""
    if state.get("complexity") == "GENERIC" and state.get("awaiting_clarification"):
         return "clarifier"
    # Route through answer relevance layer if not awaiting clarification
    return "answer_relevance"

workflow.add_conditional_edges("simple_rag", check_simple_rag_status)

deep_agent_app = workflow.compile()


@app.post("/query", response_model=QueryResponse, operation_id="query_knowledge_base")
async def query_endpoint(request: QueryRequest):
    """
    Queries the Azadea Knowledge Base.
    Use this tool to fetch answers for specific employee questions.
    Inputs:
    - query: The standalone question (e.g. 'What is the maternity leave policy in Lebanon?')
    - user_id: (Optional) The user's ID.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()
    
    try:
        query_text = request.query.strip()
        user_id = request.user_id or "default_user"

        log_request(request_id, "🤖 QUERY_START", {"query": query_text})

        # Get enhanced components including general query handler and optimization modules
        components = get_enhanced_components()
        # Unpack: conv_manager, clarification_tracker, conversation_summarizer, self_evaluator,
        #         quality_gate, adaptive_retriever, contextual_compressor,
        #         reranker, corrective_rag, general_query_handler, conversational_excellence,
        #         best_guess_answering, user_profile_tracker, topic_change_detector,
        #         conversation_state_machine, unified_clarification_handler
        general_query_handler_instance = components[9]
        conversational_excellence_instance = components[10]
        best_guess_answering_instance = components[11]
        user_profile_tracker_instance = components[12]
        topic_change_detector_instance = components[13]
        conversation_state_machine_instance = components[14]
        unified_clarification_handler_instance = components[15]
        llm_context_classifier_instance = components[16] if len(components) > 16 else None
        llm_classifier_instance = components[17] if len(components) > 17 else None

        # Get conversation history for context-aware classification
        history = get_user_history(user_id)

        # ============================================================================
        # OPTIMIZATION LAYER: User Profile, Topic Detection, State Management
        # ============================================================================

        # 1. Extract and remember user context (role, country, department)
        user_profile_tracker_instance.update_from_query(
            user_id=user_id,
            query=query_text,
            conversation_history=history
        )
        user_profile = user_profile_tracker_instance.get_profile(user_id)
        logger.info(f"👤 User profile for {user_id}: {user_profile}")

        # 2. Detect topic changes for smooth transitions
        # BUT: Use LLM to intelligently determine if user is answering a clarification
        topic_acknowledgment = None
        
        # Check if there's an active clarification session
        active_clarification = clarification_tracker.get_active_session(user_id)
        skip_topic_transition = False
        
        if active_clarification and llm_context_classifier_instance:
            # Use LLM with CoT to determine if this is a clarification answer or topic change
            last_question = getattr(active_clarification, 'questions', [''])[0] if active_clarification else ""
            original_query = getattr(active_clarification, 'original_query', "") if active_clarification else ""
            
            context_classification = llm_context_classifier_instance.classify_user_response(
                user_response=query_text,
                conversation_history=history,
                last_clarification_question=last_question,
                original_query=original_query
            )
            logger.info(f"🧠 LLM Context: {context_classification.classification} "
                       f"(confidence: {context_classification.confidence:.2f}) "
                       f"reasoning: {context_classification.reasoning[:100]}...")
            
            if context_classification.classification == "clarification_answer":
                # User is answering the clarification - skip topic transition
                skip_topic_transition = True
                logger.info("🎯 User is answering clarification - skipping topic transition")
            elif context_classification.classification == "topic_change":
                # User wants to switch topics - gracefully abandon clarification
                logger.info("🔄 User wants to switch topics - abandoning clarification gracefully")
                clarification_tracker.abandon_session(user_id)
                topic_acknowledgment = "No problem, let me help you with that instead."
        
        if not skip_topic_transition and len(history) > 0:
            # Get last user message
            last_user_messages = [m for m in history if m.get("role") == "user"]
            if last_user_messages:
                last_query = last_user_messages[-1].get("content", "")
                topic_transition = topic_change_detector_instance.detect_transition(
                    previous_query=last_query,
                    current_query=query_text,
                    conversation_history=history
                )
                logger.info(f"🔄 Topic transition: {topic_transition}")

                # Add acknowledgment if topic changed
                if topic_transition.changed and topic_transition.acknowledgment:
                    # Store acknowledgment to prepend to response later
                    topic_acknowledgment = topic_transition.acknowledgment

        # 3. Update conversation state machine
        conversation_state_machine_instance.transition_to_answering(user_id)
        current_state = conversation_state_machine_instance.get_state(user_id)
        logger.info(f"🎯 Conversation state: {current_state}")

        # === NEW: Check if this is a general conversational query (not knowledge-based) ===
        # Use LLM-based classification instead of hardcoded patterns
        general_response = general_query_handler_instance.handle_query(
            query=query_text,
            conversation_history=history,
            confidence_threshold=0.7
        )

        if general_response is not None:
            # This is a general conversational query - respond directly without RAG
            log_request(request_id, "💬 GENERAL_QUERY", {
                "query": query_text,
                "bypassed_rag": True
            })

            total_elapsed = (datetime.now() - start_time).total_seconds()

            # Save to conversation history
            conv_manager.add_message(user_id, "user", query_text, {
                "request_id": request_id,
                "query_type": "general_conversational"
            })

            conv_manager.add_message(user_id, "assistant", general_response, {
                "request_id": request_id,
                "query_type": "general_conversational",
                "elapsed_sec": round(total_elapsed, 3)
            })

            log_request(request_id, "✅ GENERAL_QUERY_COMPLETE", {
                "elapsed_sec": round(total_elapsed, 3),
                "response_length": len(general_response)
            })

            # Return response directly
            return QueryResponse(
                response=format_gfm_to_html(general_response),
                metadata={
                    "request_id": request_id,
                    "query_type": "general_conversational",
                    "bypassed_rag": True,
                    "elapsed_sec": round(total_elapsed, 3)
                }
            )

        # === If not general query, proceed with normal RAG flow ===
        log_request(request_id, "🤖 DEEP_AGENT_START", {"query": query_text})

        # Check for active clarification session FIRST (before rewriting)
        active_session = clarification_tracker.get_active_session(user_id)

        # Check if this is actually a clarification answer or a new question
        is_clarification = active_session and clarification_tracker.is_clarification_response(user_id, query_text)

        if is_clarification:
            # User is answering a clarifying question - don't rewrite, use original query
            logger.info(f"User {user_id} is answering clarification question")
            rewritten_query = query_text  # Use original query for clarification handler
        else:
            # This is a new question - abandon any active clarification session
            if active_session:
                clarification_tracker.abandon_session(user_id)
                logger.info(f"Abandoned clarification session for {user_id} - new question detected: '{query_text[:50]}'")

            # Normal flow - rewrite query with history
            rewritten_query = rewrite_query_with_history(history, query_text, user_id)
        
        if rewritten_query != query_text:
            log_request(request_id, "🔄 DEEP_QUERY_REWRITE", {
                "original": query_text,
                "rewritten": rewritten_query
            })

        # Extract previous assistant response for FORMAT path
        previous_response = ""
        original_user_query = ""
        if history:
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    previous_response = msg.get("content", "")
                    break
            # Extract original user query (the one before the preference question was asked)
            # This is the second-to-last user message if the last assistant message was a preference question
            if "Which type would you prefer" in previous_response:
                user_messages = [m for m in history if m.get("role") == "user"]
                if len(user_messages) >= 1:
                    original_user_query = user_messages[-1].get("content", "")

        # Initial state used rewritten query for better routing and retrieval
        initial_state = {
            "original_query": rewritten_query,
            "user_id": user_id,
            "complexity": "SIMPLE",
            "sub_queries": [],
            "sub_answers": [],
            "final_answer": "",
            "previous_response": previous_response,
            "sources": [],
            "images": [],  # Multimodal images
            # Clarification flow fields
            "clarifying_questions": [],
            "awaiting_clarification": False,
            "user_responses": [],
            "rag_context_for_clarification": "",
            "original_user_query": original_user_query,
            # Greeting detection fields
            "is_greeting": False,  # Initialize to False, will be set by greeting_detection_node
            "greeting_type": None,
            # Optimization layer data
            "user_profile": user_profile,  # Pass user context to RAG system
            "topic_acknowledgment": topic_acknowledgment  # Topic transition acknowledgment
        }
        
        # Invoke LangGraph
        result = await deep_agent_app.ainvoke(initial_state)
        answer_text = result.get("final_answer", "No answer generated.")
        complexity = result.get("complexity", "UNKNOWN")
        
        # Cleanup: Complete clarification session if turn 3 was finished
        if result.get("clarification_turn_3_complete"):
            session_id = result.get("clarification_session_id")
            if session_id:
                # Extract user_id from session_id (format: user_id_timestamp)
                user_id_from_session = session_id.rsplit("_", 2)[0] if "_" in session_id else user_id
                clarification_tracker.complete_session(user_id_from_session)
                # Mark clarification as completed in state machine (for golden rule enforcement)
                conversation_state_machine.mark_clarification_done(user_id_from_session)
                conversation_state_machine.transition_to_answering(user_id_from_session)
                logger.info(f"Completed clarification session for {user_id_from_session} after turn 3")
        
        # Log & Save History
        total_elapsed = (datetime.now() - start_time).total_seconds()
        
        log_request(request_id, "🤖 DEEP_AGENT_END", {
            "elapsed_sec": round(total_elapsed, 3),
            "complexity": complexity,
            "sub_queries": len(result.get("sub_queries", [])),
            "response_length": len(answer_text)
        })

        # Update persistent conversation history
        # Mark new questions (not clarification responses) as original questions
        is_clarification_answer = clarification_tracker.get_active_session(user_id) and \
                                 clarification_tracker.is_clarification_response(user_id, query_text)
        # Get conversation history for context-aware greeting detection
        is_obvious_greeting = is_greeting_or_casual(query_text, history)
        is_obvious_greeting = is_greeting_or_casual(query_text)

        metadata = {"request_id": request_id}
        if not is_clarification_answer and not is_obvious_greeting:
            # This is a new question - mark it as the original question
            metadata["is_original_question"] = True

        conv_manager.add_message(user_id, "user", query_text, metadata)

        # Assess answer quality using LLM classifier (zero hardcoding approach)
        sources = result.get("sources", [])
        
        # Build context string from sources for confidence assessment
        context_parts = []
        for source in sources[:5]:  # Use top 5 sources for context
            source_name = source.get("source", "Unknown")
            text_content = source.get("text", "") or source.get("content", "")
            if text_content:
                context_parts.append(f"Source: {source_name}\nContent: {text_content[:300]}")
        context_str = "\n\n".join(context_parts) if context_parts else "No context available"
        
        # Use LLM classifier for confidence assessment
        confidence_result = None
        if llm_classifier_instance:
            try:
                confidence_result = llm_classifier_instance.assess_answer_confidence(
                    query=query_text,
                    answer=answer_text,
                    sources=sources,
                    context=context_str
                )
                logger.info(f"📊 LLM Confidence Assessment: {confidence_result.confidence_level.value} "
                           f"({confidence_result.confidence_score:.0%}) - {confidence_result.reasoning[:100]}")
            except Exception as e:
                logger.error(f"Error in LLM confidence assessment: {e}")
                # Fallback to basic confidence
                confidence_result = None
        
        # Fallback to AnswerQuality if LLM classifier not available or failed
        if confidence_result is None:
            graphiti_facts = []  # Will be populated if Graphiti is used
            quality_assessment = AnswerQuality.assess_answer(
                answer_text,
                sources,
                graphiti_facts,
                query_text
            )
            # Convert to confidence_result format for consistency
            confidence_level_str = quality_assessment["confidence"]["level"]
            if confidence_level_str == "high":
                conf_level = ConfidenceLevel.HIGH
            elif confidence_level_str == "low":
                conf_level = ConfidenceLevel.LOW
            else:
                conf_level = ConfidenceLevel.MEDIUM
            confidence_result = AnswerConfidenceResult(
                confidence_level=conf_level,
                confidence_score=quality_assessment["confidence"]["score"],
                source_quality="good" if quality_assessment["grounding"]["is_grounded"] else "fair",
                has_sufficient_context=True,
                reasoning="Fallback assessment using AnswerQuality"
            )

        # === NEW: Enhance response for natural conversation ===
        # Get conversation context
        conv_context = conversational_excellence_instance.get_or_create_context(
            user_id=user_id,
            conversation_history=history
        )

        # Enhance the response to be more natural, contextual, and conversational
        enhancement = conversational_excellence_instance.enhance_response(
            original_response=answer_text,
            user_query=query_text,
            context=conv_context,
            metadata={
                "confidence": confidence_result.confidence_score,
                "sources": sources,
                "complexity": complexity
            }
        )

        # Use enhanced response
        final_answer = enhancement.enhanced_response

        # Prepend topic acknowledgment if topic changed
        if topic_acknowledgment:
            final_answer = f"{topic_acknowledgment}\n\n{final_answer}"
            logger.info(f"📝 Prepended topic acknowledgment: {topic_acknowledgment}")

        # Update context
        conversational_excellence_instance.update_context_from_interaction(
            user_query=query_text,
            response=final_answer,
            context=conv_context
        )

        logger.info(f"Response enhanced: {len(enhancement.improvements_made)} improvements made")

        # Format answer with confidence display and source references using LLM classifier
        if llm_classifier_instance and confidence_result:
            final_answer_with_confidence = llm_classifier_instance.format_answer_with_confidence(
                answer=final_answer,
                confidence=confidence_result,
                sources=sources
            )
        else:
            # Fallback: manual formatting if LLM classifier not available
            confidence_level = confidence_result.confidence_level.value if confidence_result else "medium"
            confidence_score = confidence_result.confidence_score if confidence_result else 0.5
            
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
                source_names = ["Knowledge Base"]
            source_display = ", ".join(source_names) if source_names else "General Knowledge Base"
            
            confidence_footer = "\n\n---\n"
            if confidence_level == "high":
                confidence_footer += f"📊 **Confidence:** HIGH ({confidence_score:.0%})\n"
            elif confidence_level == "medium":
                confidence_footer += f"📊 **Confidence:** MEDIUM ({confidence_score:.0%})\n"
            else:
                confidence_footer += f"⚠️ **Confidence:** LOW ({confidence_score:.0%}) - Information may be incomplete\n"
            
            confidence_footer += f"📚 **Sources:** {source_display}\n"
            if confidence_level == "low":
                confidence_footer += "💡 **Tip:** Consider contacting HR for verification\n"
            
            final_answer_with_confidence = final_answer + confidence_footer

        # Save assistant response with quality metadata
        conv_manager.add_message(
            user_id,
            "assistant",
            final_answer_with_confidence,  # Use response with confidence footer
            {
                "request_id": request_id,
                "complexity": complexity,
                "confidence": {
                    "level": confidence_result.confidence_level.value if confidence_result else "medium",
                    "score": confidence_result.confidence_score if confidence_result else 0.5,
                    "source_quality": confidence_result.source_quality if confidence_result else "fair",
                    "reasoning": confidence_result.reasoning if confidence_result else ""
                },
                "conversational_enhancements": enhancement.improvements_made
            }
        )

        # Async save to graphiti
        asyncio.create_task(save_to_graphiti_memory(user_id, query_text, answer_text))
        
        metadata = {
                "request_id": request_id,
                "agent": "LangGraph Decomposition",
                "complexity": complexity,
                "sub_queries": result.get("sub_queries", []),
            "sources": sources,
            "elapsed_sec": round(total_elapsed, 3),
            "quality": {
                "confidence": confidence_result.confidence_level.value if confidence_result else "medium",
                "confidence_score": confidence_result.confidence_score if confidence_result else 0.5,
                "source_quality": confidence_result.source_quality if confidence_result else "fair",
                "has_sufficient_context": confidence_result.has_sufficient_context if confidence_result else True,
                "should_show_warning": confidence_result.should_show_warning if confidence_result else False,
                "warning_message": confidence_result.warning_message if confidence_result else None
            }
        }
        
        return QueryResponse(
            response=format_gfm_to_html(final_answer_with_confidence),
            metadata=metadata
        )
        
    except Exception as e:
        log_request(request_id, "❌ DEEP_AGENT_ERROR", {"error": str(e)}, level="error")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Parlant-Compatible Endpoint (Simple Schema)
# ---------------------------------------------------------------------
class ParlantQueryRequest(BaseModel):
    """Minimal request schema for Parlant compatibility - no Optional types."""
    query: str

class ParlantQueryResponse(BaseModel):
    """Minimal response schema for Parlant compatibility."""
    answer: str
    sources: str

@app.post("/parlant_query", response_model=ParlantQueryResponse, operation_id="ask_knowledge_base")
async def parlant_query_endpoint(request: ParlantQueryRequest):
    """
    Query the Azadea Knowledge Base.
    Use this tool to find answers about HR policies, procedures, and company guidelines.
    
    Args:
        query: The question to ask (e.g. 'What is the maternity leave policy in Lebanon?')
    
    Returns:
        answer: The response from the knowledge base
        sources: List of document sources used
    """
    # Call the main query logic internally
    internal_request = QueryRequest(query=request.query, user_id="parlant_user")
    result = await query_endpoint(internal_request)
    
    # Flatten sources to a simple string for Parlant
    sources_list = result.metadata.get("sources", [])
    sources_str = ", ".join([s.get("source", "") for s in sources_list if isinstance(s, dict)]) if sources_list else "No specific sources"
    
    return ParlantQueryResponse(
        answer=result.response,
        sources=sources_str
    )

# ---------------------------------------------------------------------
# Streaming Endpoint (Optional - maintains compatibility)
# ---------------------------------------------------------------------
@app.post("/query/stream")
async def query_stream_endpoint(request: QueryRequest):
    """
    Streaming version of /query endpoint for progressive response delivery.
    Maintains same request format, streams response tokens.
    """
    async def generate() -> AsyncGenerator[str, None]:
        request_id = str(uuid.uuid4())[:8]
        try:
            query_text = request.query.strip()
            user_id = request.user_id or "default_user"
            
            # Get history and rewrite query
            history = get_user_history(user_id)
            rewritten_query = rewrite_query_with_history(history, query_text)
            
            # Extract previous response
            previous_response = ""
            original_user_query = ""
            if history:
                for msg in reversed(history):
                    if msg.get("role") == "assistant":
                        previous_response = msg.get("content", "")
                        break
                if "Which type would you prefer" in previous_response:
                    user_messages = [m for m in history if m.get("role") == "user"]
                    if len(user_messages) >= 1:
                        original_user_query = user_messages[-1].get("content", "")
            
            # Initial state
            initial_state = {
                "original_query": rewritten_query,
                "user_id": user_id,
                "complexity": "SIMPLE",
                "sub_queries": [],
                "sub_answers": [],
                "final_answer": "",
                "previous_response": previous_response,
                "sources": [],
                "images": [],
                "clarifying_questions": [],
                "awaiting_clarification": False,
                "user_responses": [],
                "rag_context_for_clarification": "",
                "original_user_query": original_user_query
            }
            
            # Invoke LangGraph
            result = await deep_agent_app.ainvoke(initial_state)
            answer_text = result.get("final_answer", "No answer generated.")
            
            # Stream response in chunks
            chunk_size = 50  # Characters per chunk
            for i in range(0, len(answer_text), chunk_size):
                chunk = answer_text[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'token', 'text': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)  # Small delay for streaming effect
            
            # Send final metadata
            sources = result.get("sources", [])
            quality_assessment = AnswerQuality.assess_answer(
                answer_text, sources, [], query_text
            )
            
            final_metadata = {
                "type": "done",
                "metadata": {
                    "request_id": request_id,
                    "complexity": result.get("complexity", "UNKNOWN"),
                    "sources": sources,
                    "quality": {
                        "confidence": quality_assessment["confidence"]["level"],
                        "confidence_score": quality_assessment["confidence"]["score"]
                    }
                }
            }
            yield f"data: {json.dumps(final_metadata, ensure_ascii=False)}\n\n"
            
            # Save to conversation history
            conv_manager.add_message(user_id, "user", query_text, {"request_id": request_id})
            conv_manager.add_message(user_id, "assistant", answer_text, {"request_id": request_id})
            
        except Exception as e:
            error_msg = json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False)
            yield f"data: {error_msg}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup Graphiti connection on shutdown."""
    global graphiti_instance
    if graphiti_instance:
        try:
            await graphiti_instance.close()
            print("✅ Graphiti connection closed")
        except Exception:
            pass
        graphiti_instance = None

if __name__ == "__main__":
    import uvicorn
    # Using port 8060 to avoid conflicts
    uvicorn.run(app, host="0.0.0.0", port=8060)
