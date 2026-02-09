"""
Agent 3: Fix Generator & PR Orchestrator

Two-Phase Workflow:
- PHASE 1 (Verification): Automatic validation, peer review, impact assessment, PR staging
- PHASE 2 (Action): On-demand PR creation after user approval

Author: Production AI Team
Version: 1.0
"""

import os
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from .validators import StaticValidator
from .reviewers import CrossAgentReviewer
from .assessors import ImpactAssessor
from .stagers import PRStager


class Agent3FixGenerator:
    """
    Agent 3: Fix Generator & PR Orchestrator
    
    Responsibilities:
    1. Generate code fixes using LLM
    2. Validate fixes (syntax, linting, imports)
    3. Request Agent 2 peer review
    4. Assess impact and risk
    5. Stage PR locally (branch + commit)
    6. Create PR on user approval
    
    Two-Phase Approach:
    - Phase 1: Verification (automatic, ~30s)
    - Phase 2: Action (on-demand, ~5s)
    """
    
    def __init__(
        self,
        repo_path: str,
        llm: Any,
        agent2_module: Optional[Any] = None,
        websocket_manager: Optional[Any] = None
    ):
        """
        Initialize Agent 3
        
        Args:
            repo_path: Path to cloned repository
            llm: LangChain LLM instance
            agent2_module: Agent 2 instance for peer review (optional)
            websocket_manager: WebSocket manager for UI updates
        """
        self.repo_path = Path(repo_path)
        self.llm = llm
        self.agent2_module = agent2_module
        self.ws_manager = websocket_manager
        
        # Initialize components
        self.validator = StaticValidator(repo_path)
        self.reviewer = CrossAgentReviewer(agent2_module)
        self.assessor = ImpactAssessor(llm)
        self.stager = PRStager(repo_path)
        
        print(f"✅ Agent 3 initialized")
        print(f"   Repo: {repo_path}")
    
    # =========================================================================
    # PHASE 1: VERIFICATION (Automatic)
    # =========================================================================
    
    async def run_verification_phase(
        self,
        session_id: str,
        agent1_analysis: Dict[str, Any],
        agent2_analysis: Dict[str, Any],
        generated_fix: str
    ) -> Dict[str, Any]:
        """
        Execute Phase 1: Verification
        
        Steps:
        1. Static validation (AST, linting, imports)
        2. Agent 2 peer review
        3. Impact & risk assessment
        4. PR staging (local branch + commit)
        5. UI notification (WebSocket)
        
        Args:
            session_id: Unique session identifier
            agent1_analysis: Agent 1 results
            agent2_analysis: Agent 2 results
            generated_fix: Fixed code from LLM
        
        Returns:
            PR data for user review:
            {
                "branch_name": str,
                "commit_sha": str,
                "pr_title": str,
                "pr_body": str,
                "diff": str,
                "validation": {...},
                "impact": {...},
                "fixed_code": str
            }
        """
        
        print("\n" + "="*80)
        print("🔧 AGENT 3: PHASE 1 - VERIFICATION")
        print("="*80)
        
        file_path = agent1_analysis.get('filePath', '')
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 1: STATIC VALIDATION
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_progress(session_id, "validation", "Running static validation...")
        
        validation_result = self.validator.validate_all(file_path, generated_fix)
        
        # Self-correct if validation fails
        if not validation_result['passed']:
            print("\n⚠️  Validation failed, attempting self-correction...")
            generated_fix = await self._self_correct(generated_fix, validation_result)
            validation_result = self.validator.validate_all(file_path, generated_fix)
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 2: CROSS-AGENT PEER REVIEW
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_progress(session_id, "review", "Agent 2 reviewing fix...")
        
        original_code = self._read_original_file(file_path)
        
        agent2_review = self.reviewer.request_review(
            original_code,
            generated_fix,
            agent2_analysis
        )
        
        validation_result['agent2_approved'] = agent2_review['approved']
        validation_result['agent2_confidence'] = agent2_review['confidence']
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 3: IMPACT & RISK ASSESSMENT
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_progress(session_id, "assessment", "Assessing impact...")
        
        impact_report = self.assessor.assess_impact(
            file_path,
            original_code,
            generated_fix,
            agent2_analysis.get('call_chain', [])
        )
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 4: PR STAGING
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_progress(session_id, "staging", "Staging PR locally...")
        
        # Create branch
        branch_name = self.stager.create_branch(
            agent1_analysis.get('incident_id', 'incident'),
            agent1_analysis.get('bug_id', 'bug')
        )
        
        # Stage changes
        self.stager.stage_changes(file_path, generated_fix)
        
        # Create commit
        commit_sha = self.stager.create_commit(
            agent1_analysis.get('incident_id', 'incident'),
            agent1_analysis.get('bug_id', 'bug'),
            agent1_analysis,
            agent2_analysis
        )
        
        # Generate PR template
        pr_body = self.stager.generate_pr_template(
            agent1_analysis,
            agent2_analysis,
            impact_report,
            validation_result
        )
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 5: PREPARE PR DATA
        # ═════════════════════════════════════════════════════════════════
        
        pr_data = {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pr_title": f"fix: {agent1_analysis.get('diagnostic_summary', 'Fix issue')[:60]}",
            "pr_body": pr_body,
            "diff": self._generate_diff(original_code, generated_fix),
            "validation": validation_result,
            "impact": impact_report,
            "fixed_code": generated_fix,
            "status": "awaiting_approval"
        }
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 6: SEND TO UI FOR REVIEW
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_review_screen(session_id, pr_data)
        
        print(f"\n✅ PHASE 1 COMPLETE")
        print(f"   Branch: {branch_name}")
        print(f"   Commit: {commit_sha[:7]}")
        print(f"   Validation: {'✅ Passed' if validation_result['passed'] else '⚠️ Issues'}")
        print(f"   Confidence: {agent2_review['confidence']:.0%}")
        print(f"   ⏸️  Awaiting user approval...")
        print("="*80 + "\n")
        
        return pr_data
    
    # =========================================================================
    # PHASE 2: ACTION (On-Demand)
    # =========================================================================
    
    async def execute_pr_creation(
        self,
        session_id: str,
        pr_data: Dict[str, Any],
        github_token: str
    ) -> Dict[str, Any]:
        """
        Execute Phase 2: PR Creation
        
        Called when user clicks "Create PR" button in UI.
        
        Steps:
        1. Push branch to GitHub
        2. Create PR via GitHub API
        3. Send notification to UI
        
        Args:
            session_id: Unique session identifier
            pr_data: PR data from Phase 1
            github_token: GitHub authentication token
        
        Returns:
            {
                "html_url": str,
                "number": int
            }
        """
        
        print("\n" + "="*80)
        print("🔧 AGENT 3: PHASE 2 - ACTION")
        print("="*80)
        
        await self._send_progress(session_id, "pushing", "Pushing branch to GitHub...")
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 1: PUSH BRANCH
        # ═════════════════════════════════════════════════════════════════
        
        branch_name = pr_data['branch_name']
        self._push_branch(branch_name)
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 2: CREATE PR
        # ═════════════════════════════════════════════════════════════════
        
        await self._send_progress(session_id, "creating_pr", "Creating pull request...")
        
        pr_result = self._create_github_pr(
            branch_name,
            pr_data['pr_title'],
            pr_data['pr_body'],
            github_token
        )
        
        print(f"\n✅ PHASE 2 COMPLETE")
        print(f"   PR #{pr_result['number']}: {pr_result['html_url']}")
        print("="*80 + "\n")
        
        return pr_result
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _read_original_file(self, file_path: str) -> str:
        """Read original file content"""
        # Normalize path
        normalized_path = file_path.lstrip('/')
        for prefix in ['app/', '/app/', 'usr/src/app/', '/usr/src/app/']:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]
        
        full_path = self.repo_path / normalized_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        with open(full_path, 'r') as f:
            return f.read()
    
    def _generate_diff(self, original: str, fixed: str) -> str:
        """Generate unified diff"""
        import difflib
        
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile='original.py',
            tofile='fixed.py'
        )
        
        return ''.join(diff)
    
    def _push_branch(self, branch_name: str) -> None:
        """Push branch to remote"""
        import subprocess
        
        print(f"\n📤 Pushing branch: {branch_name}")
        
        result = subprocess.run(
            ['git', 'push', '-u', 'origin', branch_name],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to push branch: {result.stderr}")
        
        print(f"   ✅ Branch pushed successfully")
    
    def _create_github_pr(
        self,
        branch: str,
        title: str,
        body: str,
        token: str
    ) -> Dict[str, Any]:
        """Create PR via GitHub API"""
        import requests
        
        print(f"\n📝 Creating GitHub PR...")
        
        # Extract repo info from git remote
        import subprocess
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise Exception("Failed to get git remote")
        
        remote_url = result.stdout.strip()
        
        # Parse owner/repo from URL
        # e.g., git@github.com:owner/repo.git or https://github.com/owner/repo.git
        if 'github.com' in remote_url:
            parts = remote_url.split('github.com')[-1].strip(':/')
            repo_path = parts.replace('.git', '')
        else:
            raise Exception("Not a GitHub repository")
        
        print(f"   Repository: {repo_path}")
        
        # Create PR
        response = requests.post(
            f"https://api.github.com/repos/{repo_path}/pulls",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": "main"  # or "master", configure as needed
            }
        )
        
        if response.status_code != 201:
            raise Exception(f"Failed to create PR: {response.status_code} - {response.text}")
        
        pr_data = response.json()
        
        print(f"   ✅ PR created: #{pr_data['number']}")
        
        return {
            "html_url": pr_data['html_url'],
            "number": pr_data['number']
        }
    
    async def _self_correct(
        self,
        code: str,
        validation: Dict[str, Any]
    ) -> str:
        """
        Attempt to auto-correct validation issues
        
        Uses LLM to fix syntax errors
        """
        from langchain_core.prompts import ChatPromptTemplate
        
        print("\n🔧 Self-correcting validation issues...")
        
        errors = []
        if not validation['syntax']['valid']:
            errors.append(f"Syntax error: {validation['syntax']['error']}")
        if validation['linting']['issues'].get('errors'):
            for error in validation['linting']['issues']['errors'][:3]:
                errors.append(f"Linting error: {error}")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a code fixer. Fix ONLY the syntax/linting errors. Output ONLY the corrected code."),
            ("human", """Code with errors:
```python
{code}
```

Errors to fix:
{errors}

Output corrected code:""")
        ])
        
        messages = prompt.format_messages(
            code=code,
            errors='\n'.join(errors)
        )
        
        response = await self.llm.ainvoke(messages)
        
        corrected = response.content
        if '```python' in corrected:
            corrected = corrected.split('```python')[1].split('```')[0]
        elif '```' in corrected:
            corrected = corrected.split('```')[1].split('```')[0]
        
        print("   ✅ Self-correction attempted")
        
        return corrected.strip()
    
    async def _send_progress(self, session_id: str, stage: str, message: str):
        """Send progress update via WebSocket"""
        if self.ws_manager:
            await self.ws_manager.send_message(session_id, {
                "type": "agent3_progress",
                "data": {
                    "stage": stage,
                    "message": message
                },
                "timestamp": datetime.now().isoformat()
            })
    
    async def _send_review_screen(self, session_id: str, pr_data: Dict[str, Any]):
        """Send review screen data to UI"""
        if self.ws_manager:
            await self.ws_manager.send_message(session_id, {
                "type": "agent3_review_fix",
                "data": {
                    "branch_name": pr_data['branch_name'],
                    "commit_sha": pr_data['commit_sha'],
                    "pr_title": pr_data['pr_title'],
                    "pr_body": pr_data['pr_body'],
                    "diff": pr_data['diff'],
                    "validation": {
                        "syntax_passed": pr_data['validation']['syntax']['valid'],
                        "linting_passed": pr_data['validation']['linting']['passed'],
                        "agent2_approved": pr_data['validation'].get('agent2_approved', False),
                        "confidence": pr_data['validation'].get('agent2_confidence', 0.75)
                    },
                    "impact": {
                        "regression_risk": pr_data['impact']['regression_risk'],
                        "affected_functions": len(pr_data['impact']['affected_functions']),
                        "side_effects": pr_data['impact']['side_effects']
                    }
                },
                "timestamp": datetime.now().isoformat()
            })
            
            print(f"\n📡 WebSocket: Sent 'review_fix' to UI")