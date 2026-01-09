# Impact of Removing Reranker

**Date:** 2026-01-08  
**Analysis:** What happens if we disable/remove reranking

## 🔍 What Reranking Currently Does

### Purpose
Reranking improves document relevance by:
1. **Re-scoring documents** using LLM-based cross-encoder approach
2. **Re-ordering results** based on semantic relevance to the query
3. **Combining signals**: 60% rerank score + 40% original vector search score
4. **Selecting top-k** most relevant documents (top 7)

### Current Implementation
- **Location:** `reranker.py` → `_cross_encoder_rerank()`
- **Process:** 
  - Takes 15 documents from Qdrant search
  - Processes in batches of 10
  - LLM scores each document (0.0-1.0) for query relevance
  - Combines with original vector search scores
  - Returns top 7 documents
- **Time:** 5-10 seconds (30-50% of total response time)

## ✅ What Happens If We Remove Reranking

### Current Fallback Behavior (Already Implemented)

The code **already has a fallback** when reranking is disabled:

```python
# Line 996-1010 in rag_server.py
if use_advanced_rag and reranker and len(documents_for_rerank) > 0:
    # Reranking happens here (5-10s)
    ranked_docs = await loop.run_in_executor(
        None,
        lambda: reranker.rerank(query, documents_for_rerank, original_scores)
    )
    top_results = ranked_docs[:7]
else:
    # FALLBACK: Simple ranking by combined score
    ranked_results = list(zip(original_scores, documents_for_rerank))
    ranked_results.sort(key=lambda x: x[0], reverse=True)
    top_results = [{"content": doc["content"], ...} for ... in ranked_results[:7]]
```

### Fallback Ranking Method

**Without reranking, documents are ranked by:**
```
combined_score = content_score + (filename_boost × 0.3)
```

Where:
- **content_score**: Vector similarity score from Qdrant (0.0-1.0)
- **filename_boost**: Keyword match in filename (0.0-1.0) × 0.3

**Example:**
- Document A: content_score=0.85, filename_boost=0.2 → combined=0.91
- Document B: content_score=0.80, filename_boost=0.5 → combined=0.95 ✅ (ranks higher)

## 📊 Impact Analysis

### ✅ **POSITIVE IMPACTS**

#### 1. **Speed Improvement** ⚡
- **Time Saved:** 5-10 seconds per query
- **Percentage:** 30-50% faster responses
- **Current Average:** 16.10s → **New Average:** ~8-11s
- **GENERIC Queries:** 22.93s → **~13-17s** (25-40% faster)
- **SIMPLE Queries:** 17.74s → **~10-13s** (30-40% faster)

#### 2. **Cost Reduction** 💰
- **Fewer LLM API calls:** 1 less LLM call per query
- **Token savings:** ~500-1000 tokens per query (document scoring)
- **Cost:** ~$0.001-0.002 per query saved

#### 3. **Reduced Complexity** 🎯
- Simpler code path
- Fewer failure points (no JSON parsing errors from reranking)
- Less error handling needed

### ⚠️ **NEGATIVE IMPACTS**

#### 1. **Potential Quality Degradation** 📉

**When reranking helps most:**
- **Ambiguous queries:** "leave policy" could match many documents
- **Semantic mismatch:** Vector search finds similar words, but not relevant context
- **Multi-topic queries:** "maternity leave in Lebanon" needs precise matching
- **Context-dependent queries:** "my insurance" needs user-specific context

**Example scenarios where reranking improves results:**

**Query:** "Can I extend my maternity leave?"
- **Without reranking:** Might return general leave policy documents
- **With reranking:** Prioritizes maternity-specific extension documents

**Query:** "What happens if my sick leave balance is over?"
- **Without reranking:** Might return general sick leave policy
- **With reranking:** Prioritizes documents about exceeding balance limits

#### 2. **Less Accurate Relevance Scoring**

**Vector search limitations:**
- Based on embedding similarity (semantic similarity)
- May rank documents with similar words but different context highly
- Doesn't understand query intent as well as LLM

**Reranking advantages:**
- LLM understands query intent and context
- Can identify subtle relevance differences
- Better at handling synonyms and paraphrasing

#### 3. **Filename Dependency**

