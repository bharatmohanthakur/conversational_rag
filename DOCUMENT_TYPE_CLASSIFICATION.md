# Document Type Classification: Workflow vs Policy

## Current Implementation (Hardcoded)

### How It Works:
Located in `rag_server.py:1278-1322` within `simple_rag_node()`:

```python
# Classification based on filename pattern
workflow_sources = [s for s in sources if " - W " in s.get("source", "") or " - W-" in s.get("source", "")]
normal_sources = [s for s in sources if s not in workflow_sources]
```

### Document Types:

#### 1. Workflow Documents (Process-Oriented)
**Identifier**: Filename contains `" - W "` or `" - W-"`

**Examples:**
- `Employee Onboarding - W - Complete Guide.pdf`
- `Leave Application - W-Process.pdf`
- `Expense Reimbursement - W Steps.pdf`

**Characteristics:**
- Step-by-step procedures
- How-to instructions
- Process flows
- Action-oriented content

**System Behavior:**
- Uses structured, numbered format
- Emphasizes sequential steps
- References diagrams/flowcharts
- Prompt: "Provide a detailed, structured answer following the workflow steps"

#### 2. Normal Documents (Policy/Guideline)
**Identifier**: Everything else (no " - W " in filename)

**Examples:**
- `Leave Policy Lebanon.pdf`
- `HR Benefits Overview.pdf`
- `Company Code of Conduct.pdf`

**Characteristics:**
- Rules and regulations
- Eligibility criteria
- General information
- What is allowed/not allowed

**System Behavior:**
- Uses standard RAG prompt with CoT
- Focuses on rules, limits, eligibility
- May include tables comparing options

---

## User Experience

### Scenario 1: BOTH Types Found
System presents choice to user:

```
I found relevant information from both **workflow documents** and **policy/guideline documents**.

**Workflow Documents** (step-by-step procedures):
- Employee Onboarding - W - Complete Guide.pdf
- Leave Application - W-Process.pdf

**Policy/Guideline Documents**:
- Leave Policy Lebanon.pdf
- HR Benefits Overview.pdf

Which type would you prefer?
1. **Workflow** - Detailed step-by-step process
2. **Policy/Guideline** - General rules and information
3. **Both** - Combined information from all sources

Please reply with your preference (e.g., 'workflow', 'policy', or 'both').
```

**Router Detection:**
When user responds with "workflow", "policy", "both", "1", "2", or "3", the router classifies it as `DOC_PREFERENCE` complexity.

### Scenario 2: ONLY Workflow Documents
```python
if has_workflow and not has_normal:
    system_prompt = "The user's query matched WORKFLOW documents which contain
                     step-by-step procedures. Provide a detailed, structured
                     answer following the workflow steps. Use numbered steps."
```

### Scenario 3: ONLY Normal Documents
Uses standard CoT-enhanced RAG prompt.

---

## Why This Matters

### 1. Different Content Types
- **Workflows** answer "How do I...?"
- **Policies** answer "What is...?" and "Am I eligible...?"

### 2. Different User Intent
| User Query | Likely Wants |
|------------|--------------|
| "How do I apply for leave?" | **Workflow** (step-by-step process) |
| "What is the leave policy?" | **Policy** (rules and eligibility) |
| "Tell me about annual leave" | **Both** (comprehensive answer) |
| "Can I take maternity leave?" | **Policy** (eligibility criteria) |
| "Show me the onboarding process" | **Workflow** (step-by-step guide) |

### 3. Answer Quality
**Workflow Answer Example:**
```
To apply for annual leave, follow these steps:

1. Log into the HR portal at [URL]
2. Navigate to Leave > Annual Leave Request
3. Select your desired dates
4. Choose your supervisor from the dropdown
5. Click Submit and await approval

Your request will be reviewed within 2 business days.
```

**Policy Answer Example:**
```
Annual Leave Policy:

Eligibility:
- Staff: 22 days per year
- Managers: 27 days per year
- Senior Management: 30 days per year

Rules:
- Must be requested 2 weeks in advance
- Maximum 10 consecutive days without VP approval
- Cannot be carried over more than 5 days to next year
```

---

## Current Limitations (Hardcoded Approach)

### Problem 1: Relies on Filename Convention
- **Issue**: Only works if documents are named with " - W " pattern
- **Impact**: If someone uploads "Onboarding Process.pdf" without " - W ", it won't be detected as workflow

### Problem 2: No Content-Based Detection
- **Issue**: Document might be a workflow but not have " - W " in filename
- **Impact**: Misclassification leads to wrong answer style

### Problem 3: Binary Classification Only
- **Issue**: Some documents might be BOTH workflow AND policy
- **Impact**: Forced to choose one type when document contains both

---

## 🚀 Potential Enhancement: LLM-Based Classification

Instead of relying on filename patterns, we could use LLM to classify document types based on **content**:

### Proposed Approach:

```python
def classify_document_type(document_content: str, document_title: str) -> str:
    """
    Use LLM to classify document as workflow, policy, or hybrid.

    Args:
        document_content: First 500 words of document
        document_title: Document filename/title

    Returns:
        "workflow", "policy", or "hybrid"
    """

    prompt = f"""Classify this document as workflow, policy, or hybrid using step-by-step reasoning.

**STEP 1 - ANALYSIS:**
1. Content structure:
   - Does it have numbered steps or sequential instructions? → Workflow
   - Does it state rules, eligibility, limits? → Policy
   - Does it have both? → Hybrid

2. Language patterns:
   - Action verbs (click, navigate, submit, follow) → Workflow
   - Requirement phrases (must, shall, eligible for) → Policy
   - Mix of both → Hybrid

3. Document purpose:
   - Teaching how to do something → Workflow
   - Explaining what is allowed → Policy
   - Comprehensive guide → Hybrid

**STEP 2 - CLASSIFICATION:**

Document Title: {document_title}

Document Content Preview:
{document_content[:500]}

Classify as:
{{
  "type": "workflow|policy|hybrid",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Respond ONLY with valid JSON."""

    # LLM call with CoT
    # ...
```

### Benefits of LLM-Based Classification:

✅ **Content-aware**: Classifies based on actual content, not filename
✅ **More accurate**: Detects workflows even without " - W " pattern
✅ **Handles hybrid docs**: Can identify documents with both types
✅ **Language-independent**: Works across different naming conventions
✅ **Self-documenting**: Provides reasoning for classification

### When to Run Classification:
- **Option 1**: At document ingestion time (store classification in metadata)
- **Option 2**: At retrieval time (classify retrieved chunks)
- **Option 3**: Hybrid (use filename hint, verify with content if uncertain)

---

## Implementation Status

**Current Status**: ✅ Hardcoded filename-based classification working
**Enhancement Status**: 📝 Documented, not yet implemented

**To implement LLM-based classification:**
1. Add `classify_document_type()` function to new file `document_classifier.py`
2. Modify ingestion pipeline to classify documents at upload time
3. Store classification in Qdrant metadata: `{"doc_type": "workflow|policy|hybrid"}`
4. Update `simple_rag_node` to use metadata instead of filename pattern
5. Add CoT reasoning to classification prompt

**Estimated Impact:**
- More accurate document type detection
- Works with any naming convention
- Better handling of hybrid documents
- Reduces dependency on filename patterns
