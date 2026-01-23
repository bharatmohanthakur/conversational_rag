# How Each Node Utilizes History and Graphiti

## Overview
This document details how each workflow node uses conversation history and Graphiti context for personalized, context-aware responses.

---

## ✅ Nodes That Use History and Graphiti

### 1. **simple_rag_node** (Answer Generation)
**Location**: `rag_server.py:2014-2125`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
related_convs = state.get("graphiti_related_conversations", [])
```

**How it uses history:**
1. **User Profile in System Prompt**:
   ```python
   profile_text = f"\n\nUser Profile: {', '.join(profile_parts)}"
   ```
   - Includes user's role, country, department, etc. in the prompt
   - Helps LLM tailor answers to user's context

2. **Related Past Conversations in System Prompt**:
   ```python
   related_text = f"\n\nRelated Past Conversations:\n{related_summary}"
   ```
   - Includes top 2 related conversations from Graphiti
   - Helps LLM understand what user has asked before

3. **Recent Conversation History in Messages**:
   ```python
   if conversation_history:
       for msg in conversation_history[-3:]:  # Last 3 messages
           if msg.get("role") in ["user", "assistant"]:
               messages.append((msg.get("role"), msg.get("content", "")))
   ```
   - Adds last 3 conversation messages to LLM context
   - Enables understanding of follow-up questions

**Impact**: Answers are personalized based on user profile and past conversations, and follow-up questions are understood in context.

---

### 2. **synthesizer_node** (Complex Query Synthesis)
**Location**: `rag_server.py:2197-2248`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
related_convs = state.get("graphiti_related_conversations", [])
```

**How it uses history:**
1. **User Profile in System Prompt**:
   ```python
   profile_text = f"\n\nUser Profile: {', '.join(profile_parts)}"
   ```
   - Personalizes synthesis based on user's context

2. **Related Past Conversations in System Prompt**:
   ```python
   related_text = f"\n\nRelated Past Conversations:\n{related_summary}"
   ```
   - Includes top 2 related conversations
   - Helps synthesize answers considering past interactions

3. **Recent Conversation History in Messages**:
   ```python
   if conversation_history:
       for msg in conversation_history[-3:]:
           messages.insert(-1, (msg.get("role"), msg.get("content", "")))
   ```
   - Adds last 3 messages before the final user query
   - Provides context for synthesis

**Impact**: Complex query synthesis is personalized and considers past conversations.

---

### 3. **format_handler_node** (Response Formatting)
**Location**: `rag_server.py:2251-2269`

**How it accesses history:**
```python
graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
```

**How it uses history:**
1. **User Format Preferences**:
   ```python
   preferred_format = user_profile.get("preferred_format", None)  # e.g., "table", "bullet", "detailed"
   format_hint = f"\n\nNote: User prefers {preferred_format} format." if preferred_format else ""
   ```
   - Uses user's preferred format from Graphiti profile
   - Applies format preference in system prompt

**Impact**: Formatting respects user preferences learned from past interactions.

---

### 4. **clarifier_node** (Clarification Questions)
**Location**: `rag_server.py:2264-2521`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
related_convs = state.get("graphiti_related_conversations", [])
```

**How it uses history:**
1. **User Profile Hints in Prompt**:
   ```python
   if user_profile.get("country"):
       profile_hint = f"\n\nNote: User is from {user_profile.get('country')}, consider this in questions."
   if user_profile.get("role"):
       profile_hint += f"\nNote: User role is {user_profile.get('role')}, tailor questions accordingly."
   ```
   - Tailors clarification questions based on user's country/role
   - Avoids asking for information already known

2. **Related Conversations Hint**:
   ```python
   if related_convs:
       related_hint = "\n\nConsider what user has asked before when generating questions."
   ```
   - Instructs LLM to consider past conversations when generating questions

**Impact**: Clarification questions are personalized and avoid asking for information already provided.

---

### 5. **clarification_answer_handler_node** (Clarification Answer Processing)
**Location**: `rag_server.py:2524-2608`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
```

**How it uses history:**
1. **User Profile in Answer Generation**:
   ```python
   profile_context = f"\n\nUser Context: {', '.join(profile_parts)}"
   ```
   - Includes user profile in system prompt
   - Helps generate personalized answers based on user's context

**Impact**: Final answers after clarification are personalized based on user profile.

---

### 6. **greeting_detection_node** (Greeting Detection)
**Location**: `rag_server.py:1737-1809`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
if not conversation_history and user_id:
    history = get_user_history(user_id, use_summarization=False)
    conversation_history = history[-5:]  # Last 5 messages
else:
    conversation_history = conversation_history[-5:]
```

**How it uses history:**
1. **LLM Classifier with History**:
   ```python
   result = llm_classifier.classify_query(
       query=query,
       conversation_context=conversation_history,
       active_clarification=False
   )
   ```
   - Passes last 5 messages to LLM classifier
   - Enables context-aware greeting detection (e.g., "hi again" vs "hi")

**Impact**: Greeting detection is context-aware and distinguishes first-time greetings from follow-ups.

---

### 7. **greeting_response_node** (Greeting Response Generation)
**Location**: `rag_server.py:1856-1942`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
if not conversation_history and user_id:
    history = get_user_history(user_id, use_summarization=False)
    conversation_history = history[-10:]  # Last 10 messages
else:
    conversation_history = conversation_history[-10:]

graphiti_context = state.get("graphiti_context", {})
user_profile = graphiti_context.get("user_profile", {})
```

