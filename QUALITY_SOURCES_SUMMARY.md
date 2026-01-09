# Quality Calculation & Source Display - Summary

## 📊 Quality Calculation

### How It Works:

1. **Primary Method: LLM-Based Assessment**
   - Uses `llm_classifier.assess_answer_confidence()`
   - LLM evaluates with Chain of Thought reasoning:
     - Does answer address the question?
     - Is answer well-supported by sources?
     - Is there missing information?
     - Should user be warned?
   
2. **Returns:**
   - `confidence_level`: high/medium/low
   - `confidence_score`: 0.0-1.0 (percentage)
   - `source_quality`: excellent/good/fair/poor
   - `has_sufficient_context`: true/false
   - `missing_info`: List of missing items
   - `should_show_warning`: true/false
   - `warning_message`: Warning text
   - `reasoning`: Step-by-step CoT explanation

3. **Fallback:** Rule-based scoring if LLM unavailable

### Quality Factors (LLM Considers):
- Answer relevance to question
- Source support quality
- Completeness of information
- Missing critical information
- Need for warnings

## 📚 Source Display - FIXED ✅

### Previous Issue:
- Only showed top 3 sources
- After deduplication, often only 1 source shown
- Multiple chunks from same document → only 1 reference

### Fixed Implementation:
- ✅ Shows **top 5 unique sources** (increased from 3)
- ✅ Sorted by **score** (best sources first)
- ✅ Checks **top 10 sources** for diversity
- ✅ Removes duplicates intelligently
- ✅ Better representation of information sources

### Code Changes:

**Before:**
```python
source_names = list(set([
    s.get("source", "Unknown").replace(".md", "")
    for s in sources[:3]  # Only top 3
]))
```

**After:**
```python
# Sort by score, get top 5 unique sources
sorted_sources = sorted(sources, key=lambda x: x.get("score", 0), reverse=True)
seen = set()
for s in sorted_sources[:10]:  # Check top 10 for diversity
    source_name = s.get("source", "Unknown").replace(".md", "").strip()
    if source_name and source_name not in seen:
        source_names.append(source_name)
        seen.add(source_name)
        if len(source_names) >= 5:  # Top 5 unique
            break
```

### Result:
- **Before:** 1-2 sources shown (often just 1)
- **After:** Up to 5 unique sources shown
- Better representation of information diversity
- Sources sorted by relevance score

## 🎯 Example

**Query:** "What is the maternity leave policy?"

**Retrieved Sources:**
1. HRD - GEN - 004 - Maternity Leave - P - 13.md (score: 0.95)
2. HRD - GEN - 004 - Maternity Leave - P - 13.md (score: 0.92) - Same doc
3. HRD - GEN - 004 - Maternity Leave - P - 13.md (score: 0.88) - Same doc
4. HRD - GEN - 001 - Annual Leave - P - 19.md (score: 0.75)
5. HRD - GEN - 006 - Employee Leaves - P - 15.md (score: 0.70)

**Before Fix:**
- Sources: "HRD - GEN - 004 - Maternity Leave - P - 13" (only 1)

**After Fix:**
- Sources: "HRD - GEN - 004 - Maternity Leave - P - 13, HRD - GEN - 001 - Annual Leave - P - 19, HRD - GEN - 006 - Employee Leaves - P - 15" (3 unique sources)

## ✅ Status

- ✅ Quality calculation: LLM-based with CoT reasoning
- ✅ Source display: Fixed to show up to 5 unique sources
- ✅ Sources sorted by relevance score
- ✅ Better diversity representation
