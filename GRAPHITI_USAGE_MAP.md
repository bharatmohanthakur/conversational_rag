# Graphiti History Usage Map

## 🔍 Quick Reference: Where Graphiti is Used vs Not Used

### ✅ **USED** - Graphiti History is Retrieved and Passed

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Context Retrieval                                        │
│    Location: rag_server.py:877-920                          │
│    Function: enhance_query_with_graphiti_context()          │
│    ✅ Retrieves: user_profile, related_conversations,       │
│       temporal_flow                                         │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Endpoint Integration                                      │
│    Locations:                                                │
│    - /query endpoint (line 3282-3476)                       │
│    - /query/stream endpoint (line 3886-4067)                │
│    ✅ Calls enhance_query_with_graphiti_context()            │
│    ✅ Merges user_profile with user_profile_tracker         │
│    ✅ Passes to initial_state:                               │
│       - graphiti_context                                     │
│       - graphiti_related_conversations                       │
│       - graphiti_temporal_flow                               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. State Passing                                             │
│    ✅ Graphiti context is in initial_state                   │
│    ❌ BUT: AgentState TypedDict doesn't define these fields  │
└─────────────────────────────────────────────────────────────┘
```

---

### ❌ **NOT USED** - Graphiti History is Available But Ignored

```
┌─────────────────────────────────────────────────────────────┐
│ WORKFLOW NODES - None Access Graphiti Context               │
│                                                              │
│ ❌ greeting_detection_node (line 1729)                      │
│    - Only uses: query, user_id                               │
│    - Should use: graphiti_context for better greeting        │
│      detection based on past interactions                    │
│                                                              │
│ ❌ greeting_response_node (line 1843)                       │
│    - Only uses: query, conversation_history                  │
│    - Should use: graphiti_context for personalized          │
│      greetings based on user profile                        │
│                                                              │
│ ❌ simple_rag_node (line 1995)                              │
│    - Only uses: query, user_id, search_result               │
│    - Should use: graphiti_context in answer generation      │
│      prompts for personalized responses                      │
│                                                              │
│ ❌ decomposer_node (line 2101)                              │
│    - Only uses: query                                        │
│    - Should use: graphiti_context for better query           │
│      decomposition based on past patterns                    │
│                                                              │
│ ❌ executor_node (line 2112)                                │
│    - Only uses: sub_queries, user_id                         │
│    - Should use: graphiti_context for context-aware         │
│      sub-query execution                                     │
│                                                              │
│ ❌ synthesizer_node (line 2148)                             │
│    - Only uses: original_query, sub_answers                 │
│    - Should use: graphiti_context in synthesis prompt        │
│      for personalized, context-aware answers                 │
│                                                              │
│ ❌ format_handler_node (line 2173)                          │
│    - Only uses: query, previous_response                     │
│    - Should use: graphiti_context for user preference       │
│      based formatting                                        │
│                                                              │
│ ❌ clarifier_node (line 2194)                               │
│    - Only uses: query, user_id, search_result               │
│    - Should use: graphiti_context for better clarification  │
│      questions based on user profile and past conversations │
│                                                              │
│ ❌ clarification_answer_handler_node (line 2320)            │
│    - Only uses: query, user_id, state fields                │
│    - Should use: graphiti_context for context-aware          │
│      clarification processing                                │
│                                                              │
│ ❌ doc_preference_handler_node (line 2538)                  │
│    - Only uses: query, search_result                        │
│    - Should use: graphiti_context for user preference       │
│      inference from past interactions                        │
│                                                              │
│ ❌ answer_relevance_node (line 2600)                        │
│    - Only uses: final_answer, sources                       │
│    - Should use: graphiti_context for better relevance      │
│      assessment based on past successful patterns            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PRE-PROCESSING FUNCTIONS - Don't Use Graphiti              │
│                                                              │
│ ❌ rewrite_query_with_history() (line 1022)                 │
│    - Only uses: conversation_history from conversation_manager│
│    - Should use: graphiti_related_conversations for        │
│      better query rewriting                                  │
│                                                              │
│ ❌ is_greeting_or_casual() (line 2916)                      │
│    - Only uses: conversation_history                         │
│    - Should use: graphiti_context for better detection       │
│                                                              │
│ ❌ LLM Classifier Calls (multiple locations)                │
│    - classify_query() (line 1777)                           │
│    - detect_user_profile_info() (line 3297)                  │
│    - detect_topic_change() (line 3348)                       │
│    - detect_frustration() (line 3366)                        │
│    - assess_answer_confidence() (line 3579, 4151)           │
│    - All only use: conversation_history                      │
│    - Should use: graphiti_context for richer context         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Usage Statistics

