# Graphiti History Usage Analysis

## Summary
Graphiti history is **retrieved** but **NOT fully utilized** in the workflow nodes. The context is passed to the state but nodes don't access it.

---

## ✅ WHERE GRAPHITI HISTORY IS USED

### 1. **Context Retrieval** (`enhance_query_with_graphiti_context()`)
- **Location**: `rag_server.py:877-920`
- **What it does**: Retrieves 3 types of Graphiti context in parallel:
  - User profile (`get_user_context_from_graphiti`)
  - Related conversations (`search_conversation_history_graphiti`)
  - Temporal flow (`get_temporal_conversation_flow`)
- **Status**: ✅ **WORKING**

### 2. **Endpoint Integration** (`/query` and `/query/stream`)
- **Location**: `rag_server.py:3282-3476` (query), `3886-4067` (stream)
- **What it does**: 
  - Calls `enhance_query_with_graphiti_context()` before processing
  - Merges Graphiti user profile with `user_profile_tracker`
  - Passes Graphiti context to `initial_state`:
    ```python
    "graphiti_context": graphiti_context,
    "graphiti_related_conversations": graphiti_context.get('related_conversations', []),
    "graphiti_temporal_flow": graphiti_context.get('temporal_flow', {})
    ```
- **Status**: ✅ **WORKING** (retrieval and passing)

### 3. **User Profile Merging**
- **Location**: `rag_server.py:3302-3303`, `3906-3907`
- **What it does**: Merges Graphiti user profile into `user_profile_tracker`
- **Status**: ✅ **WORKING**

---

## ❌ WHERE GRAPHITI HISTORY IS NOT USED (BUT SHOULD BE)

### 1. **AgentState Definition** ⚠️
- **Location**: `rag_server.py:1698-1720`
- **Issue**: Graphiti fields are NOT in the TypedDict definition
- **Impact**: Type checking won't catch missing fields, nodes may not know they exist
- **Fix Needed**: Add to `AgentState`:
  ```python
  graphiti_context: Optional[Dict[str, Any]]
  graphiti_related_conversations: Optional[List[Dict[str, Any]]]
  graphiti_temporal_flow: Optional[Dict[str, Any]]
  ```

### 2. **Workflow Nodes - NO ACCESS** ❌ **CRITICAL**
- **Issue**: **NONE of the workflow nodes access Graphiti context from state**
- **Affected Nodes**:
  - `greeting_detection_node` - Doesn't use Graphiti context
  - `greeting_response_node` - Doesn't use Graphiti context
  - `simple_rag_node` - Doesn't use Graphiti context
  - `decomposer_node` - Doesn't use Graphiti context
  - `executor_node` - Doesn't use Graphiti context
  - `synthesizer_node` - Doesn't use Graphiti context
  - `format_handler_node` - Doesn't use Graphiti context
  - `clarifier_node` - Doesn't use Graphiti context
  - `clarification_answer_handler_node` - Doesn't use Graphiti context
  - `doc_preference_handler_node` - Doesn't use Graphiti context
  - `answer_relevance_node` - Doesn't use Graphiti context

- **What Should Happen**: Nodes should access `state.get("graphiti_context")` and use it in:
  - **Answer generation prompts** - Include related conversations and user profile
  - **Query understanding** - Use temporal flow for context
  - **Personalization** - Use user profile for tailored responses

### 3. **Query Rewriting** (`rewrite_query_with_history()`)
- **Location**: `rag_server.py:1022-1095`
- **Issue**: Only uses `get_user_history()` from conversation_manager, not Graphiti
- **Impact**: Missing rich context from Graphiti (related conversations, temporal patterns)
- **Fix Needed**: Pass Graphiti context to query rewriting:
  ```python
  def rewrite_query_with_history(history, latest_query, user_id, graphiti_context=None):
      # Use graphiti_context.get('related_conversations') for better context
      # Use graphiti_context.get('temporal_flow') for temporal understanding
  ```

### 4. **LLM Classifier Calls**
- **Locations**: Multiple places in `rag_server.py`
- **Issue**: LLM classifiers receive `conversation_history` but NOT Graphiti context
- **Affected Functions**:
  - `classify_query()` - Line 1777
  - `is_greeting_or_casual()` - Line 2927
  - `detect_user_profile_info()` - Line 3297
  - `detect_topic_change()` - Line 3348
  - `detect_frustration()` - Line 3366
  - `assess_answer_confidence()` - Line 3579, 4151
