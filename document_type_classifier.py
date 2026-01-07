"""
Intelligent Document Type Classifier using LLM with Chain of Thought.
Classifies documents as workflow, policy, or hybrid based on content analysis.
"""

import logging
from typing import Dict, Any, Literal, Optional
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger("DocumentTypeClassifier")


class DocumentType(Enum):
    """Document type classification."""
    WORKFLOW = "workflow"  # Step-by-step procedures, how-to guides
    POLICY = "policy"  # Rules, guidelines, eligibility criteria
    HYBRID = "hybrid"  # Contains both workflow and policy content


class DocumentTypeResult(BaseModel):
    """Result of document type classification."""
    type: DocumentType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    indicators: Dict[str, Any]  # What led to this classification


class DocumentTypeClassifier:
    """
    Intelligent document type classifier using LLM with CoT reasoning.

    Can classify based on:
    1. Filename (fast, pattern-based)
    2. Content sample (intelligent, LLM-based)
    3. Combined (filename hint + content verification)
    """

    def __init__(self, llm_client, deployment_name: str):
        """
        Initialize classifier.

        Args:
            llm_client: Azure OpenAI client
            deployment_name: Model deployment name
        """
        self.llm_client = llm_client
        self.deployment_name = deployment_name
        self._cache: Dict[str, DocumentTypeResult] = {}

    def classify_by_filename(self, filename: str) -> Optional[DocumentType]:
        """
        Quick classification based on filename patterns (fallback method).

        Args:
            filename: Document filename

        Returns:
            DocumentType if pattern match found, None otherwise
        """
        filename_lower = filename.lower()

        # Workflow indicators in filename
        workflow_keywords = [
            " - w ", " - w-", "workflow", "process", "procedure", "step",
            "guide", "how to", "how-to", "tutorial", "instructions"
        ]

        # Policy indicators in filename
        policy_keywords = [
            "policy", "guideline", "rules", "regulation", "handbook",
            "manual", "code of conduct", "eligibility", "benefits"
        ]

        has_workflow = any(kw in filename_lower for kw in workflow_keywords)
        has_policy = any(kw in filename_lower for kw in policy_keywords)

        if has_workflow and has_policy:
            return DocumentType.HYBRID
        elif has_workflow:
            return DocumentType.WORKFLOW
        elif has_policy:
            return DocumentType.POLICY

        return None  # Uncertain

    def classify_by_content(
        self,
        filename: str,
        content_sample: str,
        max_sample_length: int = 1000
    ) -> DocumentTypeResult:
        """
        Intelligent classification using LLM with Chain of Thought reasoning.

        Args:
            filename: Document filename (used as hint)
            content_sample: First N characters of document content
            max_sample_length: Max characters to analyze (default 1000)

        Returns:
            DocumentTypeResult with classification and reasoning
        """
        # Check cache
        cache_key = f"{filename}_{content_sample[:100]}"
        if cache_key in self._cache:
            logger.debug(f"Cache hit for document: {filename}")
            return self._cache[cache_key]

        # Truncate content sample
        sample = content_sample[:max_sample_length]

        prompt = f"""Classify this document as workflow, policy, or hybrid using step-by-step reasoning.

**STEP 1 - CHAIN OF THOUGHT ANALYSIS:**
Think through the classification step-by-step:

1. Content structure analysis:
   - Does it have numbered steps or sequential instructions? → Workflow indicator
   - Does it state rules, eligibility criteria, or limits? → Policy indicator
   - Does it have both procedural steps AND rules? → Hybrid indicator

2. Language patterns:
   - Action verbs (click, navigate, submit, follow, complete) → Workflow
   - Requirement phrases (must, shall, eligible for, entitled to, restricted) → Policy
   - Mix of both action verbs and requirements → Hybrid

3. Document purpose:
   - Teaching HOW to do something (step-by-step) → Workflow
   - Explaining WHAT is allowed/required (rules) → Policy
   - Comprehensive guide with both → Hybrid

4. Structural indicators:
   - "Step 1, Step 2, Step 3..." → Strong workflow indicator
   - "Eligibility: ..." or "Requirements: ..." → Strong policy indicator
   - Sections for both procedures and policies → Hybrid

5. Filename hint:
   - Does filename contain "workflow", "process", "procedure"? → Likely workflow
   - Does filename contain "policy", "guidelines", "rules"? → Likely policy
   - Filename with " - W " pattern → Explicit workflow marker

**STEP 2 - CLASSIFICATION:**

Filename: {filename}

Content Sample (first {len(sample)} characters):
{sample}

Based on your analysis, classify this document:

{{
  "type": "workflow|policy|hybrid",
  "confidence": 0.0-1.0 (float),
  "reasoning": "Brief explanation of your step-by-step thinking",
  "indicators": {{
    "has_steps": true/false,
    "has_rules": true/false,
    "action_verb_count": integer,
    "requirement_phrase_count": integer,
    "primary_purpose": "procedural|regulatory|comprehensive"
  }}
}}

Classification guidelines:
- **workflow**: Primarily step-by-step instructions (confidence > 0.7 for workflow indicators)
- **policy**: Primarily rules and eligibility (confidence > 0.7 for policy indicators)
- **hybrid**: Significant mix of both (workflow confidence 0.4-0.7 AND policy confidence 0.4-0.7)

Respond ONLY with valid JSON."""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing document types. Use step-by-step reasoning to classify documents accurately. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600
            )

            import json
            result_dict = json.loads(response.choices[0].message.content)

            result = DocumentTypeResult(
                type=DocumentType(result_dict.get("type", "policy")),
                confidence=result_dict.get("confidence", 0.5),
                reasoning=result_dict.get("reasoning", ""),
                indicators=result_dict.get("indicators", {})
            )

            # Cache result
            self._cache[cache_key] = result

            logger.info(f"📄 Classified '{filename}' as {result.type.value} (confidence: {result.confidence:.2f})")
            logger.debug(f"   Reasoning: {result.reasoning[:100]}")

            return result

        except Exception as e:
            logger.error(f"❌ Error classifying document: {e}")

            # Fallback to filename-based classification
            filename_type = self.classify_by_filename(filename)
            return DocumentTypeResult(
                type=filename_type or DocumentType.POLICY,
                confidence=0.5 if filename_type else 0.3,
                reasoning=f"Fallback classification due to error: {str(e)}",
                indicators={"error": True}
            )

    def classify_sources(
        self,
        sources: list,
        content_key: str = "text_snippet",
        filename_key: str = "source"
    ) -> Dict[str, list]:
        """
        Classify a list of sources into workflow, policy, and hybrid categories.

        Args:
            sources: List of source dictionaries
            content_key: Key in dict containing text content
            filename_key: Key in dict containing filename

        Returns:
            Dictionary with 'workflow', 'policy', 'hybrid' keys containing classified sources
        """
        classified = {
            "workflow": [],
            "policy": [],
            "hybrid": []
        }

        for source in sources:
            filename = source.get(filename_key, "unknown")
            content = source.get(content_key, "")

            # Quick filename check first
            filename_type = self.classify_by_filename(filename)

            # If uncertain from filename, use content analysis
            if filename_type is None and content:
                result = self.classify_by_content(filename, content)
                doc_type = result.type
            elif filename_type:
                doc_type = filename_type
            else:
                doc_type = DocumentType.POLICY  # Default fallback

            # Add source to appropriate category
            classified[doc_type.value].append(source)

        logger.info(f"📊 Classification results: "
                   f"{len(classified['workflow'])} workflow, "
                   f"{len(classified['policy'])} policy, "
                   f"{len(classified['hybrid'])} hybrid")

        return classified


# Global instance
_doc_classifier: Optional[DocumentTypeClassifier] = None


def get_document_classifier() -> Optional[DocumentTypeClassifier]:
    """Get global document classifier instance."""
    return _doc_classifier


def init_document_classifier(llm_client, deployment_name: str):
    """
    Initialize global document classifier.

    Args:
        llm_client: Azure OpenAI client
        deployment_name: Model deployment name
    """
    global _doc_classifier
    _doc_classifier = DocumentTypeClassifier(
        llm_client=llm_client,
        deployment_name=deployment_name
    )
    logger.info("✅ Initialized intelligent document type classifier with CoT")
