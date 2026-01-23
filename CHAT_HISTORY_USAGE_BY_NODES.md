# Chat History Usage by Nodes

## Summary
This document shows which workflow nodes and functions currently use chat history and how they access it.

---

## ✅ NODES THAT USE CHAT HISTORY

### 1. **greeting_detection_node** ✅
- **Location**: `rag_server.py:1729-1841`
- **How it accesses history**:
  ```python
  history = get_user_history(user_id, use_summarization=False)
  conversation_history = history[-5:]  # Last 5 messages
  ```
- **How it uses history**:
  - Passes to `llm_classifier.classify_query()` with `conversation_context=conversation_history`
  - Used for context-aware greeting detection (distinguishes greetings from HR queries)
  - Also used in fallback `is_greeting_or_casual()` function
- **Purpose**: Better greeting detection based on conversation context

---

### 2. **greeting_response_node** ✅
- **Location**: `rag_server.py:1844-1942`
- **How it accesses history**:
  ```python
  history = get_user_history(user_id, use_summarization=False)
  conversation_history = history[-10:]  # Last 10 messages
  ```
- **How it uses history**:
  - Builds conversation context string from last 5 messages
  - Includes in LLM prompt for personalized greeting responses
  - Example: "Recent conversation history:\n{context_str}"
- **Purpose**: Generate personalized, context-aware greeting responses
- **Example**: If user asked questions before, acknowledge continuity naturally

---

### 3. **answer_relevance_node** ✅
- **Location**: `rag_server.py:3040-3056`
- **How it accesses history**:
  ```python
  history = get_user_history(user_id, use_summarization=False)
  conversation_history = history[-5:]  # Last 5 messages
  ```
- **How it uses history**:
  - Passes to `is_greeting_or_casual()` to check if query is greeting/casual
  - Used to determine if clarification should be preserved or refined
  - If greeting detected, refines response to appropriate greeting (not clarification)
- **Purpose**: Ensure greetings get greeting responses, not clarification questions

---

## ✅ PRE-PROCESSING FUNCTIONS THAT USE CHAT HISTORY

### 4. **rewrite_query_with_history()** ✅
- **Location**: `rag_server.py:1022-1095`
- **How it accesses history**:
  - Receives `history` as parameter (from `get_user_history()`)
  - Filters out greetings/casual messages
  - Uses last 10 messages: `history[-10:]`
- **How it uses history**:
  - Extracts original question from conversation history
  - Builds history string for LLM prompt
  - Uses LLM to rewrite query to be standalone based on context
- **Purpose**: Make queries standalone by incorporating conversation context
- **Called from**: `/query` and `/query/stream` endpoints before processing

---

### 5. **is_greeting_or_casual()** ✅
- **Location**: `rag_server.py:2916-2930`
- **How it accesses history**:
  - Receives `conversation_history` as optional parameter
- **How it uses history**:
  - Passes to `llm_classifier.classify_query()` with `conversation_context=conversation_history`
  - Used for context-aware greeting detection
- **Purpose**: Determine if query is greeting/casual based on context
- **Called from**: Multiple places (greeting_detection_node, answer_relevance_node)

---

## ✅ ENDPOINT-LEVEL USAGE (Before Nodes)

### 6. **`/query` endpoint** ✅
- **Location**: `rag_server.py:3239-3580`
- **How it accesses history**:
  ```python
  history = get_user_history(user_id)
  ```
- **How it uses history**:
  1. **Query Rewriting**: `rewritten_query = rewrite_query_with_history(history, query_text, user_id)`
  2. **User Profile Tracking**: `user_profile_tracker.update_from_query(..., conversation_history=history)`
  3. **Topic Change Detection**: `topic_change_detector.detect_transition(..., conversation_history=history)`
  4. **LLM Context Classification**: `llm_context_classifier.classify_user_response(..., conversation_history=history)`
  5. **General Query Handler**: `general_query_handler.handle_query(..., conversation_history=history)`
  6. **Answer Confidence**: `llm_classifier.assess_answer_confidence(..., conversation_history=history)`
  7. **Graphiti Context**: `enhance_query_with_graphiti_context(..., conversation_history=history)`
  8. **Extract previous response**: Loops through history to find last assistant message
  9. **Extract original user query**: Extracts from history if preference question was asked

