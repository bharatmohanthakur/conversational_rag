# Missing JSON Error Handling in Structured Outputs

## Issues Found

The following functions use `with_structured_output()` but **DO NOT have proper JSON parsing error handling**:

### 1. `router_node` (rag_server.py:2018)
- **Status**: ❌ NO error handling
- **Impact**: If JSON parsing fails, entire routing fails
- **Location**: Line 2018-2020

### 2. `simple_rag_node` (rag_server.py:2152)
- **Status**: ❌ NO error handling
- **Impact**: If JSON parsing fails, answer generation fails
- **Location**: Line 2152-2153

### 3. `decomposer_node` (rag_server.py:2214)
- **Status**: ❌ NO error handling
- **Impact**: If JSON parsing fails, query decomposition fails
- **Location**: Line 2214-2215

### 4. `clarifier_node` (rag_server.py:2586)
- **Status**: ❌ NO error handling
- **Impact**: If JSON parsing fails, clarification logic fails
- **Location**: Line 2586-2587

### 5. `assess_answer_confidence` (llm_classifier.py:675)
- **Status**: ⚠️ Has try-except but doesn't specifically handle JSONDecodeError
- **Impact**: JSON errors are caught but not handled gracefully
- **Location**: Line 675

### 6. `greeting_detection_node` (rag_server.py:1855)
- **Status**: ⚠️ Has try-except but might not catch structured output JSON errors
- **Impact**: JSON errors might not be handled properly
- **Location**: Line 1855-1856

## Functions WITH Proper Error Handling

✅ `clarification_answer_handler_node` (rag_server.py:3269) - Has try-except
✅ `answer_relevance_check_node` (rag_server.py:3341) - Has try-except
✅ `reranker.py` - Has JSON error handling with retry
✅ `llm_context_classifier.py` - Has JSON error handling
✅ `corrective_rag.py` - Has basic error handling

## Recommended Fix

Add try-except blocks with JSON parsing error handling and fallback logic for all functions using `with_structured_output()`.
