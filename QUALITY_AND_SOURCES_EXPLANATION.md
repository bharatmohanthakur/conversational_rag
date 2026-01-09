# Quality Calculation & Source Display Explanation

## 📊 How Quality is Calculated

### Current Implementation: LLM-Based with CoT Reasoning

**Location:** `llm_classifier.py:assess_answer_confidence()`

The quality/confidence is calculated using **LLM with Chain of Thought reasoning**:

```python
confidence_result = llm_classifier.assess_answer_confidence(
    query=query_text,
    answer=answer_text,
    sources=sources,
    context=context_str
)
```

### Quality Assessment Process:

1. **LLM Evaluation** (with CoT):
   - ✅ Does the answer directly address the question?
   - ✅ Is the answer well-supported by the sources?
   - ✅ Is there any missing critical information?
   - ✅ Should the user be warned about anything?

2. **LLM Returns:**
   - `confidence_level`: "high" | "medium" | "low"
   - `confidence_score`: 0.0-1.0 (percentage)
   - `source_quality`: "excellent" | "good" | "fair" | "poor"
   - `has_sufficient_context`: true/false
   - `missing_info`: List of missing information
   - `should_show_warning`: true/false
   - `warning_message`: Warning text if needed
   - `reasoning`: Step-by-step CoT reasoning

3. **Fallback** (if LLM unavailable):
   - Uses `AnswerQuality.assess_answer()` with rule-based scoring
   - Based on: retrieval scores, source diversity, uncertainty phrases

### Quality Calculation Factors:

**LLM-Based (Primary):**
- Answer relevance to question
- Source support quality
- Completeness assessment
- Missing information detection

**Rule-Based (Fallback):**
- Average retrieval score (60%)
- Source diversity (20%)
- Answer mentions sources (+10%)
- Uncertainty phrases (-50%)
- Both chunks and facts (+10%)

## 📚 Why Only One Reference is Shown

### Current Source Display Logic:

**Location:** `llm_classifier.py:format_answer_with_confidence()` (line 713-716)

```python
# Get unique source names
source_names = list(set([
    s.get("source", "Unknown").replace(".md", "")
    for s in sources[:3]  # Takes top 3 sources
])) if sources else ["General Knowledge Base"]
```

### The Issue:

1. **Takes top 3 sources** (`sources[:3]`)
2. **Deduplicates** using `set()` - removes duplicate source names
3. **Problem:** If all 3 sources are from the same document, only 1 unique name remains

### Example Scenario:

```python
sources = [
    {"source": "HRD - GEN - 004 - Maternity Leave - P - 13.md"},
    {"source": "HRD - GEN - 004 - Maternity Leave - P - 13.md"},  # Same doc, different chunk
    {"source": "HRD - GEN - 004 - Maternity Leave - P - 13.md"}   # Same doc, different chunk
]

# After deduplication:
source_names = ["HRD - GEN - 004 - Maternity Leave - P - 13"]  # Only 1!
```

### Why This Happens:

- Multiple chunks from the same document are retrieved
- All chunks have the same `source` field (document name)
- Deduplication removes duplicates, leaving only unique document names
- Result: Only 1 source shown even if 3 chunks were used

## 🔧 Solutions

### Option 1: Show More Sources (Increase Limit)
```python
# Show top 5 unique sources instead of 3
source_names = list(set([
    s.get("source", "Unknown").replace(".md", "")
    for s in sources[:5]  # Increased from 3 to 5
]))
```

### Option 2: Show Source Count
```python
# Show unique sources + count of chunks
unique_sources = list(set([...]))
source_count = len(sources)
source_display = f"{', '.join(unique_sources)} ({source_count} chunks)"
```

### Option 3: Show All Unique Sources (No Limit)
```python
# Show all unique sources, not just top 3
source_names = list(set([
    s.get("source", "Unknown").replace(".md", "")
    for s in sources  # All sources, not just [:3]
]))
```

### Option 4: Show Top Sources by Score
```python
# Sort by score and show top unique sources
sorted_sources = sorted(sources, key=lambda x: x.get("score", 0), reverse=True)
unique_sources = []
seen = set()
for s in sorted_sources:
    source_name = s.get("source", "Unknown").replace(".md", "")
    if source_name not in seen:
        unique_sources.append(source_name)
        seen.add(source_name)
        if len(unique_sources) >= 5:  # Top 5 unique
            break
```

## 📋 Current Behavior

**What's Happening:**
- System retrieves multiple chunks (often 5-7 chunks)
- Many chunks come from the same document
- Only unique document names are shown
- Result: 1-2 sources displayed even if 5+ chunks used

**Why It's Limited:**
- Code limits to top 3 sources: `sources[:3]`
- Deduplication removes duplicates
- If all 3 are from same doc → only 1 shown

## 🎯 Recommendation

**Best Solution:** Show top 5 unique sources with chunk count

```python
# Get top 5 unique sources
sorted_sources = sorted(sources, key=lambda x: x.get("score", 0), reverse=True)
unique_sources = []
seen = set()
for s in sorted_sources[:10]:  # Check top 10 for diversity
    source_name = s.get("source", "Unknown").replace(".md", "").replace("HRD - ", "").strip()
    if source_name not in seen:
        unique_sources.append(source_name)
        seen.add(source_name)
        if len(unique_sources) >= 5:  # Top 5 unique sources
            break

# Show sources with count
total_chunks = len(sources)
source_display = f"{', '.join(unique_sources)}"
if total_chunks > len(unique_sources):
    source_display += f" ({total_chunks} chunks)"
```

This would show:
- Top 5 unique document sources
- Total chunk count if more chunks than unique sources
- Better representation of information sources used