- **Fix Needed**: Pass Graphiti context to LLM classifiers:
  ```python
  result = llm_classifier.classify_query(
      query=query,
      conversation_context=conversation_history,
      graphiti_context=graphiti_context,  # ADD THIS
      active_clarification=False
  )
  ```

### 5. **Answer Generation Prompts**
- **Location**: All answer generation nodes (`simple_rag`, `synthesizer`, `format_handler`, etc.)
- **Issue**: Prompts don't include Graphiti context (related conversations, user profile, temporal flow)
- **Impact**: Answers are not personalized or context-aware from Graphiti memory
- **Fix Needed**: Include Graphiti context in system/user prompts:
  ```python
  # In simple_rag_node, synthesizer_node, etc.
  graphiti_context = state.get("graphiti_context", {})
  related_convs = graphiti_context.get('related_conversations', [])
  user_profile = graphiti_context.get('user_profile', {})
  
  system_prompt = f"""You are a helpful HR assistant.
  User Profile: {user_profile}
  Related Past Conversations: {related_convs}
  ...
  """
  ```

### 6. **Clarification Handlers**
- **Location**: `clarifier_node`, `clarification_answer_handler_node`
- **Issue**: Don't use Graphiti context for better clarification questions
- **Impact**: Clarification questions are generic, not personalized
- **Fix Needed**: Use Graphiti user profile and past conversations to ask better questions

### 7. **General Query Handler**
- **Location**: `general_query_handler.py`
- **Issue**: Doesn't receive or use Graphiti context
- **Impact**: Conversational responses are not personalized
- **Fix Needed**: Pass Graphiti context to `generate_conversational_response()`

### 8. **Topic Change Detection**
- **Location**: `rag_server.py:3348`
- **Issue**: Uses `conversation_history` but not Graphiti temporal flow
- **Impact**: Topic changes detected only from recent history, not long-term patterns
- **Fix Needed**: Use `graphiti_temporal_flow` for better topic change detection

### 9. **Frustration Detection**
- **Location**: `rag_server.py:3366`
- **Issue**: Uses `conversation_history` but not Graphiti context
- **Impact**: Missing patterns from past conversations
- **Fix Needed**: Include Graphiti related conversations in frustration analysis

### 10. **Answer Confidence Assessment**
- **Location**: `rag_server.py:3579`, `4151`
- **Issue**: Uses `conversation_history` but not Graphiti context
- **Impact**: Confidence assessment doesn't consider past successful/unsuccessful patterns
- **Fix Needed**: Include Graphiti context in confidence assessment

---

## 🔧 RECOMMENDED FIXES (Priority Order)

### **Priority 1: CRITICAL - Make Nodes Use Graphiti Context**
1. **Add Graphiti fields to AgentState TypedDict**
2. **Update answer generation nodes** to include Graphiti context in prompts:
   - `simple_rag_node`
   - `synthesizer_node`
   - `format_handler_node`
   - `doc_preference_handler_node`

### **Priority 2: HIGH - Enhance LLM Classifiers**
3. **Update LLM classifier calls** to include Graphiti context:
   - `classify_query()`
   - `is_greeting_or_casual()`
   - `detect_topic_change()`
   - `detect_frustration()`
   - `assess_answer_confidence()`

### **Priority 3: MEDIUM - Improve Query Processing**
4. **Update `rewrite_query_with_history()`** to use Graphiti context
5. **Update clarification handlers** to use Graphiti context
6. **Update general query handler** to use Graphiti context

---

## 📊 CURRENT USAGE SUMMARY

| Component | Graphiti Used? | Status |
|-----------|---------------|--------|
| Context Retrieval | ✅ Yes | Working |
| State Passing | ✅ Yes | Working |
| User Profile Merging | ✅ Yes | Working |
| AgentState Definition | ❌ No | Missing fields |
| Workflow Nodes | ❌ No | **CRITICAL GAP** |
| Query Rewriting | ❌ No | Should use |
| LLM Classifiers | ❌ No | Should use |
| Answer Generation | ❌ No | **CRITICAL GAP** |
| Clarification | ❌ No | Should use |
| Topic Detection | ❌ No | Should use |
| Frustration Detection | ❌ No | Should use |
| Confidence Assessment | ❌ No | Should use |

---

## 🎯 CONCLUSION

**Graphiti history is retrieved and passed to the state, but it's essentially unused.** The workflow nodes don't access it, so all the rich context (related conversations, user profile, temporal flow) is wasted.

**The biggest gap**: Answer generation nodes should use Graphiti context to provide personalized, context-aware responses based on past conversations and user profile.
