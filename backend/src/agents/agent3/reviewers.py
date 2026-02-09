"""
Cross-Agent Peer Review for Agent 3

Agent 2 verifies Agent 3's fix makes sense in the context of the codebase.
"""

from typing import Dict, Any


class CrossAgentReviewer:
    """Submits fix to Agent 2 for logic verification"""
    
    def __init__(self, agent2_module):
        """
        Initialize reviewer
        
        Args:
            agent2_module: Agent 2 instance (optional)
        """
        self.agent2 = agent2_module
    
    def request_review(
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
        print("\n" + "="*80)
        print("🔄 CROSS-AGENT PEER REVIEW")
        print("="*80)
        print("\nSubmitting fix to Agent 2 for verification...\n")
        
        # Prepare review request
        review_request = {
            "original_code": original_file,
            "proposed_fix": fixed_file,
            "original_analysis": agent2_analysis,
            "review_type": "fix_verification"
        }
        
        # Review the fix
        # Check: Does the fix address the identified issue?
        # Check: Does it break the call chain?
        # Check: Does it introduce new dependency conflicts?
        
        review_result = self._perform_review(review_request)
        
        print(f"\n📊 Agent 2 Review Result:")
        print(f"   Approved: {'✅ Yes' if review_result['approved'] else '❌ No'}")
        print(f"   Confidence: {review_result['confidence']:.0%}")
        
        if review_result['concerns']:
            print(f"\n⚠️  Concerns ({len(review_result['concerns'])}):")
            for concern in review_result['concerns']:
                print(f"   • {concern}")
        
        if review_result['recommendations']:
            print(f"\n💡 Recommendations ({len(review_result['recommendations'])}):")
            for rec in review_result['recommendations']:
                print(f"   • {rec}")
        
        print("\n" + "="*80 + "\n")
        
        return review_result
    
    def _perform_review(self, request: Dict) -> Dict[str, Any]:
        """
        Perform the actual review
        
        In production, this would call Agent 2's review method.
        For now, implements heuristic-based review.
        
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
                print("   ✅ Check 1: Retry mechanism implemented")
            else:
                concerns.append("Retry mechanism recommended but not found in fix")
        
        # Check 2: Does fix implement circuit breaker?
        if 'circuit' in agent2_recommendation or 'breaker' in agent2_recommendation:
            if 'CircuitBreaker' in fixed or 'pybreaker' in fixed:
                print("   ✅ Check 2: Circuit breaker implemented")
            else:
                concerns.append("Circuit breaker recommended but not found in fix")
        
        # Check 3: Does fix add timeout?
        if 'timeout' in agent2_recommendation:
            if 'timeout=' in fixed or 'timeout:' in fixed:
                print("   ✅ Check 3: Timeout configured")
            else:
                concerns.append("Timeout recommended but not configured in fix")
        
        # Check 4: Does fix add error handling?
        if 'error' in agent2_recommendation or 'exception' in agent2_recommendation:
            if 'try:' in fixed or 'except' in fixed:
                print("   ✅ Check 4: Error handling added")
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
            print("   ✅ Check 5: All necessary imports present")
        
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
                print("   ✅ Check 6: Code structure maintained")
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