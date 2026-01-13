# Plan: Integrate History and Graphiti in All Nodes

## 🎯 Objective
Make all workflow nodes use both conversation history and Graphiti context for personalized, context-aware responses.

---

## 📋 Current State Analysis

### ✅ What's Working
- Graphiti context is retrieved and passed to `initial_state`
- History is retrieved at endpoint level
- 3 nodes use history (greeting_detection, greeting_response, answer_relevance)
- Graphiti context is passed but NOT used by any nodes

### ❌ What's Missing
- History is NOT passed in `AgentState` (nodes call `get_user_history()` individually)
- Graphiti context is NOT typed in `AgentState`
- 9 workflow nodes don't use history
- 11 workflow nodes don't use Graphiti context
- No unified way to access both history and Graphiti

---

## 🚀 Implementation Plan

### **Phase 1: Update AgentState Definition** (Priority: CRITICAL)

#### Task 1.1: Add History and Graphiti Fields to AgentState
**File**: `rag_server.py` (line ~1698)

**Current**:
```python
class AgentState(TypedDict):
    original_query: str
    user_id: str
    complexity: Literal["SIMPLE", "COMPLEX", "FORMAT", "GENERIC", "DOC_PREFERENCE", "CLARIFICATION_ANSWER"]
    # ... other fields ...
    user_profile: Dict[str, Any]
    topic_acknowledgment: Optional[str]
```

**Change to**:
```python
class AgentState(TypedDict):
    original_query: str
    user_id: str
    complexity: Literal["SIMPLE", "COMPLEX", "FORMAT", "GENERIC", "DOC_PREFERENCE", "CLARIFICATION_ANSWER"]
    # ... other fields ...
    user_profile: Dict[str, Any]
    topic_acknowledgment: Optional[str]
    # ADD THESE:
    conversation_history: List[Dict[str, str]]  # Recent conversation history
    graphiti_context: Optional[Dict[str, Any]]  # Graphiti context (user profile, related conversations, temporal flow)
    graphiti_related_conversations: Optional[List[Dict[str, Any]]]  # Related past conversations
    graphiti_temporal_flow: Optional[Dict[str, Any]]  # Temporal conversation patterns
```

**Impact**: All nodes will have typed access to history and Graphiti context.

---

### **Phase 2: Update Endpoints to Pass History and Graphiti** (Priority: CRITICAL)

#### Task 2.1: Update `/query` Endpoint
**File**: `rag_server.py` (line ~3450)

**Current**:
```python
initial_state = {
    "original_query": rewritten_query,
    # ... other fields ...
    "user_profile": user_profile,
    "topic_acknowledgment": topic_acknowledgment,
    "graphiti_context": graphiti_context,
    "graphiti_related_conversations": graphiti_context.get('related_conversations', []),
    "graphiti_temporal_flow": graphiti_context.get('temporal_flow', {})
}
```

**Change to**:
```python
initial_state = {
    "original_query": rewritten_query,
    # ... other fields ...
    "user_profile": user_profile,
    "topic_acknowledgment": topic_acknowledgment,
    # ADD HISTORY:
    "conversation_history": history[-10:] if history else [],  # Last 10 messages
    # ENSURE GRAPHITI IS PASSED (already done, but ensure it's correct):
    "graphiti_context": graphiti_context,
    "graphiti_related_conversations": graphiti_context.get('related_conversations', []),
    "graphiti_temporal_flow": graphiti_context.get('temporal_flow', {})
}
```

#### Task 2.2: Update `/query/stream` Endpoint
**File**: `rag_server.py` (line ~4065)

**Same changes as Task 2.1**

**Impact**: All nodes will receive history and Graphiti context in state.

---

### **Phase 3: Update Answer Generation Nodes** (Priority: HIGH)

#### Task 3.1: Update `simple_rag_node`
**File**: `rag_server.py` (line ~1995)

**Current**: Doesn't use history or Graphiti