**Without reranking:**
- More reliance on filename keyword matching
- Documents with matching filenames get boosted
- May miss relevant documents with different filenames

## 🎯 When Reranking Matters Most

### High Impact (Reranking Helps Significantly):
1. **Complex queries** with multiple concepts
2. **Ambiguous queries** that could match many documents
3. **Context-dependent queries** requiring understanding
4. **Queries with synonyms** or paraphrasing
5. **Multi-part questions** needing precise matching

### Low Impact (Reranking Less Critical):
1. **Simple, specific queries** with clear keywords
2. **Queries with unique terms** that match few documents
3. **Well-structured knowledge base** with clear document organization
4. **High-quality vector embeddings** that already capture relevance well

## 💡 Recommendations

### Option 1: **Conditional Reranking** (Recommended) ⭐

**Only rerank when needed:**
```python
# Skip reranking for simple queries or high-confidence retrievals
should_rerank = (
    query_complexity == "COMPLEX" or
    avg_retrieval_score < 0.7 or
    len(documents) > 10
)

if should_rerank and reranker:
    # Rerank (5-10s)
else:
    # Use fallback (instant)
```

**Benefits:**
- Fast for simple queries (8-11s)
- Accurate for complex queries (13-17s)
- Best of both worlds

### Option 2: **Disable Reranking Completely**

**Set `use_advanced_rag=False` or `reranker=None`:**

**Pros:**
- ✅ 30-50% faster (5-10s saved)
- ✅ Lower costs
- ✅ Simpler code

**Cons:**
- ⚠️ May get less relevant documents for complex queries
- ⚠️ Quality degradation for ambiguous queries
- ⚠️ More reliance on vector search quality

**Best for:**
- Simple, well-structured knowledge bases
- Queries with clear, specific keywords
- When speed is more important than perfect relevance

### Option 3: **Faster Reranking Alternative**

**Use keyword-based reranking instead of LLM:**
```python
# In reranker.py, set use_cross_encoder=False
reranker = Reranker(..., use_cross_encoder=False)
```

**Benefits:**
- Still reranks (improves relevance)
- Much faster (~0.5-1s instead of 5-10s)
- No LLM calls needed

**Trade-off:**
- Less accurate than LLM reranking
- But better than no reranking

## 📈 Expected Performance After Removal

### Current Performance:
- **Average:** 16.10s
- **GENERIC:** 22.93s
- **SIMPLE:** 17.74s
- **CLARIFICATION:** 8.16s

### After Removing Reranking:
- **Average:** ~8-11s (30-50% faster) ⚡
- **GENERIC:** ~13-17s (25-40% faster)
- **SIMPLE:** ~10-13s (30-40% faster)
- **CLARIFICATION:** ~6-8s (minimal change, already fast)

### Quality Impact:
- **Simple queries:** Minimal quality loss (5-10%)
- **Complex queries:** Moderate quality loss (10-20%)
- **Ambiguous queries:** Higher quality loss (15-25%)

## 🔧 Implementation Steps

### To Disable Reranking:

**Method 1: Set flag in code**
```python
# In rag_server.py, line 840
result = await run_search_for_deep_agent(query, user_id, use_advanced_rag=False)
```

**Method 2: Set reranker to None**
```python
# In get_enhanced_components()
_reranker = None  # Disable reranking
```

**Method 3: Conditional reranking**
```python
# In _retrieve_single_query(), line 997
should_rerank = (
    use_advanced_rag and 
    reranker and 
    len(documents_for_rerank) > 0 and
    query_complexity in ["COMPLEX", "GENERIC"]  # Only for complex queries
)

if should_rerank:
    # Rerank
else:
    # Use fallback
```

## 📝 Summary

### Removing Reranking:

**✅ Pros:**
- 30-50% faster (5-10s saved)
- Lower costs
- Simpler code

**⚠️ Cons:**
- Potential quality loss (5-25% depending on query)
- Less accurate for complex/ambiguous queries
- More reliance on vector search quality

### Recommendation:

**Use conditional reranking:**
- Fast for simple queries (skip reranking)
- Accurate for complex queries (use reranking)
- Best balance of speed and quality

**Or disable completely if:**
- Speed is critical
- Knowledge base is well-structured
- Queries are typically simple and specific
- You can accept 10-20% quality trade-off