| Category | Used | Not Used | Total |
|----------|------|----------|-------|
| **Context Retrieval** | ✅ 1 | ❌ 0 | 1 |
| **State Passing** | ✅ 1 | ❌ 0 | 1 |
| **Workflow Nodes** | ❌ 0 | ❌ 11 | 11 |
| **Pre-processing** | ❌ 0 | ❌ 3 | 3 |
| **LLM Classifiers** | ❌ 0 | ❌ 6 | 6 |
| **TOTAL** | ✅ 2 | ❌ 20 | 22 |

**Usage Rate: 9% (2/22 components use Graphiti)**

---

## 🎯 Critical Gaps

### **Gap 1: Answer Generation Nodes Don't Use Graphiti**
**Impact**: Answers are generic, not personalized based on:
- User profile from Graphiti
- Related past conversations
- Temporal conversation patterns

**Example Fix for `simple_rag_node`**:
```python
async def simple_rag_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # ✅ ADD THIS: Get Graphiti context
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    related_convs = graphiti_context.get("related_conversations", [])
    
    # Build personalized system prompt
    profile_text = f"User Profile: {user_profile}" if user_profile else ""
    related_text = "\n".join([f"- {c.get('fact', '')[:100]}" for c in related_convs[:3]])
    
    system_prompt = f"""You are a helpful HR assistant. {profile_text}
    
    Related Past Conversations:
    {related_text}
    
    Answer the user request based STRICTLY on the context provided...
    """
```

### **Gap 2: LLM Classifiers Don't Use Graphiti**
**Impact**: Classifications are based only on recent history, missing:
- Long-term user patterns
- Related conversation context
- Temporal flow patterns

**Example Fix for `classify_query()`**:
```python
result = llm_classifier.classify_query(
    query=query,
    conversation_context=conversation_history,
    graphiti_context=graphiti_context,  # ✅ ADD THIS
    active_clarification=False
)
```

### **Gap 3: Query Rewriting Doesn't Use Graphiti**
**Impact**: Query rewriting misses context from:
- Related past conversations
- Temporal patterns
- User profile preferences

**Example Fix**:
```python
def rewrite_query_with_history(history, latest_query, user_id, graphiti_context=None):
    # ✅ ADD: Use Graphiti related conversations
    if graphiti_context:
        related = graphiti_context.get('related_conversations', [])
        # Use related conversations for better context
```

---

## 🚀 Priority Fixes

1. **HIGH**: Add Graphiti fields to `AgentState` TypedDict
2. **CRITICAL**: Update answer generation nodes to use Graphiti context in prompts
3. **HIGH**: Update LLM classifiers to accept and use Graphiti context
4. **MEDIUM**: Update query rewriting to use Graphiti context
5. **MEDIUM**: Update clarification handlers to use Graphiti context

---

## 📝 Conclusion

**Graphiti history is retrieved and passed to the workflow, but it's completely unused by the nodes.** This is a significant missed opportunity for:
- Personalized responses
- Context-aware answer generation
- Better query understanding
- Improved user experience

**The fix is straightforward**: Nodes need to access `state.get("graphiti_context")` and use it in their prompts and logic.