**Change to**:
```python
async def simple_rag_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    related_convs = state.get("graphiti_related_conversations", [])
    
    # Retrieve documents
    search_result = await run_search_for_deep_agent(query, user_id)
    context = search_result["context"]
    sources = search_result["sources"]
    retrieved_images = search_result.get("images", [])
    
    # BUILD PERSONALIZED SYSTEM PROMPT
    profile_text = ""
    if user_profile:
        profile_parts = [f"{k}: {v}" for k, v in user_profile.items() if v]
        profile_text = f"\n\nUser Profile: {', '.join(profile_parts)}"
    
    related_text = ""
    if related_convs:
        related_text = "\n\nRelated Past Conversations:\n"
        for i, conv in enumerate(related_convs[:3], 1):
            fact = conv.get("fact", "")[:150]
            related_text += f"{i}. {fact}...\n"
    
    # Build personalized system prompt
    if has_workflow and not has_normal:
        system_prompt = (f"You are a helpful HR assistant. The user's query matched WORKFLOW documents.{profile_text}{related_text}\n\n"
                        "Provide a detailed, structured answer following the workflow steps...")
    else:
        system_prompt = (f"You are a helpful HR assistant.{profile_text}{related_text}\n\n"
                        "Answer the user request based STRICTLY on the context provided...")
    
    # Include conversation history in messages
    messages = [("system", system_prompt)]
    
    # Add recent conversation history for context
    if conversation_history:
        for msg in conversation_history[-3:]:  # Last 3 messages
            if msg.get("role") in ["user", "assistant"]:
                messages.append((msg.get("role"), msg.get("content", "")))
    
    # Rest of the function...
```

**Impact**: Answers will be personalized based on user profile and past conversations.

---

#### Task 3.2: Update `synthesizer_node`
**File**: `rag_server.py` (line ~2148)

**Current**: Doesn't use history or Graphiti

**Change to**:
```python
async def synthesizer_node(state: AgentState):
    original_query = state["original_query"]
    sub_answers = state["sub_answers"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    related_convs = state.get("graphiti_related_conversations", [])
    
    combined_context = "\n\n".join(sub_answers)
    
    # BUILD PERSONALIZED PROMPT
    profile_text = f"\nUser Profile: {user_profile}" if user_profile else ""
    related_text = "\n".join([f"- {c.get('fact', '')[:100]}" for c in related_convs[:2]]) if related_convs else ""
    
    messages = [
        ("system", f"You are a helpful HR expert.{profile_text}\n\n"
                   f"Related Past Conversations:\n{related_text}\n\n"
                   "Synthesize the provided sub-answers into a cohesive final report..."),
        ("user", f"Original Request: {original_query}\n\n"
                f"Gathered Information: {combined_context}\n\n"
                f"Based STRICTLY on the information above, synthesize a comprehensive answer...")
    ]
    
    # Add conversation history
    if conversation_history:
        for msg in conversation_history[-3:]:
            if msg.get("role") in ["user", "assistant"]:
                messages.insert(-1, (msg.get("role"), msg.get("content", "")))
    
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content}
```

**Impact**: Synthesis will be personalized and context-aware.

---

#### Task 3.3: Update `format_handler_node`
**File**: `rag_server.py` (line ~2173)

**Current**: Doesn't use history or Graphiti

**Change to**:
```python
async def format_handler_node(state: AgentState):
    query = state["original_query"]
    previous_response = state.get("previous_response", "")
    
    # GET GRAPHITI FROM STATE
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    
    # Check user preferences from profile
    preferred_format = user_profile.get("preferred_format", None)  # e.g., "table", "bullet", "detailed"
    
    if not previous_response:
        return {"final_answer": "I don't have a previous response to reformat..."}
    
    format_hint = f"User prefers: {preferred_format}" if preferred_format else ""
    
    messages = [
        ("system", f"You are a helpful assistant. {format_hint}\n\n"
                   "The user wants you to reformat or re-present a previous response..."),
        ("user", f"Previous Response:\n{previous_response}\n\nUser Request: {query}")
    ]
    
    response = await agent_llm.ainvoke(messages)
    return {"final_answer": response.content}
```

**Impact**: Formatting will consider user preferences.

---

### **Phase 4: Update Clarification Nodes** (Priority: HIGH)

#### Task 4.1: Update `clarifier_node`
**File**: `rag_server.py` (line ~2194)

**Current**: Doesn't use history or Graphiti