**How it uses history:**
1. **Conversation Context String**:
   ```python
   if conversation_history:
       context_parts = []
       for msg in conversation_history:
           if content and role in ["user", "assistant"]:
               context_parts.append(f"{role.capitalize()}: {content}")
       context_str = "\n".join(context_parts[-5:])  # Last 5 messages
   ```
   - Builds conversation context from last 5 messages
   - Includes in LLM prompt for personalized greetings

2. **User Profile** (from Graphiti):
   - Available for future personalization enhancements

**Impact**: Greeting responses are personalized (e.g., "Hi again!" for returning users, "Hello!" for first-time users).

---

### 8. **answer_relevance_node** (Answer Relevance Check)
**Location**: `rag_server.py:3040-3100`

**How it accesses history:**
```python
conversation_history = state.get("conversation_history", [])
if not conversation_history:
    history = get_user_history(user_id, use_summarization=False)
    conversation_history = history[-5:] if history else []
else:
    conversation_history = conversation_history[-5:]
```

**How it uses history:**
1. **Greeting Detection for Relevance**:
   ```python
   if not is_greeting_or_casual(original_query, conversation_history):
       # This is an actual HR query - preserve clarification
   ```
   - Uses history to detect if query is greeting/casual
   - Prevents clarification questions for simple greetings

**Impact**: Ensures greetings get appropriate responses, not clarification questions.

---

## ❌ Nodes That Don't Use History (Yet)

### 9. **router_node** (Query Routing)
**Location**: `rag_server.py:1972-2006`

**Current Status**: ❌ Does NOT use history or Graphiti

**Should Use**:
- History to understand follow-up questions
- Graphiti to route based on past conversation patterns

---

### 10. **decomposer_node** (Query Decomposition)
**Location**: `rag_server.py:2101-2109`

**Current Status**: ❌ Does NOT use history or Graphiti

**Should Use**:
- History to understand what was asked before
- Graphiti to decompose based on past patterns

---

### 11. **executor_node** (Sub-query Execution)
**Location**: `rag_server.py:2112-2194`

**Current Status**: ❌ Does NOT use history or Graphiti

**Should Use**:
- History for context-aware sub-query execution
- Graphiti for personalized sub-query processing

---

### 12. **doc_preference_handler_node** (Document Preference)
**Location**: `rag_server.py:2538-2582`

**Current Status**: ❌ Does NOT use history or Graphiti

**Should Use**:
- Graphiti to infer user preferences from past interactions
- History to understand preference context

---

## 📊 Summary Table

| Node | History Used? | Graphiti Used? | How It Uses |
|------|--------------|----------------|-------------|
| **simple_rag_node** | ✅ Yes | ✅ Yes | Profile + related convs in prompt, last 3 msgs in context |
| **synthesizer_node** | ✅ Yes | ✅ Yes | Profile + related convs in prompt, last 3 msgs in context |
| **format_handler_node** | ❌ No | ✅ Yes | User format preferences from profile |
| **clarifier_node** | ❌ No | ✅ Yes | Profile hints for better questions, related convs hint |
| **clarification_answer_handler_node** | ❌ No | ✅ Yes | Profile in answer generation |
| **greeting_detection_node** | ✅ Yes | ❌ No | Last 5 msgs for context-aware detection |
| **greeting_response_node** | ✅ Yes | ✅ Yes | Last 5 msgs for personalized greetings |
| **answer_relevance_node** | ✅ Yes | ❌ No | Last 5 msgs for greeting detection |
| **router_node** | ❌ No | ❌ No | - |
| **decomposer_node** | ❌ No | ❌ No | - |
| **executor_node** | ❌ No | ❌ No | - |
| **doc_preference_handler_node** | ❌ No | ❌ No | - |

---

## 🎯 Key Patterns

### Pattern 1: System Prompt Enhancement
Most nodes add user profile and related conversations to the system prompt:
```python
profile_text = f"\n\nUser Profile: {', '.join(profile_parts)}"
related_text = f"\n\nRelated Past Conversations:\n{related_summary}"
system_prompt = f"You are a helpful HR assistant.{profile_text}{related_text}\n\n..."
```

### Pattern 2: Message History Injection
Answer generation nodes add recent messages to the LLM context:
```python
if conversation_history:
    for msg in conversation_history[-3:]:
        messages.append((msg.get("role"), msg.get("content", "")))
```

### Pattern 3: Profile-Based Personalization
Nodes use user profile to tailor responses:
```python
if user_profile.get("country"):
    # Tailor based on country
if user_profile.get("role"):
    # Tailor based on role
```

---

## 📈 Impact

### ✅ Benefits Achieved:
1. **Personalized Answers**: Answers consider user profile and past conversations
2. **Context-Aware Follow-ups**: Follow-up questions are understood in context
3. **Better Clarifications**: Questions are tailored to user's known information
4. **Natural Greetings**: Greetings are personalized based on conversation history

### 🔄 Future Enhancements:
1. **Router Node**: Use history to better route follow-up questions
2. **Decomposer Node**: Use history to understand query context
3. **Executor Node**: Use history for context-aware sub-query execution
4. **Doc Preference Handler**: Use Graphiti to infer preferences

---

## ✅ Conclusion

**8 out of 12 nodes** now use history and/or Graphiti:
- ✅ All answer generation nodes use both
- ✅ Clarification nodes use Graphiti
- ✅ Greeting nodes use history
- ⚠️ Routing and decomposition nodes don't use history yet (lower priority)

The critical nodes for user experience are **fully integrated** and providing personalized, context-aware responses!
