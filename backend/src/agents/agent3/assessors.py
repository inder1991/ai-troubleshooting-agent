"""
Impact & Risk Assessment for Agent 3

Analyzes potential side effects, security concerns, and regression risk.

Version: 4.0 - Anthropic migration
"""

import ast
import json
import difflib
from typing import Dict, Any, List

from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ImpactAssessor:
    """Assesses impact and risk of proposed fix"""

    def __init__(self, llm_client: AnthropicClient):
        """
        Initialize assessor

        Args:
            llm_client: AnthropicClient instance for LLM calls
        """
        self.llm_client = llm_client

    async def assess_impact(
        self,
        file_path: str,
        original_code: str,
        fixed_code: str,
        call_chain: List[str],
    ) -> Dict[str, Any]:
        """
        Generate impact report

        Args:
            file_path: Path to file being fixed
            original_code: Original code
            fixed_code: Fixed code
            call_chain: Function call chain from Agent 2

        Returns:
            {
                "side_effects": list,
                "security_review": str,
                "regression_risk": str (Low/Medium/High),
                "affected_functions": list,
                "diff_lines": int
            }
        """
        logger.info("\n" + "=" * 80)
        logger.info("IMPACT & RISK ASSESSMENT")
        logger.info("=" * 80)

        # 1. Identify affected functions
        affected = self._find_affected_functions(fixed_code, call_chain)
        logger.info(f"\nAffected Functions: {len(affected)}")
        for func in affected[:5]:
            logger.info(f"   - {func}")
        if len(affected) > 5:
            logger.info(f"   ... and {len(affected) - 5} more")

        # 2. Generate diff
        diff = list(
            difflib.unified_diff(
                original_code.splitlines(keepends=True),
                fixed_code.splitlines(keepends=True),
                fromfile="original.py",
                tofile="fixed.py",
                lineterm="",
            )
        )

        diff_text = "\n".join(diff[:100])  # Limit diff size for LLM

        # 3. LLM analysis of impact
        impact_analysis = await self._llm_impact_analysis(
            file_path, diff_text, affected
        )

        # 4. Calculate regression risk
        risk_score = self._calculate_risk(original_code, fixed_code)

        result = {
            "side_effects": impact_analysis.get("side_effects", []),
            "security_review": impact_analysis.get(
                "security_review", "No security concerns identified"
            ),
            "regression_risk": risk_score,
            "affected_functions": affected,
            "diff_lines": len(diff),
        }

        logger.info(f"\nRegression Risk: {risk_score}")
        logger.info(f"Diff Size: {len(diff)} lines")

        if result["side_effects"]:
            logger.info(f"\nPotential Side Effects:")
            for effect in result["side_effects"][:3]:
                logger.info(f"   - {effect}")

        logger.info("\n" + "=" * 80 + "\n")

        return result

    def _find_affected_functions(
        self, code: str, call_chain: List[str]
    ) -> List[str]:
        """Find functions that might be affected by the change."""
        try:
            tree = ast.parse(code)
            functions = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            affected = [f for f in functions if f in call_chain]
            if not affected and functions:
                affected = functions[:5]
            return affected
        except Exception:
            return call_chain[:5]

    async def _llm_impact_analysis(
        self, file_path: str, diff: str, affected: List[str]
    ) -> Dict[str, Any]:
        """
        Use AnthropicClient to analyze potential impact.

        Args:
            file_path: Path to file
            diff: Code diff
            affected: List of affected functions

        Returns:
            {"side_effects": list, "security_review": str, "breaking_changes": list}
        """
        system_prompt = (
            "You are a code review expert analyzing the impact of a code change.\n\n"
            "Analyze the diff and identify:\n"
            "1. Potential side effects on other parts of the system\n"
            "2. Security concerns (new inputs, secrets, vulnerabilities)\n"
            "3. Breaking changes for callers\n\n"
            "Respond in JSON format:\n"
            '{\n  "side_effects": ["list of potential side effects"],\n'
            '  "security_review": "security assessment",\n'
            '  "breaking_changes": ["list of breaking changes or empty"]\n}\n\n'
            "Be concise. Focus on real risks, not theoretical concerns."
        )

        user_prompt = (
            f"File: {file_path}\n"
            f"Affected Functions: {', '.join(affected) if affected else 'unknown'}\n\n"
            f"Diff:\n{diff[:2000]}\n\n"
            f"Analyze the impact:"
        )

        try:
            response = await self.llm_client.chat(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=2048,
            )

            content = response.text

            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())

        except Exception as e:
            logger.info(f"   LLM analysis failed: {e}")
            return self._heuristic_analysis(diff)

    def _heuristic_analysis(self, diff: str) -> Dict[str, Any]:
        """Fallback heuristic analysis when LLM fails."""
        side_effects = []
        security_concerns = []

        if "import" in diff.lower():
            side_effects.append("New dependencies added - verify compatibility")
        if "timeout" in diff.lower():
            side_effects.append("Timeout behavior changed - may affect latency")
        if "retry" in diff.lower():
            side_effects.append(
                "Retry mechanism added - may increase request duration"
            )
        if "except" in diff.lower():
            side_effects.append(
                "Error handling modified - verify exception propagation"
            )
        if any(
            kw in diff.lower() for kw in ("password", "token", "key")
        ):
            security_concerns.append(
                "Potential credential handling - review for security"
            )
        if "input" in diff.lower() or "request." in diff.lower():
            security_concerns.append(
                "User input handling - verify validation"
            )

        security_review = (
            "Security concerns identified: " + "; ".join(security_concerns)
            if security_concerns
            else "No obvious security concerns"
        )

        return {
            "side_effects": side_effects
            if side_effects
            else ["Unable to analyze - manual review recommended"],
            "security_review": security_review,
            "breaking_changes": [],
        }

    def _calculate_risk(self, original: str, fixed: str) -> str:
        """Calculate regression risk score."""
        diff = list(
            difflib.unified_diff(original.splitlines(), fixed.splitlines())
        )

        diff_lines = len(diff)
        original_lines = len(original.splitlines())
        lines_changed_pct = (diff_lines / max(original_lines, 1)) * 100

        risk_factors = 0

        if diff_lines > 100:
            risk_factors += 2
        elif diff_lines > 50:
            risk_factors += 1

        if lines_changed_pct > 50:
            risk_factors += 2
        elif lines_changed_pct > 20:
            risk_factors += 1

        diff_str = "\n".join(diff)
        if "+import " in diff_str:
            risk_factors += 1
        if any("+except" in line or "-except" in line for line in diff):
            risk_factors += 1

        if risk_factors >= 4:
            return "High"
        elif risk_factors >= 2:
            return "Medium"
        else:
            return "Low"