---

### 7. **`/query/stream` endpoint** ✅
- **Location**: `rag_server.py:3168-4160`
- **How it accesses history**:
  ```python
  history = get_user_history(user_id)
  ```
- **How it uses history**:
  - **Same as `/query` endpoint** (all 9 uses listed above)
  - Used identically for all pre-processing steps

---

## ❌ NODES THAT DO NOT USE CHAT HISTORY

### 1. **router_node** ❌
- **Location**: `rag_server.py:1960-1987`
- **Status**: Does NOT access history
- **Impact**: Routing decisions are made without conversation context
- **Should use**: History to better understand query intent and route appropriately

---

### 2. **simple_rag_node** ❌
- **Location**: `rag_server.py:1995-2095`
- **Status**: Does NOT access history
- **Impact**: Answer generation is generic, not personalized
- **Should use**: History for:
  - Personalized responses based on past interactions
  - Better understanding of follow-up questions
  - Context-aware answer generation

---

### 3. **decomposer_node** ❌
- **Location**: `rag_server.py:2101-2109`
- **Status**: Does NOT access history
- **Impact**: Query decomposition doesn't consider past conversation patterns
- **Should use**: History to understand what sub-questions were asked before

---

### 4. **executor_node** ❌
- **Location**: `rag_server.py:2112-2145`
- **Status**: Does NOT access history
- **Impact**: Sub-query execution doesn't use conversation context
- **Should use**: History for context-aware sub-query processing

---

### 5. **synthesizer_node** ❌
- **Location**: `rag_server.py:2148-2170`
- **Status**: Does NOT access history
- **Impact**: Answer synthesis is generic, not personalized
- **Should use**: History for:
  - Personalized synthesis based on user preferences
  - Better integration of past conversation context
  - Context-aware answer formatting

---

### 6. **format_handler_node** ❌
- **Location**: `rag_server.py:2173-2187`
- **Status**: Does NOT access history
- **Impact**: Formatting doesn't consider user preferences from past interactions
- **Should use**: History to understand user's preferred format/style

---

### 7. **clarifier_node** ❌
- **Location**: `rag_server.py:2194-2411`
- **Status**: Does NOT access history
- **Impact**: Clarification questions are generic, not personalized
- **Should use**: History for:
  - Better clarification questions based on past patterns
  - Understanding what user has asked before
  - Personalized clarification approach

---

### 8. **clarification_answer_handler_node** ❌
- **Location**: `rag_server.py:2414-2520`
- **Status**: Does NOT access history
- **Impact**: Clarification processing doesn't use conversation context
- **Should use**: History to better understand clarification answers in context

---

### 9. **doc_preference_handler_node** ❌
- **Location**: `rag_server.py:2538-2582`
- **Status**: Does NOT access history
- **Impact**: Document preference handling doesn't consider past preferences
- **Should use**: History to infer user preferences from past interactions

---

## 📊 SUMMARY TABLE

