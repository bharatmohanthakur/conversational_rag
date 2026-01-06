# Performance Analysis: Why Deep Search Takes 30 Seconds

## Current Bottlenecks

### 1. **Reranking (5-10 seconds)**
- **Location**: `reranker.py` line 164-170
- **Operation**: LLM call to score 15 documents in batches of 10
- **Time**: ~5-10 seconds per batch
- **Impact**: High - happens on every search

### 2. **Corrective RAG Evaluation (3-5 seconds)**
- **Location**: `rag_server.py` line 941
- **Operation**: LLM call to evaluate retrieval quality
- **Time**: ~3-5 seconds
- **Impact**: Medium - only when enabled

### 3. **Graphiti Search (2-5 seconds)**
- **Location**: `rag_server.py` line 933
- **Operation**: Graphiti memory search with embeddings
- **Time**: ~2-5 seconds
- **Impact**: Medium - happens on every search

### 4. **Qdrant Search (1-2 seconds)**
- **Location**: `rag_server.py` line 788-798
- **Operation**: Vector search in Qdrant
- **Time**: ~1-2 seconds
- **Impact**: Low - relatively fast

### 5. **Sequential Processing**
- All operations run sequentially, not in parallel
- Total time = sum of all operations

## Time Breakdown (Typical)

```
Qdrant Search:           1-2 seconds
Filename Embedding:      0.5-1 second
Reranking (LLM):         5-10 seconds  ⚠️ SLOWEST
Graphiti Search:         2-5 seconds
Corrective RAG (LLM):    3-5 seconds   ⚠️ SLOW
Contextual Compression:  2-3 seconds (if needed)
─────────────────────────────────────────────
Total:                   15-28 seconds
```

## Optimization Options

### Option 1: Disable Advanced RAG for Faster Response
```python
# In rag_server.py, set use_advanced_rag=False
result = await run_search_for_deep_agent(query, user_id, use_advanced_rag=False)
```
**Impact**: Reduces time from 30s to ~5-8s
**Trade-off**: Lower quality results

### Option 2: Make Reranking Optional/Faster
- Use simple keyword-based reranking instead of LLM
- Only use LLM reranking for complex queries
- Cache reranking results

### Option 3: Parallelize Operations
- Run Qdrant and Graphiti searches in parallel
- Run reranking and corrective RAG in parallel (if independent)

### Option 4: Reduce LLM Calls
- Skip corrective RAG for simple queries
- Use faster model for reranking (gpt-4o-mini)
- Cache evaluation results

## Recommended Quick Fix

For faster response times, you can disable advanced RAG techniques:

```python
# In clarifier_node and clarification_answer_handler_node
search_result = await run_search_for_deep_agent(query, user_id, use_advanced_rag=False)
```

This will:
- Skip reranking (saves 5-10 seconds)
- Skip corrective RAG (saves 3-5 seconds)
- Skip contextual compression (saves 2-3 seconds)
- **Total time: ~5-8 seconds instead of 30 seconds**

