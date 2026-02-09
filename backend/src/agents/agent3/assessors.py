"""
Impact & Risk Assessment for Agent 3

Analyzes potential side effects, security concerns, and regression risk.
"""

import ast
import difflib
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate


class ImpactAssessor:
    """Assesses impact and risk of proposed fix"""
    
    def __init__(self, llm):
        """
        Initialize assessor
        
        Args:
            llm: LangChain LLM instance
        """
        self.llm = llm
    
    def assess_impact(
        self,
        file_path: str,
        original_code: str,
        fixed_code: str,
        call_chain: List[str]
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
        print("\n" + "="*80)
        print("📊 IMPACT & RISK ASSESSMENT")
        print("="*80)
        
        # 1. Identify affected functions
        affected = self._find_affected_functions(fixed_code, call_chain)
        print(f"\n🎯 Affected Functions: {len(affected)}")
        for func in affected[:5]:
            print(f"   • {func}")
        if len(affected) > 5:
            print(f"   ... and {len(affected) - 5} more")
        
        # 2. Generate diff
        diff = list(difflib.unified_diff(
            original_code.splitlines(keepends=True),
            fixed_code.splitlines(keepends=True),
            fromfile='original.py',
            tofile='fixed.py',
            lineterm=''
        ))
        
        diff_text = '\n'.join(diff[:100])  # Limit diff size for LLM
        
        # 3. LLM analysis of impact
        impact_analysis = self._llm_impact_analysis(
            file_path, diff_text, affected
        )
        
        # 4. Calculate regression risk
        risk_score = self._calculate_risk(original_code, fixed_code)
        
        result = {
            "side_effects": impact_analysis.get("side_effects", []),
            "security_review": impact_analysis.get("security_review", "No security concerns identified"),
            "regression_risk": risk_score,
            "affected_functions": affected,
            "diff_lines": len(diff)
        }
        
        print(f"\n📈 Regression Risk: {risk_score}")
        print(f"📝 Diff Size: {len(diff)} lines")
        
        if result['side_effects']:
            print(f"\n⚠️  Potential Side Effects:")
            for effect in result['side_effects'][:3]:
                print(f"   • {effect}")
        
        print("\n" + "="*80 + "\n")
        
        return result
    
    def _find_affected_functions(self, code: str, call_chain: List[str]) -> List[str]:
        """
        Find functions that might be affected by the change
        
        Args:
            code: Fixed code
            call_chain: Call chain from Agent 2
        
        Returns:
            List of affected function names
        """
        try:
            tree = ast.parse(code)
            
            # Find all function definitions
            functions = [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            
            # Filter to those in call chain or calling modified function
            affected = [f for f in functions if f in call_chain]
            
            # If none in call chain, return all functions (conservative)
            if not affected and functions:
                affected = functions[:5]  # Limit to first 5
            
            return affected
        
        except:
            # Fallback to call chain
            return call_chain[:5]
    
    def _llm_impact_analysis(
        self, file_path: str, diff: str, affected: List[str]
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze potential impact
        
        Args:
            file_path: Path to file
            diff: Code diff
            affected: List of affected functions
        
        Returns:
            {
                "side_effects": list,
                "security_review": str,
                "breaking_changes": list
            }
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a code review expert analyzing the impact of a code change.

Analyze the diff and identify:
1. Potential side effects on other parts of the system
2. Security concerns (new inputs, secrets, vulnerabilities)
3. Breaking changes for callers

Respond in JSON format:
{
  "side_effects": ["list of potential side effects"],
  "security_review": "security assessment",
  "breaking_changes": ["list of breaking changes or empty"]
}

Be concise. Focus on real risks, not theoretical concerns."""),
            ("human", """File: {file_path}
Affected Functions: {affected}

Diff:
{diff}

Analyze the impact:""")
        ])
        
        try:
            response = self.llm.invoke(
                prompt.format_messages(
                    file_path=file_path,
                    affected=", ".join(affected) if affected else "unknown",
                    diff=diff[:2000]  # Limit diff size
                )
            )
            
            import json
            
            # Extract JSON from response
            content = response.content
            
            # Handle markdown code blocks
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            result = json.loads(content.strip())
            
            return result
        
        except Exception as e:
            print(f"   ⚠️  LLM analysis failed: {e}")
            
            # Fallback to heuristic analysis
            return self._heuristic_analysis(diff)
    
    def _heuristic_analysis(self, diff: str) -> Dict[str, Any]:
        """
        Fallback heuristic analysis when LLM fails
        
        Args:
            diff: Code diff
        
        Returns:
            Basic impact analysis
        """
        side_effects = []
        security_concerns = []
        
        # Check for common patterns
        if 'import' in diff.lower():
            side_effects.append("New dependencies added - verify compatibility")
        
        if 'timeout' in diff.lower():
            side_effects.append("Timeout behavior changed - may affect latency")
        
        if 'retry' in diff.lower():
            side_effects.append("Retry mechanism added - may increase request duration")
        
        if 'except' in diff.lower():
            side_effects.append("Error handling modified - verify exception propagation")
        
        if 'password' in diff.lower() or 'token' in diff.lower() or 'key' in diff.lower():
            security_concerns.append("Potential credential handling - review for security")
        
        if 'input' in diff.lower() or 'request.' in diff.lower():
            security_concerns.append("User input handling - verify validation")
        
        security_review = (
            "Security concerns identified: " + "; ".join(security_concerns)
            if security_concerns
            else "No obvious security concerns"
        )
        
        return {
            "side_effects": side_effects if side_effects else ["Unable to analyze - manual review recommended"],
            "security_review": security_review,
            "breaking_changes": []
        }
    
    def _calculate_risk(self, original: str, fixed: str) -> str:
        """
        Calculate regression risk score
        
        Args:
            original: Original code
            fixed: Fixed code
        
        Returns:
            "Low", "Medium", or "High"
        """
        
        # Calculate diff size
        diff = list(difflib.unified_diff(
            original.splitlines(),
            fixed.splitlines()
        ))
        
        diff_lines = len(diff)
        
        # Calculate complexity change
        original_lines = len(original.splitlines())
        fixed_lines = len(fixed.splitlines())
        lines_changed_pct = (diff_lines / max(original_lines, 1)) * 100
        
        # Risk factors
        risk_factors = 0
        
        # Factor 1: Diff size
        if diff_lines > 100:
            risk_factors += 2
        elif diff_lines > 50:
            risk_factors += 1
        
        # Factor 2: Percentage changed
        if lines_changed_pct > 50:
            risk_factors += 2
        elif lines_changed_pct > 20:
            risk_factors += 1
        
        # Factor 3: New imports (adds dependencies)
        if '+import ' in '\n'.join(diff):
            risk_factors += 1
        
        # Factor 4: Exception handling changes
        if any('+except' in line or '-except' in line for line in diff):
            risk_factors += 1
        
        # Calculate risk level
        if risk_factors >= 4:
            return "High"
        elif risk_factors >= 2:
            return "Medium"
        else:
            return "Low"