**Change to**:
```python
async def clarifier_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    related_convs = state.get("graphiti_related_conversations", [])
    
    # ... existing session check logic ...
    
    # If not, Fetch initial RAG data
    if not context:
        search_result = await run_search_for_deep_agent(query, user_id)
        context = search_result["context"]
        sources = search_result["sources"]
    
    # BUILD PERSONALIZED CLARIFICATION PROMPT
    profile_hint = ""
    if user_profile:
        # Use profile to ask better questions
        if user_profile.get("country"):
            profile_hint = f"\nNote: User is from {user_profile.get('country')}, consider this in questions."
        if user_profile.get("role"):
            profile_hint += f"\nNote: User role is {user_profile.get('role')}, tailor questions accordingly."
    
    related_hint = ""
    if related_convs:
        related_hint = "\n\nConsider what user has asked before when generating questions."
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are an HR assistant helping to clarify a user's generic question.{profile_hint}{related_hint}

Based on the retrieved context from our knowledge base, generate 2-4 targeted clarifying questions.

IMPORTANT RULES:
1. Questions should be based on ACTUAL OPTIONS/CATEGORIES found in the context
2. Consider user's profile and past conversations when possible
3. Questions should help narrow down exactly what the user needs
4. Format questions as a numbered list
5. Be specific - use real category names from the context
6. Keep questions concise and clear
7. Ask questions in a logical order (e.g., country first, then position, then specific details)"""),
        ("user", f"User's generic question: {query}\n\nAvailable context from knowledge base:\n{context}\n\nGenerate clarifying questions:")
    ])
    
    # Rest of the function...
```

**Impact**: Clarification questions will be personalized and context-aware.

---

#### Task 4.2: Update `clarification_answer_handler_node`
**File**: `rag_server.py` (line ~2414)

**Current**: Doesn't use history or Graphiti

**Change to**:
```python
async def clarification_answer_handler_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    
    # ... existing session logic ...
    
    # When generating final answer, include profile context
    profile_context = ""
    if user_profile:
        profile_parts = [f"{k}: {v}" for k, v in user_profile.items() if v]
        profile_context = f"\n\nUser Context: {', '.join(profile_parts)}"
    
    messages = [
        ("system", f"You are a helpful HR assistant.{profile_context}\n\n"
                   "Answer the user's question based STRICTLY on the context provided..."),
        ("user", f"Original Question: {existing_session.original_query}\n\n"
                + (f"Clarification Answers Provided:\n{clarification_summary}\n\n" if clarification_summary else "")
                + f"Context from Knowledge Base:\n{context}\n\n"
                + f"Based STRICTLY on the context above, provide a comprehensive answer...")
    ]
    
    # Rest of the function...
```

**Impact**: Clarification answers will be personalized.

---

### **Phase 5: Update Other Nodes** (Priority: MEDIUM)

#### Task 5.1: Update `router_node`
**File**: `rag_server.py` (line ~1960)

**Change to**: Include history and Graphiti in routing decision

```python
async def router_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    
    # ... existing clarification check ...
    
    # Include context in routing prompt
    context_hint = ""
    if conversation_history:
        last_user_msg = [m for m in conversation_history if m.get("role") == "user"]
        if last_user_msg:
            context_hint = f"\n\nPrevious user question: {last_user_msg[-1].get('content', '')[:100]}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an expert at routing user queries.{context_hint}\n\n"
                   "Classify the query as:\n"
                   "- 'SIMPLE' if it is specific, factual...\n"
                   "- 'COMPLEX' if it implies multiple steps...\n"
                   # ... rest of routing logic
        ),
        ("user", "{query}")
    ])
    
    # Rest of the function...
```

---

#### Task 5.2: Update `decomposer_node`
**File**: `rag_server.py` (line ~2101)

**Change to**: Use history to understand what was asked before

```python
async def decomposer_node(state: AgentState):
    query = state["original_query"]
    
    # GET HISTORY FROM STATE
    conversation_history = state.get("conversation_history", [])
    
    # Include context in decomposition
    context_hint = ""
    if conversation_history:
        context_hint = "\n\nConsider what the user has asked before when breaking down this query."
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"You are an expert planner.{context_hint}\n\n"
                   "Break down the complex query into 2-4 distinct, simpler sub-queries..."),
        ("user", "{query}")
    ])
    
    # Rest of the function...
```

---

#### Task 5.3: Update `executor_node`
**File**: `rag_server.py` (line ~2112)

**Change to**: Use history for context-aware sub-query execution