| Node/Function | Uses History? | How It Accesses | How It Uses | Priority to Add |
|---------------|--------------|-----------------|-------------|-----------------|
| **greeting_detection_node** | ✅ Yes | `get_user_history()` | LLM classifier context | - |
| **greeting_response_node** | ✅ Yes | `get_user_history()` | Personalized prompts | - |
| **answer_relevance_node** | ✅ Yes | `get_user_history()` | Greeting detection | - |
| **rewrite_query_with_history()** | ✅ Yes | Parameter | Query rewriting | - |
| **is_greeting_or_casual()** | ✅ Yes | Parameter | Greeting detection | - |
| **`/query` endpoint** | ✅ Yes | `get_user_history()` | 9 different uses | - |
| **`/query/stream` endpoint** | ✅ Yes | `get_user_history()` | 9 different uses | - |
| **router_node** | ❌ No | - | - | Medium |
| **simple_rag_node** | ❌ No | - | - | **HIGH** |
| **decomposer_node** | ❌ No | - | - | Low |
| **executor_node** | ❌ No | - | - | Low |
| **synthesizer_node** | ❌ No | - | - | **HIGH** |
| **format_handler_node** | ❌ No | - | - | Medium |
| **clarifier_node** | ❌ No | - | - | **HIGH** |
| **clarification_answer_handler_node** | ❌ No | - | - | Medium |
| **doc_preference_handler_node** | ❌ No | - | - | Medium |

---

## 🔍 HOW HISTORY IS ACCESSED

### Pattern 1: Direct Call to `get_user_history()`
```python
history = get_user_history(user_id, use_summarization=False)
conversation_history = history[-5:]  # Last N messages
```

**Used by**:
- `greeting_detection_node`
- `greeting_response_node`
- `answer_relevance_node`
- Endpoints (`/query`, `/query/stream`)

### Pattern 2: Passed as Parameter
```python
def some_function(..., conversation_history: List[Dict[str, str]]):
    # Use conversation_history
```

**Used by**:
- `rewrite_query_with_history(history, ...)`
- `is_greeting_or_casual(query, conversation_history)`
- LLM classifier calls: `classify_query(..., conversation_context=conversation_history)`
- Various tracker/classifier methods

### Pattern 3: From State (NOT CURRENTLY USED)
```python
# This pattern is NOT used, but SHOULD be:
history = state.get("conversation_history", [])
```

**Should be used by**: All workflow nodes that need history

---

## 🎯 KEY FINDINGS

1. **Only 3 workflow nodes use history directly**:
   - `greeting_detection_node`
   - `greeting_response_node`
   - `answer_relevance_node`

2. **Most history usage is at endpoint level** (before nodes):
   - Query rewriting
   - User profile tracking
   - Topic change detection
   - LLM classifications

3. **Answer generation nodes don't use history**:
   - `simple_rag_node` - Generic answers
   - `synthesizer_node` - Generic synthesis
   - `format_handler_node` - No personalization

4. **Clarification nodes don't use history**:
   - `clarifier_node` - Generic questions
   - `clarification_answer_handler_node` - No context awareness

5. **History is NOT passed in state**:
   - Nodes would need to call `get_user_history()` themselves
   - This is inefficient (multiple calls) and inconsistent

---

## 🚀 RECOMMENDATIONS

### **Priority 1: Pass History in State**
Add `conversation_history` to `AgentState` and pass it from endpoints:
```python
class AgentState(TypedDict):
    # ... existing fields ...
    conversation_history: List[Dict[str, str]]  # ADD THIS
```

### **Priority 2: Update Answer Generation Nodes**
Make `simple_rag_node` and `synthesizer_node` use history for personalized responses:
```python
async def simple_rag_node(state: AgentState):
    conversation_history = state.get("conversation_history", [])
    # Include in prompts for personalized answers
```

### **Priority 3: Update Clarification Nodes**
Make `clarifier_node` use history for better questions:
```python
async def clarifier_node(state: AgentState):
    conversation_history = state.get("conversation_history", [])
    # Use to generate personalized clarification questions
```

---

## 📝 CONCLUSION

**Current State**:
- History is used at endpoint level for pre-processing (9 different uses)
- Only 3 workflow nodes use history directly
- Answer generation nodes don't use history (major gap)
- History is not passed in state (inefficient)

**Impact**:
- Answers are generic, not personalized
- Clarification questions are not context-aware
- Follow-up questions may not be understood properly
- User preferences are not considered in responses

**Fix**:
- Pass history in `AgentState`
- Update all answer generation nodes to use history
- Update clarification nodes to use history
- Consider passing history to all nodes that need context
