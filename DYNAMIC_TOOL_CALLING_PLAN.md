# Plan: Dynamic Tool Calling for Agentic System

## 🎯 Current Problem

**Current System**: Uses **fixed tools** for every query
- Always calls: Qdrant + Graphiti
- No dynamic selection based on query type
- No tool calling capabilities

**What We Need**: **Agent decides which tools to use** based on query

---

## ✅ What Dynamic Tool Calling Would Enable

### Example Scenarios:

1. **Calculation Query**: "What's 25% of 5000?"
   - Current: Searches Qdrant (wrong tool)
   - With Tool Calling: Agent calls `calculate()` tool

2. **Web Search Query**: "What's the latest HR policy update?"
   - Current: Only searches local documents
   - With Tool Calling: Agent calls `web_search()` tool

3. **Memory Query**: "What did I ask about last week?"
   - Current: Uses Graphiti (but always)
   - With Tool Calling: Agent decides if Graphiti is needed

4. **Document Query**: "What's the leave policy?"
   - Current: Uses Qdrant (but always)
   - With Tool Calling: Agent decides if Qdrant is needed

5. **Multi-Tool Query**: "Calculate my leave balance and check the policy"
   - Current: Only searches documents
   - With Tool Calling: Agent calls both `calculate()` and `search_documents()`

---

## 🚀 Implementation Plan

### Phase 1: Define Tool Registry

