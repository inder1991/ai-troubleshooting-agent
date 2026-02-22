"""
Cross-Agent Peer Review for Agent 3

Agent 2 verifies Agent 3's fix makes sense in the context of the codebase.
Now uses LLM-based review with heuristic fallback.
"""

import json
from typing import Dict, Any, Optional

from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CrossAgentReviewer:
    """Submits fix to Agent 2 for logic verification"""

    def __init__(self, agent2_module, llm_client: Optional[AnthropicClient] = None):
        """
        Initialize reviewer

        Args:
            agent2_module: Agent 2 instance (optional)
            llm_client: AnthropicClient for LLM-based review (optional)
        """
        self.agent2 = agent2_module
        self.llm_client = llm_client

    async def request_review(
        self,
        original_file: str,
        fixed_file: str,
        agent2_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Submit fix to Agent 2 for review

        Args:
            original_file: Original code
            fixed_file: Fixed code
            agent2_analysis: Agent 2's analysis results

        Returns:
            {
                "approved": bool,
                "confidence": float,
                "concerns": list,
                "recommendations": list
            }
        """
        logger.info("Starting cross-agent peer review")

        # Prepare review request
        review_request = {
            "original_code": original_file,
            "proposed_fix": fixed_file,
            "original_analysis": agent2_analysis,
            "review_type": "fix_verification"
        }

        # Try LLM-based review first, fall back to heuristics
        if self.llm_client:
            try:
                review_result = await self._llm_review(review_request)
            except Exception as e:
                logger.warning("LLM review failed, falling back to heuristics: %s", e)
                review_result = self._heuristic_review(review_request)
        else:
            review_result = self._heuristic_review(review_request)

        logger.info(
            "Peer review result: approved=%s confidence=%.0f%%",
            review_result['approved'], review_result['confidence'] * 100,
        )

        if review_result['concerns']:
            logger.info("Review concerns (%d): %s", len(review_result['concerns']), review_result['concerns'])

        return review_result

    async def _llm_review(self, request: Dict) -> Dict[str, Any]:
        """Perform LLM-based code review."""
        original = request['original_code']
        fixed = request['proposed_fix']
        analysis = request['original_analysis']

        system_prompt = (
            "You are a senior code reviewer. Analyze the proposed fix against the original code "
            "and the analysis recommendations. Respond with ONLY a JSON object:\n"
            '{"approved": true/false, "confidence": 0.0-1.0, '
            '"concerns": ["list of concerns"], "recommendations": ["list of recommendations"]}\n\n'
            "Approve if the fix correctly addresses the identified issue without introducing "
            "regressions or breaking changes."
        )

        user_prompt = (
            f"## Original Code\n```\n{original[:3000]}\n```\n\n"
            f"## Proposed Fix\n```\n{fixed[:3000]}\n```\n\n"
            f"## Agent 2 Recommendations\n"
            f"- Recommended fix: {analysis.get('recommended_fix', 'N/A')}\n"
            f"- Root cause: {analysis.get('root_cause_explanation', 'N/A')}\n"
            f"- Call chain: {analysis.get('call_chain', [])}\n\n"
            f"Review the fix:"
        )

        response = await self.llm_client.chat(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=1024,
        )

        content = response.text
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())
        # Normalize fields
        return {
            "approved": bool(result.get("approved", False)),
            "confidence": float(result.get("confidence", 0.5)),
            "concerns": list(result.get("concerns", [])),
            "recommendations": list(result.get("recommendations", [])),
        }

    def _heuristic_review(self, request: Dict) -> Dict[str, Any]:
        """
        Fallback heuristic-based review.

        Args:
            request: Review request data

        Returns:
            Review result with approval, confidence, concerns
        """
        concerns = []
        recommendations = []

        original = request['original_code']
        fixed = request['proposed_fix']
        analysis = request['original_analysis']

        # Get recommended fix from Agent 2
        agent2_recommendation = analysis.get('recommended_fix', '').lower()

        # Check 1: Does fix implement retry mechanism?
        if 'retry' in agent2_recommendation or 'tenacity' in agent2_recommendation:
            if '@retry' in fixed or 'tenacity' in fixed:
                logger.debug("Check passed: Retry mechanism implemented")
            else:
                concerns.append("Retry mechanism recommended but not found in fix")

        # Check 2: Does fix implement circuit breaker?
        if 'circuit' in agent2_recommendation or 'breaker' in agent2_recommendation:
            if 'CircuitBreaker' in fixed or 'pybreaker' in fixed:
                logger.debug("Check passed: Circuit breaker implemented")
            else:
                concerns.append("Circuit breaker recommended but not found in fix")

        # Check 3: Does fix add timeout?
        if 'timeout' in agent2_recommendation:
            if 'timeout=' in fixed or 'timeout:' in fixed:
                logger.debug("Check passed: Timeout configured")
            else:
                concerns.append("Timeout recommended but not configured in fix")

        # Check 4: Does fix add error handling?
        if 'error' in agent2_recommendation or 'exception' in agent2_recommendation:
            if 'try:' in fixed or 'except' in fixed:
                logger.debug("Check passed: Error handling added")
            else:
                concerns.append("Error handling recommended but not found in fix")

        # Check 5: Are necessary imports added?
        imports_needed = []
        if '@retry' in fixed and 'from tenacity' not in fixed:
            imports_needed.append('tenacity')
        if 'CircuitBreaker' in fixed and 'from pybreaker' not in fixed:
            imports_needed.append('pybreaker')

        if imports_needed:
            concerns.append(f"Missing imports: {', '.join(imports_needed)}")
        else:
            logger.debug("Check passed: All necessary imports present")

        # Check 6: Code structure maintained?
        if 'def ' in original:
            original_functions = [
                line.strip() for line in original.split('\n')
                if line.strip().startswith('def ')
            ]
            fixed_functions = [
                line.strip() for line in fixed.split('\n')
                if line.strip().startswith('def ')
            ]

            if len(fixed_functions) == len(original_functions):
                logger.debug("Check passed: Code structure maintained")
            else:
                concerns.append(f"Function count changed: {len(original_functions)} -> {len(fixed_functions)}")

        # Calculate confidence based on checks
        total_checks = 6
        checks_passed = total_checks - len(concerns)
        base_confidence = 0.5 + (checks_passed / total_checks * 0.4)

        # Boost confidence if no critical concerns
        critical_concerns = [c for c in concerns if 'Missing imports' in c or 'not found' in c]
        if not critical_concerns:
            base_confidence += 0.1

        # Cap confidence
        confidence = min(base_confidence, 0.95)

        # Approve if confidence is high and no critical concerns
        approved = confidence >= 0.8 and len(critical_concerns) == 0

        # Add recommendations based on concerns
        if not approved:
            if concerns:
                recommendations.append("Review and address the concerns listed above")
            recommendations.append("Verify fix implements all Agent 2 recommendations")

        return {
            "approved": approved,
            "confidence": confidence,
            "concerns": concerns,
            "recommendations": recommendations
        }