```python
async def executor_node(state: AgentState):
    sub_queries = state["sub_queries"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    
    # Use context when executing sub-queries
    # (Sub-queries are executed via run_search_for_deep_agent, which already uses user_id)
    # Could enhance run_search_for_deep_agent to accept history/Graphiti if needed
    
    # Rest of the function...
```

---

#### Task 5.4: Update `doc_preference_handler_node`
**File**: `rag_server.py` (line ~2538)

**Change to**: Use Graphiti to infer user preferences

```python
async def doc_preference_handler_node(state: AgentState):
    query = state["original_query"]
    
    # GET GRAPHITI FROM STATE
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    related_convs = state.get("graphiti_related_conversations", [])
    
    # Check if we can infer preference from past conversations
    inferred_preference = None
    if related_convs:
        # Analyze past conversations to infer preference
        # (e.g., if user always asks for workflows, prefer workflow)
        workflow_count = sum(1 for c in related_convs if "workflow" in c.get("fact", "").lower())
        if workflow_count > len(related_convs) / 2:
            inferred_preference = "workflow"
    
    # Use inferred preference if available
    # ... rest of the function ...
```

---

### **Phase 6: Update Existing Nodes That Use History** (Priority: LOW)

#### Task 6.1: Update `greeting_detection_node`
**File**: `rag_server.py` (line ~1729)

**Change**: Use history from state instead of calling `get_user_history()`

```python
async def greeting_detection_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY FROM STATE (instead of calling get_user_history)
    conversation_history = state.get("conversation_history", [])
    
    # ... rest of the function uses conversation_history ...
```

---

#### Task 6.2: Update `greeting_response_node`
**File**: `rag_server.py` (line ~1844)

**Change**: Use history from state instead of calling `get_user_history()`

```python
async def greeting_response_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # GET HISTORY AND GRAPHITI FROM STATE
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    user_profile = graphiti_context.get("user_profile", {})
    
    # Use both history and Graphiti for better personalization
    # ... rest of the function ...
```

---

#### Task 6.3: Update `answer_relevance_node`
**File**: `rag_server.py` (line ~3040)

**Change**: Use history from state instead of calling `get_user_history()`

```python
async def answer_relevance_node(state: AgentState):
    # ... existing code ...
    
    # GET HISTORY FROM STATE
    conversation_history = state.get("conversation_history", [])
    
    # ... rest of the function uses conversation_history ...
```

---

### **Phase 7: Helper Functions** (Priority: LOW)

#### Task 7.1: Create Helper Function to Build Context-Aware Prompts
**File**: `rag_server.py` (new function)

```python
def build_context_aware_prompt(
    base_prompt: str,
    conversation_history: List[Dict[str, str]] = None,
    graphiti_context: Dict[str, Any] = None
) -> str:
    """
    Build a personalized prompt using conversation history and Graphiti context.
    
    Args:
        base_prompt: Base system prompt
        conversation_history: Recent conversation history
        graphiti_context: Graphiti context (user profile, related conversations, temporal flow)
    
    Returns:
        Enhanced prompt with context
    """
    enhancements = []
    
    # Add user profile
    if graphiti_context:
        user_profile = graphiti_context.get("user_profile", {})
        if user_profile:
            profile_parts = [f"{k}: {v}" for k, v in user_profile.items() if v]
            enhancements.append(f"User Profile: {', '.join(profile_parts)}")
    
    # Add related conversations
    related_convs = graphiti_context.get("related_conversations", []) if graphiti_context else []
    if related_convs:
        related_text = "\n".join([f"- {c.get('fact', '')[:150]}" for c in related_convs[:3]])
        enhancements.append(f"Related Past Conversations:\n{related_text}")
    
    # Add conversation history summary
    if conversation_history:
        recent_topics = []
        for msg in conversation_history[-5:]:
            if msg.get("role") == "user":
                content = msg.get("content", "")[:50]
                recent_topics.append(content)
        if recent_topics:
            enhancements.append(f"Recent Topics: {', '.join(recent_topics)}")
    
    if enhancements:
        context_section = "\n\n".join(enhancements)
        return f"{base_prompt}\n\n{context_section}"
    
    return base_prompt
```

**Usage**: Can be used by all nodes to build personalized prompts consistently.

---

## 📊 Implementation Checklist