Create a registry of available tools:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search HR policy documents in Qdrant vector database. Use for questions about policies, procedures, benefits, leave, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "default": 7}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search conversation history and user profile from Graphiti knowledge graph. Use for questions about past conversations, user preferences, or context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "memory_types": {"type": "array", "items": {"type": "string"}, "description": "Types: conversation, user_profile, procedural, semantic"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform mathematical calculations. Use for questions involving numbers, percentages, dates, or calculations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Mathematical expression to evaluate"},
                    "context": {"type": "string", "description": "Context for the calculation"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use for questions about latest updates, current events, or information not in documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query"},
                    "num_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Get user profile information (country, role, department, preferences). Use when user context is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID"},
                    "fields": {"type": "array", "items": {"type": "string"}, "description": "Specific fields to retrieve"}
                },
                "required": ["user_id"]
            }
        }
    }
]
```

---

### Phase 2: Create Tool Execution Functions

```python
async def execute_tool(tool_name: str, parameters: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Execute a tool based on tool name and parameters.
    
    Args:
        tool_name: Name of the tool to execute
        parameters: Tool parameters
        user_id: User ID for context
    
    Returns:
        Tool execution result
    """
    if tool_name == "search_documents":
        query = parameters.get("query")
        num_results = parameters.get("num_results", 7)
        result = await run_search_for_deep_agent(query, user_id, use_advanced_rag=True)
        return {
            "tool": "search_documents",
            "result": result.get("context", ""),
            "sources": result.get("sources", []),
            "images": result.get("images", [])
        }
    
    elif tool_name == "search_memory":
        query = parameters.get("query")
        memory_types = parameters.get("memory_types", ["conversation", "user_profile"])
        facts = await search_graphiti_memory(query, user_id, num_results=5, memory_types=memory_types)
        return {
            "tool": "search_memory",
            "result": "\n".join([f.get("fact", "") for f in facts]),
            "facts": facts
        }
    
    elif tool_name == "calculate":
        expression = parameters.get("expression")
        context = parameters.get("context", "")
        # Use Python eval (with safety checks) or a math library
        try:
            # Safe evaluation (only math operations)
            import re
            if re.match(r'^[0-9+\-*/().\s%]+$', expression):
                result = eval(expression)
                return {
                    "tool": "calculate",
                    "result": str(result),
                    "expression": expression
                }
            else:
                return {"tool": "calculate", "error": "Invalid expression"}
        except Exception as e:
            return {"tool": "calculate", "error": str(e)}
    
    elif tool_name == "web_search":
        query = parameters.get("query")
        # Integrate with web search API (e.g., Tavily, Serper, etc.)
        # For now, return placeholder
        return {
            "tool": "web_search",
            "result": f"Web search results for: {query}",
            "note": "Web search integration needed"
        }
    
    elif tool_name == "get_user_profile":
        user_id_param = parameters.get("user_id", user_id)
        fields = parameters.get("fields", [])
        profile = user_profile_tracker.get_profile(user_id_param)
        if fields:
            profile = {k: v for k, v in profile.items() if k in fields}
        return {
            "tool": "get_user_profile",
            "result": profile
        }
    
    else:
        return {"tool": tool_name, "error": f"Unknown tool: {tool_name}"}
```

---

### Phase 3: Create Tool Selection Node

```python
async def tool_selection_node(state: AgentState):
    """
    Agent decides which tools to use based on query.
    Uses LLM with function calling to select tools.
    """
    query = state["original_query"]
    user_id = state["user_id"]
    
    # Get conversation history for context
    conversation_history = state.get("conversation_history", [])
    graphiti_context = state.get("graphiti_context", {})
    
    # Build context for tool selection
    context_parts = []
    if conversation_history:
        context_parts.append(f"Recent conversation: {conversation_history[-3:]}")
    if graphiti_context.get("user_profile"):
        context_parts.append(f"User profile: {graphiti_context['user_profile']}")
    
    context_str = "\n".join(context_parts) if context_parts else "No additional context"
    
    # Use LLM with function calling to select tools
    messages = [
        {
            "role": "system",
            "content": f"""You are a tool selection agent. Analyze the user's query and decide which tools are needed to answer it.

Available Tools:
1. search_documents - For HR policy questions
2. search_memory - For past conversation questions
3. calculate - For mathematical calculations
4. web_search - For current/latest information
5. get_user_profile - For user context

Context:
{context_str}

Select the appropriate tools for this query. You can select multiple tools if needed."""
        },
        {
            "role": "user",
            "content": f"Query: {query}\n\nWhich tools should be used to answer this query?"
        }
    ]
    
    # Enable function calling
    response = aoai_client.chat.completions.create(
        model=AZURE_CHAT_DEPLOYMENT,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",  # Let model decide
        temperature=0.1
    )
    
    # Extract tool calls
    tool_calls = []
    if response.choices[0].message.tool_calls:
        for tool_call in response.choices[0].message.tool_calls:
            tool_name = tool_call.function.name
            parameters = json.loads(tool_call.function.arguments)
            tool_calls.append({
                "tool": tool_name,
                "parameters": parameters
            })
    
    # If no tools selected, default to document search
    if not tool_calls:
        tool_calls = [{
            "tool": "search_documents",
            "parameters": {"query": query}
        }]
    
    logger.info(f"🔧 Tool selection: {[tc['tool'] for tc in tool_calls]}")
    
    return {
        "selected_tools": tool_calls,
        "tool_selection_reasoning": response.choices[0].message.content or ""
    }
```

---

### Phase 4: Create Tool Execution Node

```python
async def tool_execution_node(state: AgentState):
    """
    Execute selected tools and collect results.
    """
    selected_tools = state.get("selected_tools", [])
    user_id = state["user_id"]
    
    if not selected_tools:
        return state
    
    # Execute tools in parallel
    tool_results = []
    execution_tasks = []
    
    for tool_call in selected_tools:
        tool_name = tool_call["tool"]
        parameters = tool_call["parameters"]
        parameters["user_id"] = user_id  # Add user_id to parameters
        execution_tasks.append(execute_tool(tool_name, parameters, user_id))
    
    # Execute all tools in parallel
    results = await asyncio.gather(*execution_tasks, return_exceptions=True)
    
    # Process results
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Tool execution error: {result}")
            tool_results.append({
                "tool": selected_tools[i]["tool"],
                "error": str(result)
            })
        else:
            tool_results.append(result)
    
    # Combine results into context
    context_parts = []
    all_sources = []
    all_images = []
    
    for result in tool_results:
        if "error" not in result:
            if result.get("result"):
                context_parts.append(f"[{result['tool']}]: {result['result']}")
            if result.get("sources"):
                all_sources.extend(result["sources"])
            if result.get("images"):
                all_images.extend(result["images"])
    
    combined_context = "\n\n".join(context_parts)
    
    logger.info(f"🔧 Tool execution complete: {len(tool_results)} tools executed")
    
    return {
        "tool_results": tool_results,
        "context": combined_context,
        "sources": all_sources,
        "images": all_images
    }
```

---

### Phase 5: Update Workflow

```python
# Add new nodes
workflow.add_node("tool_selection", tool_selection_node)
workflow.add_node("tool_execution", tool_execution_node)

# Update routing
# After router, go to tool selection instead of directly to simple_rag
workflow.add_edge("router", "tool_selection")
workflow.add_edge("tool_selection", "tool_execution")

# Tool execution goes to answer generation
# (simple_rag_node would use tool_results instead of calling run_search_for_deep_agent)
workflow.add_edge("tool_execution", "simple_rag")
```

---

### Phase 6: Update Answer Generation Nodes

```python
async def simple_rag_node(state: AgentState):
    query = state["original_query"]
    user_id = state["user_id"]
    
    # Check if tools were executed
    tool_results = state.get("tool_results", [])
    context = state.get("context", "")
    sources = state.get("sources", [])
    images = state.get("images", [])
    
    # If tools were executed, use their results
    if tool_results and context:
        # Use tool-generated context
        pass
    else:
        # Fallback to standard retrieval (backward compatibility)
        search_result = await run_search_for_deep_agent(query, user_id)
        context = search_result["context"]
        sources = search_result["sources"]
        images = search_result.get("images", [])
    
    # Rest of the function...
```

---

## 📊 Benefits

### 1. **Dynamic Tool Selection**
- Agent chooses tools based on query
- No unnecessary tool calls
- Better performance

### 2. **Multi-Tool Support**
- Can use multiple tools for complex queries
- Combines results from different sources

### 3. **Extensibility**
- Easy to add new tools
- Tools are independent modules

### 4. **Cost Efficiency**
- Only calls needed tools
- Reduces unnecessary API calls

---

## 🎯 Example Flows

### Flow 1: Calculation Query
```
Query: "What's 25% of 5000?"
→ Tool Selection: [calculate]
→ Tool Execution: calculate(expression="5000 * 0.25")
→ Result: 1250
→ Answer: "25% of 5000 is 1250."
```

### Flow 2: Document Query
```
Query: "What's the leave policy?"
→ Tool Selection: [search_documents]
→ Tool Execution: search_documents(query="leave policy")
→ Result: Document context
→ Answer: Generated from documents
```

### Flow 3: Memory Query
```
Query: "What did I ask about last week?"
→ Tool Selection: [search_memory]
→ Tool Execution: search_memory(query="last week", memory_types=["conversation"])
→ Result: Past conversations
→ Answer: Generated from memory
```

### Flow 4: Multi-Tool Query
```
Query: "Calculate my leave balance and check the policy"
→ Tool Selection: [calculate, search_documents]
→ Tool Execution: 
  - calculate(expression="...")
  - search_documents(query="leave policy")
→ Result: Combined results
→ Answer: Generated from both
```

---

## ⚠️ Considerations

### 1. **Backward Compatibility**
- Keep `run_search_for_deep_agent` as fallback
- Default to document search if no tools selected

### 2. **Error Handling**
- Handle tool execution failures gracefully
- Fallback to standard retrieval if tools fail

### 3. **Performance**
- Execute tools in parallel
- Cache tool results when possible

### 4. **Security**
- Validate tool parameters
- Sanitize inputs (especially for calculate tool)
- Rate limiting for tool calls

---

## 🚀 Implementation Priority

### **Priority 1: Core Tool Calling** (High Impact)
1. ✅ Define tool registry
2. ✅ Create tool execution functions
3. ✅ Add tool selection node
4. ✅ Add tool execution node
5. ✅ Update workflow

### **Priority 2: Enhanced Tools** (Medium Impact)
6. Add web search tool
7. Add calculator tool
8. Add database query tool (if needed)

### **Priority 3: Optimization** (Low Impact)
9. Tool result caching
10. Parallel tool execution optimization
11. Tool selection learning from past queries

---

## 📝 Conclusion

**Current System**: Fixed tools (always Qdrant + Graphiti)

**With Dynamic Tool Calling**: Agent decides which tools to use

**Impact**: 
- ✅ More agentic behavior
- ✅ Better tool selection
- ✅ Cost efficiency
- ✅ Extensibility

**This is a key feature for making the system truly agentic!**
