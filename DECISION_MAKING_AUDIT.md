# Decision-Making Audit - LLM + CoT + History Usage

**Date:** 2026-01-08  
**Goal:** Verify all decision-making uses LLM with CoT reasoning and conversation history

## ✅ Using LLM Classifier (With CoT + History)

### 1. **Greeting Detection**
- ✅ `is_greeting_or_casual()` - Uses `llm_classifier.classify_query()` with history
- ✅ `greeting_detection_node()` - Uses LLM classifier primarily
- ⚠️ **Issue:** Still has hardcoded "obvious_greetings" fast path before LLM

### 2. **Clarification Response Detection**
- ✅ `clarification_tracker.is_clarification_response()` - Uses `llm_classifier.classify_query()` with full context
- ❌ **Issue:** `clarification_handler.is_clarification_answer()` still uses hardcoded patterns

### 3. **User Profile Extraction**
- ✅ `user_profile_tracker.extract_from_text()` - Uses `llm_classifier.detect_user_profile_info()` with history
- ✅ All calls pass conversation history

### 4. **Frustration Detection**
- ✅ `clarification_handler.detect_frustration()` - Uses `llm_classifier.detect_frustration()` with history
- ✅ All calls pass conversation history

### 5. **Answer Confidence Assessment**
- ✅ `llm_classifier.assess_answer_confidence()` - Uses LLM with CoT reasoning
- ✅ Integrated in query endpoint

## ❌ NOT Using LLM Classifier (Still Hardcoded)

### 1. **Topic Change Detection** ⚠️ CRITICAL
**Location:** `topic_change_detector.py`
- ❌ Uses keyword matching (`_detect_topic_keywords()`) with hardcoded `hr_topics` dictionary
- ❌ Uses semantic similarity (embeddings) but not LLM reasoning
- ✅ **Available:** `llm_classifier.detect_topic_change()` exists but NOT used
- **Used in:** `rag_server.py:2709` - `topic_change_detector_instance.detect_transition()`

**Should be:** Using `llm_classifier.detect_topic_change()` with conversation history

### 2. **Clarification Answer Detection (Handler)**
**Location:** `clarification_handler.py:258` - `is_clarification_answer()`
- ❌ Uses hardcoded `new_question_starters`, `greeting_patterns`
- ❌ Uses word count limits
- ✅ **Available:** `llm_classifier.classify_query()` exists but NOT used here

**Should be:** Using `llm_classifier.classify_query()` with clarification context

### 3. **Greeting Detection Fast Path**
**Location:** `rag_server.py:1163-1181` - `greeting_detection_node()`
- ⚠️ Has hardcoded "obvious_greetings" list checked BEFORE LLM
- ⚠️ Hardcoded greeting type detection: `any(g in query_lower for g in ["hi", "hello", "hey", "good"])`
- **Impact:** LLM is bypassed for obvious cases (but this might be intentional for performance)

### 4. **Greeting Response Node**
**Location:** `rag_server.py:1288-1310` - `greeting_response_node()`
- ❌ Uses hardcoded checks: `if query_lower in ["hi", "hello", "hey"]`
- ❌ Hardcoded responses for different greeting types
- **Note:** This is response generation, not classification, so might be acceptable

### 5. **Pattern Matcher** (Fallback Only)
**Location:** `pattern_matcher.py`
- ⚠️ Still has hardcoded patterns
- ✅ **Status:** Used only as fallback when LLM unavailable
- **Acceptable:** Fallback is fine, but should verify it's not primary path

## 📊 Summary

### ✅ Fully LLM-Based (5/8)
1. Greeting detection (main path)
2. Clarification response detection (tracker)
3. User profile extraction
4. Frustration detection
5. Answer confidence assessment

### ⚠️ Partially LLM-Based (1/8)
1. Greeting detection (has fast path before LLM)

### ❌ Not Using LLM (2/8)
1. **Topic change detection** - Uses keyword matching + embeddings (not LLM)
2. **Clarification answer detection (handler)** - Uses hardcoded patterns

## 🎯 Recommendations

### High Priority
1. **Replace topic_change_detector with LLM classifier**
   - Use `llm_classifier.detect_topic_change()` instead of keyword matching
   - Pass conversation history for context
   - Get CoT reasoning for topic changes

2. **Replace clarification_handler.is_clarification_answer() with LLM**
   - Use `llm_classifier.classify_query()` with clarification context
   - Remove hardcoded patterns

### Medium Priority
3. **Consider removing greeting fast path**
   - Let LLM handle all greetings for consistency
   - Or keep fast path but document it's for performance only

### Low Priority
4. **Greeting response generation**
   - Current hardcoded responses might be acceptable
   - Could enhance with LLM for more natural responses

## 🔍 Verification Checklist

- [x] Greeting detection uses LLM (with fast path)
- [x] Clarification tracker uses LLM
- [ ] Clarification handler uses LLM (needs update)
- [x] User profile extraction uses LLM
- [x] Frustration detection uses LLM
- [x] Confidence assessment uses LLM
- [ ] Topic change detection uses LLM (needs update)
- [x] All methods pass conversation history

## 📝 Next Steps

1. Update `topic_change_detector` to use LLM classifier
2. Update `clarification_handler.is_clarification_answer()` to use LLM
3. Test all decision points with conversation history
4. Verify CoT reasoning is provided for all decisions
