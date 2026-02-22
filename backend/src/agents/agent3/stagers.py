"""
PR Staging for Agent 3

Handles git operations:
- Branch creation
- File staging
- Commit creation
- PR template generation
"""

import subprocess
import os
from typing import Dict, Any
from pathlib import Path
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PRStager:
    """Stages PR locally without pushing"""
    
    def __init__(self, repo_path: str):
        """
        Initialize PR stager
        
        Args:
            repo_path: Path to cloned repository
        """
        self.repo_path = Path(repo_path)
    
    def create_branch(self, incident_id: str, bug_id: str) -> str:
        """
        Create git branch locally
        
        Args:
            incident_id: Incident identifier
            bug_id: Bug identifier
        
        Returns:
            branch_name
        """
        logger.info("\n" + "="*80)
        logger.info("🌳 PR STAGING: Branch Creation")
        logger.info("="*80)
        
        # Generate branch name
        timestamp = datetime.now().strftime("%Y%m%d")
        branch_name = f"fix/{incident_id}-{bug_id}-{timestamp}-3".lower()
        
        # Remove special characters
        branch_name = ''.join(c if c.isalnum() or c in '-/_' else '-' for c in branch_name)
        
        try:
            # Check current branch
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
            logger.info(f"   Current branch: {current_branch}")
            
            # Create new branch
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"   ✅ Created branch: {branch_name}")
            
            return branch_name
        
        except subprocess.CalledProcessError as e:
            logger.info(f"   ❌ Branch creation failed: {e.stderr}")
            raise
    
    def stage_changes(self, file_path: str, fixed_code: str) -> None:
        """
        Write fixed code to file and stage it
        
        Args:
            file_path: Path to file
            fixed_code: Fixed code content
        """
        logger.info("\n📝 Staging Changes...")
        
        # Normalize path
        normalized_path = file_path.lstrip('/')
        for prefix in ['app/', '/app/', 'usr/src/app/', '/usr/src/app/']:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]
        
        full_path = self.repo_path / normalized_path
        
        # Ensure directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write fixed code
        with open(full_path, 'w') as f:
            f.write(fixed_code)
        
        logger.info(f"   ✅ Wrote: {normalized_path}")
        
        # Stage file
        subprocess.run(
            ['git', 'add', normalized_path],
            cwd=self.repo_path,
            check=True
        )
        
        logger.info(f"   ✅ Staged: {normalized_path}")
    
    def create_commit(
        self,
        incident_id: str,
        bug_id: str,
        agent1_analysis: Dict[str, Any],
        agent2_analysis: Dict[str, Any]
    ) -> str:
        """
        Create git commit with structured message
        
        Args:
            incident_id: Incident identifier
            bug_id: Bug identifier
            agent1_analysis: Agent 1 results
            agent2_analysis: Agent 2 results
        
        Returns:
            commit_sha
        """
        logger.info("\n📝 Creating Commit...")
        
        # Generate commit message following Conventional Commits
        commit_msg = self._generate_commit_message(
            incident_id, bug_id, agent1_analysis, agent2_analysis
        )
        
        # Commit
        try:
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get commit SHA
            sha_result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            commit_sha = sha_result.stdout.strip()
            
            logger.info(f"   ✅ Commit created: {commit_sha[:7]}")
            
            return commit_sha
        
        except subprocess.CalledProcessError as e:
            logger.info(f"   ❌ Commit failed: {e.stderr}")
            raise
    
    def _generate_commit_message(
        self, incident_id: str, bug_id: str, agent1: Dict, agent2: Dict
    ) -> str:
        """
        Generate conventional commit message
        
        Format:
        fix(component): brief description
        
        Incident ID: INC-123
        Bug ID: BUG-4
        
        Root Cause: [from Agent 1]
        Fix: [from Agent 2]
        """
        
        # Extract component from file path
        file_path = agent1.get('filePath', 'unknown')
        component = Path(file_path).stem if file_path else 'code'
        
        # Generate subject line
        summary = agent1.get('diagnostic_summary', 'fix issue')
        if len(summary) > 60:
            summary = summary[:57] + '...'
        
        subject = f"fix({component}): {summary}"
        
        # Generate body
        root_cause = agent1.get('preliminaryRca', agent1.get('root_cause', 'N/A'))
        fix_summary = agent2.get('recommended_fix', 'N/A')
        
        # Truncate if too long
        if len(root_cause) > 200:
            root_cause = root_cause[:197] + '...'
        if len(fix_summary) > 200:
            fix_summary = fix_summary[:197] + '...'
        
        body = f"""
Incident: {incident_id}
Bug: {bug_id}

Root Cause:
{root_cause}

Fix:
{fix_summary}

Confidence: {agent2.get('confidence_score', 0):.0%}
"""
        
        return f"{subject}\n{body}"
    
    def generate_pr_template(
        self,
        agent1_analysis: Dict[str, Any],
        agent2_analysis: Dict[str, Any],
        impact_report: Dict[str, Any],
        validation_result: Dict[str, Any]
    ) -> str:
        """
        Generate PR description
        
        Args:
            agent1_analysis: Agent 1 results
            agent2_analysis: Agent 2 results
            impact_report: Impact assessment results
            validation_result: Validation results
        
        Returns:
            Formatted PR body
        """
        logger.info("\n📄 Generating PR Template...")
        
        template = f"""## 🐛 Problem

**Incident ID:** {agent1_analysis.get('incident_id', 'N/A')}  
**Bug ID:** {agent1_analysis.get('bug_id', 'N/A')}  
**Severity:** {agent1_analysis.get('severity', 'N/A')}

{agent1_analysis.get('diagnostic_summary', agent1_analysis.get('preliminaryRca', 'N/A'))}

## 🔍 Root Cause (Agent 1 Analysis)

**Location:** `{agent1_analysis.get('filePath', 'N/A')}:{agent1_analysis.get('lineNumber', 'N/A')}`  
**Function:** `{agent1_analysis.get('functionName', 'unknown')}()`

{agent1_analysis.get('preliminaryRca', agent1_analysis.get('root_cause', 'N/A'))}

## 💡 Solution (Agent 2 Recommendations)

{agent2_analysis.get('root_cause_explanation', 'N/A')}

### Implementation:
{agent2_analysis.get('recommended_fix', 'N/A')}

## 📊 Impact Assessment

**Regression Risk:** {impact_report.get('regression_risk', 'Unknown')}  
**Affected Functions:** {len(impact_report.get('affected_functions', []))}  
**Diff Size:** {impact_report.get('diff_lines', 0)} lines

### Potential Side Effects:
{self._format_list(impact_report.get('side_effects', []))}

### Security Review:
{impact_report.get('security_review', 'N/A')}

## ✅ Validation

**Syntax Check:** {'✅ Passed' if validation_result['syntax']['valid'] else '❌ Failed'}  
**Linting:** {'✅ Passed' if validation_result['linting']['passed'] else '⚠️ Warnings'}  
**Agent 2 Review:** {'✅ Approved' if validation_result.get('agent2_approved') else '⚠️ Review needed'}  
**Confidence:** {validation_result.get('agent2_confidence', 0.75):.0%}

## 🧪 Testing Checklist

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Monitoring alerts configured

## 📈 Expected Impact

- Improved error handling and reliability
- Reduced failure rate
- Better user experience

## 🔄 Rollback Plan

If issues occur:
```bash
git revert HEAD
```

---

*Generated by AI Troubleshooting System*  
*Agent 1 (Log Analysis) → Agent 2 (Code Navigation) → Agent 3 (Fix Generation)*  
*Confidence Score: {agent2_analysis.get('confidence_score', 0):.0%}*
"""
        
        logger.info("   ✅ PR template generated")
        
        return template
    
    def _format_list(self, items: list) -> str:
        """Format list for markdown"""
        if not items:
            return "- None identified"
        return '\n'.join(f"- {item}" for item in items)