### Phase 1: AgentState ✅
- [ ] Add `conversation_history` to `AgentState`
- [ ] Add `graphiti_context` to `AgentState` (ensure it's typed)
- [ ] Add `graphiti_related_conversations` to `AgentState`
- [ ] Add `graphiti_temporal_flow` to `AgentState`

### Phase 2: Endpoints ✅
- [ ] Update `/query` endpoint to pass `conversation_history` in `initial_state`
- [ ] Update `/query/stream` endpoint to pass `conversation_history` in `initial_state`
- [ ] Verify Graphiti context is correctly passed (already done, but verify)

### Phase 3: Answer Generation Nodes ✅
- [ ] Update `simple_rag_node` to use history and Graphiti
- [ ] Update `synthesizer_node` to use history and Graphiti
- [ ] Update `format_handler_node` to use Graphiti (user preferences)

### Phase 4: Clarification Nodes ✅
- [ ] Update `clarifier_node` to use history and Graphiti
- [ ] Update `clarification_answer_handler_node` to use history and Graphiti

### Phase 5: Other Nodes ✅
- [ ] Update `router_node` to use history
- [ ] Update `decomposer_node` to use history
- [ ] Update `executor_node` to use history and Graphiti
- [ ] Update `doc_preference_handler_node` to use Graphiti

### Phase 6: Existing Nodes ✅
- [ ] Update `greeting_detection_node` to use state history
- [ ] Update `greeting_response_node` to use state history and Graphiti
- [ ] Update `answer_relevance_node` to use state history

### Phase 7: Helper Functions ✅
- [ ] Create `build_context_aware_prompt()` helper function
- [ ] Update nodes to use helper function (optional, for consistency)

---

## 🧪 Testing Plan

### Test 1: History Passed in State
- Verify `conversation_history` is in `initial_state`
- Verify nodes can access `state.get("conversation_history")`
- Verify history contains last 10 messages

### Test 2: Graphiti Passed in State
- Verify `graphiti_context` is in `initial_state`
- Verify nodes can access `state.get("graphiti_context")`
- Verify Graphiti context contains user_profile, related_conversations, temporal_flow

### Test 3: Answer Generation Uses Context
- Test `simple_rag_node` with history and Graphiti
- Verify answers are personalized (mention user profile if available)
- Verify answers reference past conversations if relevant

### Test 4: Clarification Uses Context
- Test `clarifier_node` with user profile
- Verify clarification questions consider user's country/role
- Verify questions are personalized

### Test 5: End-to-End
- Test full conversation flow with history and Graphiti
- Verify responses are context-aware
- Verify personalization improves over time

---

## 📈 Expected Benefits

1. **Personalized Responses**: Answers will consider user profile and past conversations
2. **Context-Aware Clarifications**: Questions will be tailored to user's context
3. **Better Follow-up Understanding**: Follow-up questions will be understood in context
4. **Consistent Context Access**: All nodes use same history/Graphiti data
5. **Improved User Experience**: More natural, personalized conversations

---

## ⚠️ Risks and Mitigations

### Risk 1: Performance Impact
- **Risk**: Passing history and Graphiti to all nodes may slow down processing
- **Mitigation**: Limit history to last 10 messages, limit Graphiti results to top 3-5

### Risk 2: Token Limit
- **Risk**: Including history and Graphiti in prompts may exceed token limits
- **Mitigation**: Truncate history to last 3-5 messages in prompts, summarize Graphiti facts

### Risk 3: Inconsistent Usage
- **Risk**: Nodes may use history/Graphiti inconsistently
- **Mitigation**: Create helper function `build_context_aware_prompt()` for consistency

### Risk 4: Breaking Changes
- **Risk**: Changes may break existing functionality
- **Mitigation**: Test each node individually, maintain backward compatibility

---

## 🎯 Success Criteria

1. ✅ All nodes can access `conversation_history` from state
2. ✅ All nodes can access `graphiti_context` from state
3. ✅ Answer generation nodes use history and Graphiti for personalization
4. ✅ Clarification nodes use history and Graphiti for better questions
5. ✅ Responses are more personalized and context-aware
6. ✅ No performance degradation (response time < 5s)
7. ✅ All tests pass

---

## 📝 Notes

- Start with Phase 1 and 2 (foundation)
- Then Phase 3 (highest impact - answer generation)
- Then Phase 4 (high impact - clarifications)
- Phases 5-7 can be done incrementally

- Consider creating a utility module for context-aware prompt building
- Monitor performance after each phase
- Test with real conversations to verify improvements
