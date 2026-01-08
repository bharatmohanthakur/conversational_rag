# Integration Guide - Best-in-Class Enhancements

## Quick Start (5 minutes)

### Step 1: Import the Orchestrator

Add to top of `rag_server.py`:

```python
from conversation_orchestrator import ConversationOrchestrator, OrchestrationResult
```

### Step 2: Initialize in `get_enhanced_components()`

```python
def get_enhanced_components():
    global _conv_manager, _clarification_tracker, _conversation_summarizer
    global _self_evaluator, _adaptive_retriever, _quality_gate
    global _contextual_compressor, _reranker, _corrective_rag
    global _conversation_orchestrator  # ADD THIS

    if _conv_manager is None:
        # ... existing initialization ...

        # ADD THIS - Initialize orchestrator
        _conversation_orchestrator = ConversationOrchestrator(
            conversation_manager=_conv_manager,
            llm_client=aoai_client,
            embedder_client=aoai_client,  # Same client
            qdrant_client=qdrant_client,
            deployment_name=AZURE_CHAT_DEPLOYMENT,
            enable_analytics=True,
            enable_compression=True,
            enable_memory_rag=False  # Can enable later
        )
        logger.info("✅ Conversation Orchestrator initialized")

    return (_conv_manager, _clarification_tracker, _conversation_summarizer,
            _self_evaluator, _quality_gate, _adaptive_retriever,
            _contextual_compressor, _reranker, _corrective_rag,
            _conversation_orchestrator)  # ADD TO RETURN
```

### Step 3: Modify `query_endpoint()` to Use Orchestrator

```python
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    request_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()

    try:
        query_text = request.query.strip()
        user_id = request.user_id or "default_user"

        log_request(request_id, "🤖 QUERY_START", {"query": query_text})

        # Get enhanced components (including orchestrator)
        components = get_enhanced_components()
        orchestrator = components[-1]  # Last item

        # Get conversation history
        history = get_user_history(user_id)

        # === NEW: Process through orchestrator ===
        orchestration_result: OrchestrationResult = orchestrator.process_query(
            user_id=user_id,
            query=query_text,
            conversation_history=history,
            retrieval_results=None  # Will add after first retrieval
        )

        log_request(request_id, "🎯 ORCHESTRATION", {
            "original": query_text,
            "rewritten": orchestration_result.rewritten_query,
            "confidence": orchestration_result.confidence_score.overall if orchestration_result.confidence_score else None,
            "should_confirm": orchestration_result.should_confirm,
            "should_recover": orchestration_result.should_recover,
            "topic_switched": orchestration_result.topic_switched
        })

        # === Handle confirmation request ===
        if orchestration_result.should_confirm and orchestration_result.confirmation_request:
            confirmation = orchestration_result.confirmation_request

            # Return confirmation to user
            return QueryResponse(
                response=confirmation.message,
                metadata={
                    "request_id": request_id,
                    "awaiting_confirmation": True,
                    "confidence": confirmation.confidence_score,
                    "entities": confirmation.entities_summary
                }
            )

        # === Handle context recovery ===
        if orchestration_result.should_recover and orchestration_result.recovery_action:
            recovery = orchestration_result.recovery_action

            log_request(request_id, "⚠️ RECOVERY_TRIGGERED", {
                "action_type": recovery.action_type,
                "message": recovery.message[:100]
            })

            # Return recovery message to user
            return QueryResponse(
                response=recovery.message,
                metadata={
                    "request_id": request_id,
                    "recovery_triggered": True,
                    "recovery_type": recovery.action_type,
                    "suggested_query": recovery.suggested_query
                }
            )

        # === Use enhanced query for retrieval ===
        query_for_retrieval = orchestration_result.should_use_query

        # Existing retrieval and answer generation logic
        # (run_search_for_deep_agent, LangGraph, etc.)
        initial_state = {
            "original_query": query_for_retrieval,  # Use enhanced query
            "user_id": user_id,
            "complexity": "SIMPLE",
            # ... rest of state ...
        }

        result = await deep_agent_app.ainvoke(initial_state)
        answer_text = result.get("final_answer", "No answer generated.")

        # === Save to conversation history with enriched metadata ===
        conv_manager.add_message(
            user_id,
            "user",
            query_text,
            {
                "request_id": request_id,
                "is_original_question": not orchestration_result.conversation_context or
                                       orchestration_result.conversation_context.turn_count == 1,
                "confidence": orchestration_result.confidence_score.overall if orchestration_result.confidence_score else None,
                "intent_relationship": orchestration_result.intent_analysis.relationship.value if orchestration_result.intent_analysis else None
            }
        )

        conv_manager.add_message(
            user_id,
            "assistant",
            answer_text,
            {
                "request_id": request_id,
                "confidence": orchestration_result.confidence_score.overall if orchestration_result.confidence_score else None
            }
        )

        # === Finalize conversation (updates preferences, analytics) ===
        orchestrator.finalize_conversation(
            user_id=user_id,
            conversation_id=request_id,
            conversation_history=get_user_history(user_id),
            context=orchestration_result.conversation_context,
            final_feedback=None  # Can add if user provides feedback
        )

        total_elapsed = (datetime.now() - start_time).total_seconds()

        return QueryResponse(
            response=format_gfm_to_html(answer_text),
            metadata={
                "request_id": request_id,
                "confidence": orchestration_result.confidence_score.overall if orchestration_result.confidence_score else None,
                "entities_extracted": orchestration_result.conversation_context.get_all_entities(),
                "topic": orchestration_result.conversation_context.primary_topic,
                "elapsed_sec": round(total_elapsed, 3)
            }
        )

    except Exception as e:
        log_request(request_id, "❌ ERROR", {"error": str(e)}, level="error")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Step 4: Add Analytics Endpoint

```python
@app.get("/analytics/insights")
async def get_analytics_insights(time_period: str = "last_7d"):
    """Get conversation analytics insights."""
    components = get_enhanced_components()
    orchestrator = components[-1]

    insights = orchestrator.get_analytics_insights(time_period)
    return insights

