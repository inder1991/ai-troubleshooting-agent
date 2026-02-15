"""
API endpoints for Agent 3 PR creation (Phase 2)

These endpoints are called when user clicks "Create PR" button in UI
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import os

router = APIRouter()


class CreatePRRequest(BaseModel):
    """Request body for PR creation"""
    pr_data: Dict[str, Any]


@router.post("/troubleshoot/{session_id}/create-pr")
async def create_pull_request(
    session_id: str,
    request: Optional[CreatePRRequest] = None
):
    """
    Execute Agent 3 Phase 2: PR Creation
    
    Called when user clicks "Create PR" button in UI
    """
    
    print(f"\n📡 API: Received PR creation request for session {session_id}")
    
    # Get stored Agent 3 instance and PR data
    try:

        from .session_manager import get_session_data
        agent3_instance = get_session_data(session_id, 'agent3_instance')
        
        if not agent3_instance:
            print("session failed without data")
            raise HTTPException(
                status_code=404,
                detail="Agent 3 instance not found. Session may have expired."
            )
        pr_data = get_session_data(session_id, 'pr_data')

    
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Session manager not configured"
        )
    
    # Get GitHub token
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        raise HTTPException(
            status_code=500,
            detail="GitHub token not configured"
        )
    
    try:
        print("session started with PR creation")

        # Execute Phase 2: Push branch + Create PR
        pr_result = await agent3_instance.execute_pr_creation(
            session_id=session_id,
            pr_data=pr_data,
            github_token=github_token
        )
        
        print(f"✅ API: PR created successfully")
        print(f"   PR URL: {pr_result['html_url']}")
        print(f"   PR #: {pr_result['number']}")
        
        return {
            "success": True,
            "pr_url": pr_result['html_url'],
            "pr_number": pr_result['number'],
            "message": f"Pull request #{pr_result['number']} created successfully"
        }
    
    except Exception as e:
        print(f"❌ API: PR creation failed: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create PR: {str(e)}"
        )


@router.post("/troubleshoot/{session_id}/reject-fix")
async def reject_fix(session_id: str):
    """
    Handle fix rejection
    
    Called when user clicks "Reject" button in UI
    """
    
    print(f"\n⛔ API: Fix rejected for session {session_id}")
    
    try:
        from .session_manager import get_session_data
        pr_data = get_session_data(session_id, 'pr_data')
        
        if pr_data and pr_data.get('branch_name'):
            # Delete local branch
            import subprocess
            repo_path = get_session_data(session_id, 'repo_path')
            
            if repo_path:
                subprocess.run(
                    ['git', 'branch', '-D', pr_data['branch_name']],
                    cwd=repo_path,
                    capture_output=True
                )
                print(f"   ✅ Deleted branch: {pr_data['branch_name']}")
    
    except Exception as e:
        print(f"   ⚠️  Cleanup error: {e}")
    
    return {
        "success": True,
        "message": "Fix rejected. Branch deleted."
    }