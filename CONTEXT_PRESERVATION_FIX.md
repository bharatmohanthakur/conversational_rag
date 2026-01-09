# Context Preservation Fix for Multi-Turn Conversations

## Problem
When conversations went beyond 2 turns (especially with clarification questions), the system would lose track of the original user question's intent. The query rewriting mechanism focused on immediate context rather than preserving the original question's purpose.

## Root Causes
1. **No explicit tracking**: Original questions weren't explicitly marked or tracked
2. **Immediate context bias**: The rewriting prompt emphasized "immediate context" over original intent
3. **Limited history**: Only looking at last 10 messages without identifying the original question
4. **Context drift**: After multiple clarification turns, LLM would drift from original intent

## Solution Implemented

### 1. Original Question Tracking (`conversation_manager.py`)
Added two new methods:
- **`get_original_question(user_id, within_last_n=10)`**: Retrieves the original question from conversation history
  - Looks for messages marked with `is_original_question` metadata
  - Filters out greetings and short clarification answers
  - Returns the first substantive user question

- **`mark_as_original_question(user_id)`**: Marks the most recent user message as the original question
  - Updates metadata with `is_original_question: True`
  - Persists to Redis or in-memory storage

### 2. Enhanced Query Rewriting (`rag_server.py`)
Modified `rewrite_query_with_history()`:
- **Extract original question**: Calls `get_original_question()` to retrieve the original query
- **Prominent prompt placement**: Includes original question at top of prompt with "**IMPORTANT - Original Question**"
- **Updated rules**:
  1. Preserve Original Intent
  2. Handle Clarification Answers (combine with original question)
  3. Maintain Core Topic (from original question)
  4. Context Over Recency (prioritize original over immediate)
- **Safety check**: If rewritten query is too short (<5 words), combines with original question

### 3. Automatic Marking (`rag_server.py`)
Modified `query_endpoint()`:
- Automatically marks new questions (not greetings or clarification answers) with `is_original_question: True`
- Ensures original intent is preserved from the first turn

## Example Flow

### Before Fix:
```
Turn 1:
User: "What is the maternity leave policy?"
System: "Which country?"

Turn 2:
User: "Lebanon"
System: "What position?"

Turn 3:
User: "Manager"
Rewritten Query: "Manager in Lebanon" ❌ (Lost "maternity leave" context)
```

### After Fix:
```
Turn 1:
User: "What is the maternity leave policy?" [MARKED AS ORIGINAL]
System: "Which country?"

Turn 2:
User: "Lebanon"
Rewritten Query: "What is the maternity leave policy in Lebanon?" ✅

Turn 3:
User: "Manager"
Rewritten Query: "What is the maternity leave policy in Lebanon for Manager position?" ✅
```

## Benefits
1. **Context preservation**: Original question intent maintained across all turns
2. **Better retrieval**: More accurate document retrieval with complete context
3. **Improved answers**: Final answers address the original question comprehensively
4. **User experience**: Users don't need to repeat their original question

## Testing
To test the fix:
```bash
python3 test_csp_questions_multi_turn.py
```

The test suite simulates multi-turn conversations with clarification questions and validates that answers maintain the original question's context.

## Files Modified
1. `conversation_manager.py` - Added original question tracking methods
2. `rag_server.py` - Enhanced query rewriting and automatic marking
3. `test_context_preservation.py` - Unit test for verification (created)

## Technical Notes
- Original question metadata is stored in Redis (with fallback to in-memory)
- Works with existing clarification tracking system
- Backward compatible - works even if original question not marked
- Graceful degradation - fallback to existing logic if extraction fails
