# RAG Server Enhanced

This folder contains an enhanced version of the RAG server with best practices improvements.

## Files

- `rag_server.py` - Main RAG server (enhanced version)
- `azure_doc_intelligence_qdrant.py` - Retrieval logic
- `qdrant_storage.py` - Qdrant storage utilities
- `semantic_chunk.py` - Semantic chunking utilities
- `conversation_manager.py` - **NEW**: Persistent conversation storage with Redis fallback
- `resilience.py` - **NEW**: Retry logic, circuit breakers, and error handling
- `answer_quality.py` - **NEW**: Answer grounding verification and confidence scoring

## API Compatibility

**IMPORTANT**: All changes maintain backward compatibility with the frontend. The API endpoints and response formats remain the same:

- `POST /query` - Same request/response format (enhanced with quality metadata)
- `POST /reset` - Same format
- `GET /health` - Same format
- `POST /parlant_query` - Same format
- `POST /query/stream` - **NEW**: Streaming endpoint for progressive response delivery

## Enhancements Implemented

### 1. Persistent Conversation Management ✅
- **File**: `conversation_manager.py`
- **Features**:
  - Redis-backed persistent storage (falls back to in-memory if Redis unavailable)
  - Conversation history persists across server restarts
  - Automatic TTL (30 days default)
  - History size limits (100 messages per user)

### 2. Answer Quality Assessment ✅
- **File**: `answer_quality.py`
- **Features**:
  - Confidence scoring (HIGH/MEDIUM/LOW/UNCERTAIN)
  - Answer grounding verification
  - Detects ungrounded claims
  - Quality metadata included in responses

### 3. Resilience & Error Handling ✅
- **File**: `resilience.py`
- **Features**:
  - Exponential backoff retries for external services
  - Circuit breakers for Qdrant, Graphiti, and LLM
  - Timeout handling
  - Graceful degradation when services fail

### 4. Streaming Support ✅
- **New Endpoint**: `POST /query/stream`
- **Features**:
  - Progressive response delivery (like ChatGPT)
  - Server-Sent Events (SSE) format
  - Same request format as `/query`
  - Optional - frontend can choose to use it or not

## Configuration

### Environment Variables

Add these optional variables to your `.env`:

```bash
# Redis (optional - falls back to in-memory if not set)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
CONVERSATION_TTL_DAYS=30

# Existing variables still work
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
QDRANT_URL=...
GRAPHITI_ENABLED=true
```

## Running

```bash
cd rag_server_enhanced
python rag_server.py
```

The server will run on port 8060 (same as original) to maintain compatibility.

## Response Format Changes

The `/query` endpoint now includes additional metadata (non-breaking):

```json
{
  "response": "<html formatted answer>",
  "metadata": {
    "request_id": "...",
    "agent": "LangGraph Decomposition",
    "complexity": "SIMPLE",
    "sources": [...],
    "elapsed_sec": 1.234,
    "quality": {                    // NEW
      "confidence": "high",          // NEW
      "confidence_score": 0.85,    // NEW
      "is_grounded": true           // NEW
    }
  }
}
```

Frontend can ignore the new `quality` field if not needed - it's purely additive.

## Dependencies

No new required dependencies! The enhancements use:
- `redis` (optional) - Only needed if you want persistent storage
- All existing dependencies remain the same

If Redis is not installed, the system gracefully falls back to in-memory storage.

## Testing

To test the enhanced server:

1. **Test persistent storage** (if Redis is available):
   ```bash
   # Send a query
   curl -X POST http://localhost:8060/query -d '{"query": "test", "user_id": "test_user"}'
   
   # Restart server
   # Send another query - history should persist
   ```

2. **Test streaming**:
   ```bash
   curl -X POST http://localhost:8060/query/stream \
     -H "Content-Type: application/json" \
     -d '{"query": "What is the leave policy?", "user_id": "test"}'
   ```

3. **Test error resilience**:
   - Temporarily stop Qdrant
   - Send a query - should handle gracefully with circuit breaker

## Next Steps (Future Enhancements)

- Multi-level caching (L1/L2/L3)
- Query expansion and intent classification
- Dynamic prompts with few-shot examples
- Entity tracking across conversations
- User feedback collection
- Comprehensive observability