@app.get("/analytics/user_profile/{user_id}")
async def get_user_profile_endpoint(user_id: str):
    """Get user profile and preferences."""
    components = get_enhanced_components()
    orchestrator = components[-1]

    profile = orchestrator.get_user_profile(user_id)
    return profile
```

---

## Step 5: Test the Integration

### Test 1: Basic Query
```bash
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the maternity leave policy?", "user_id": "test_user"}'
```

**Expected:**
- Query processed through orchestrator
- Context created with topic extracted
- Confidence scored
- Answer returned with metadata

### Test 2: Clarification Flow
```bash
# Turn 1
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the leave policy?", "user_id": "test_user2"}'

# Turn 2  (Answer clarification)
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "maternity leave", "user_id": "test_user2"}'

# Turn 3 (Another clarification)
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Lebanon", "user_id": "test_user2"}'
```

**Expected:**
- Turn 1: System may ask for clarification
- Turn 2: Context updated with "maternity leave"
- Turn 3: Context updated with "Lebanon"
- Final query: "What is the maternity leave policy in Lebanon?"
- Entities tracked: {policy_type: "maternity leave", country: "Lebanon"}

### Test 3: Topic Switch
```bash
# Turn 1
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the insurance policy?", "user_id": "test_user3"}'

# Turn 2 (Different topic)
curl -X POST http://localhost:8069/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What about vacation days?", "user_id": "test_user3"}'
```

**Expected:**
- Turn 1: Topic = "insurance policy"
- Turn 2: Topic switch detected → New context created
- No context bleed between topics

### Test 4: Analytics
```bash
curl http://localhost:8069/analytics/insights?time_period=last_24h
```

**Expected:**
```json
{
  "summary": {
    "total_conversations": 5,
    "avg_confidence": "0.82",
    "satisfaction_rate": "80.0%"
  },
  "concerns": [],
  "recommendations": [],
  "highlights": [
    "High user satisfaction: 80.0%"
  ]
}
```

---

## Configuration Options

### Enable/Disable Features

In `get_enhanced_components()`:

```python
_conversation_orchestrator = ConversationOrchestrator(
    conversation_manager=_conv_manager,
    llm_client=aoai_client,
    embedder_client=aoai_client,
    qdrant_client=qdrant_client,
    deployment_name=AZURE_CHAT_DEPLOYMENT,
    enable_analytics=True,      # Track metrics
    enable_compression=True,    # Compress long conversations
    enable_memory_rag=False     # Store in vector DB (requires setup)
)
```

### Adjust Confidence Thresholds

```python
# After initialization
_conversation_orchestrator.confidence_scorer.CONFIRM_THRESHOLD = 0.75  # Higher = fewer confirmations
_conversation_orchestrator.confidence_scorer.RECOVERY_THRESHOLD = 0.55  # Higher = less recovery
```

### Adjust Compression Settings

```python
_conversation_orchestrator.compressor.keep_recent_turns = 4  # Keep more recent context
_conversation_orchestrator.compressor.max_turns_before_compression = 10  # Compress later
```

---

## Monitoring

### Log Examples

You'll see logs like:

```
2026-01-08 10:15:23 | INFO | ContextManager | Created new context for user123: topic=maternity leave
2026-01-08 10:15:23 | INFO | IntentAnalyzer | Intent analysis: CONTINUATION, similarity=0.87
2026-01-08 10:15:23 | INFO | ConfidenceScorer | Confidence: 0.92 (VERY_HIGH)
2026-01-08 10:15:23 | INFO | ConversationOrchestrator | Query rewrite: 'Lebanon' → 'What is the maternity leave policy in Lebanon?'
```

### Low Confidence Warning

```
2026-01-08 10:20:15 | WARNING | ContextRecovery | Context recovery triggered for user456: confirm
```

---

## Troubleshooting

### Issue: Import errors

**Solution:**
```bash
# Ensure all files are in the same directory
ls -la conversation_*.py intent_*.py confidence_*.py user_preferences.py

# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"
```

### Issue: "No module named 'conversation_context'"

**Solution:**
```python
# In rag_server.py, add at top
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

### Issue: Embeddings taking too long

**Solution:**
```python
# Use smaller embedding model
intent_analyzer = SemanticIntentAnalyzer(
    embedder_client,
    embedding_model="text-embedding-3-small"  # Faster
)
```

### Issue: High memory usage

**Solution:**
```python
# Disable memory RAG if not needed
enable_memory_rag=False

# Clear embedding cache periodically
intent_analyzer._embedding_cache.clear()
```

---

## Performance Optimization

### 1. Cache Embeddings
Already implemented in `SemanticIntentAnalyzer._embedding_cache`

### 2. Async Processing
The orchestrator is sync but can be wrapped:

```python
import asyncio

async def process_query_async(...):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        orchestrator.process_query,
        user_id, query, history, None
    )
    return result
```

### 3. Parallel Component Initialization
Already optimized - components initialize only once

---

## Gradual Rollout Strategy

### Phase 1 (Week 1): Core Features
- Enable context tracking
- Enable intent analysis
- Enable confidence scoring
- **Disable** analytics, compression, memory RAG

```python
enable_analytics=False,
enable_compression=False,
enable_memory_rag=False
```

### Phase 2 (Week 2): Quality Features
- Enable analytics
- Monitor metrics
- Adjust confidence thresholds based on data

```python
enable_analytics=True,
enable_compression=False,
enable_memory_rag=False
```

### Phase 3 (Week 3): Efficiency Features
- Enable compression
- Monitor token savings

```python
enable_analytics=True,
enable_compression=True,
enable_memory_rag=False
```

### Phase 4 (Week 4): Advanced Features
- Enable memory RAG (if needed)
- Fine-tune all parameters

```python
enable_analytics=True,
enable_compression=True,
enable_memory_rag=True
```

---

## Success Metrics

Track these metrics to measure success:

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| Context Loss Rate | 20% | <10% | Analytics API |
| Avg Confidence | 0.65 | >0.80 | Analytics API |
| User Satisfaction | 60% | >80% | Analytics API |
| Avg Turns/Conv | 4.5 | <3.5 | Analytics API |
| Token Usage | 100% | <70% | Monitor compression |

---

## Support

For issues or questions:
1. Check logs: `tail -f logs/rag_server.log | grep -E "Context|Intent|Confidence|Orchestrator"`
2. View analytics: `curl http://localhost:8069/analytics/insights`
3. Check user profile: `curl http://localhost:8069/analytics/user_profile/USER_ID`

---

## Next Steps

After integration:
1. ✅ Run test suite: `python3 test_csp_questions_multi_turn.py`
2. ✅ Monitor logs for 24 hours
3. ✅ Review analytics after 100 conversations
4. ✅ Adjust thresholds based on data
5. ✅ Enable additional features gradually

Good luck! 🚀
