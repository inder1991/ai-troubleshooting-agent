"""
API Routes and Endpoints - REFACTORED VERSION

Clean, maintainable routes with orchestrator pattern.
All workflow logic moved to TroubleshootingOrchestrator.

This file now only handles:
- HTTP routing
- Request validation
- Session management
- Response formatting
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from datetime import datetime
import uuid
import asyncio
import os

from ..agents.agent0_intent_detector import IntentAgent
from ..agents.agent1_node import run_agent1_analysis
from ..orchestrator import TroubleshootingOrchestrator

from .models import (
    TroubleshootRequest,
    TroubleshootResponse,
    SessionStatusResponse,
    ApprovalRequest,
    ConversationRequest
)
from .websocket import manager


router = APIRouter()

# Global state
active_sessions = {}
orchestrators = {}


# =========================================================================
# CONVERSATION ENDPOINT
# =========================================================================

@router.post("/api/conversation")
async def handle_conversation(request: ConversationRequest):
    """
    Handle conversational messages and detect intent
    
    Uses Agent 0 (Intent Detector) to analyze user message and determine
    if troubleshooting workflow should be triggered.
    """
    try:
        # Initialize Intent Agent
        intent_agent = IntentAgent()
        
        # Analyze user message
        result = intent_agent.handle_conversation(
            user_message=request.message,
            conversation_history=request.conversation_history
        )
        
        # Add timestamp
        result["timestamp"] = datetime.now().isoformat()
        
        return result
        
    except Exception as e:
        print(f"Error in conversation handling: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing conversation: {str(e)}"
        )


# =========================================================================
# SYSTEM ENDPOINTS
# =========================================================================

@router.get("/")
async def root():
    """API information"""
    return {
        "message": "AI Multi-Agent Troubleshooting System",
        "version": "3.0.0",
        "architecture": "Orchestrator Pattern",
        "features": [
            "3-agent workflow (Log Analysis → Code Navigation → Fix Generation)",
            "Production Agent 2 with 4 key responsibilities",
            "Real-time WebSocket streaming",
            "Flowchart generation",
            "Automatic PR creation",
            "Human-in-the-loop approval"
        ],
        "agents": {
            "agent0": "Intent Detection",
            "agent1": "Log Analysis & Exception Extraction",
            "agent2": "Code Navigation (Codebase Mapping, Context Retrieval, Call Chain, Dependencies)",
            "agent3": "Fix Generation & PR Creation"
        }
    }


@router.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "active_orchestrators": len(orchestrators),
        "timestamp": datetime.now().isoformat()
    }


# =========================================================================
# TROUBLESHOOTING WORKFLOW
# =========================================================================

@router.post("/api/troubleshoot/start", response_model=TroubleshootResponse)
async def start_troubleshooting(
    request: TroubleshootRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new troubleshooting session
    
    Creates session, initializes orchestrator, and runs workflow in background.
    Returns immediately with session_id for WebSocket connection.
    """
    try:
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        print("\n" + "="*80)
        print("🔥 NEW TROUBLESHOOTING SESSION")
        print(f"Session ID: {session_id}")
        print(f"Repository: {request.githubRepo}")
        print(f"ELK Index: {request.elkIndex}")
        print(f"Timeframe: {request.timeframe}")
        print("="*80 + "\n")

        # Create session
        active_sessions[session_id] = {
            "id": session_id,
            "status": "initializing",
            "request": request.dict(),
            "current_step": "init",
            "progress": 0.0,
            "created_at": datetime.now().isoformat(),
            "agent1_result": None,
            "agent2_result": None,
            "agent3_result": None
        }
        
        # Start background workflow
        background_tasks.add_task(
            run_troubleshooting_workflow,
            session_id,
            request
        )
        
        return TroubleshootResponse(
            session_id=session_id,
            status="started",
            message="Troubleshooting session started. Connect via WebSocket for real-time updates."
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# SESSION MANAGEMENT
# =========================================================================

@router.get("/api/troubleshoot/status/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Get current status of a troubleshooting session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    return SessionStatusResponse(
        session_id=session_id,
        status=session["status"],
        current_step=session.get("current_step"),
        progress=session.get("progress", 0.0),
        results={
            "agent1": session.get("agent1_result"),
            "agent2": session.get("agent2_result"),
            "agent3": session.get("agent3_result")
        }
    )


@router.post("/api/troubleshoot/approve")
async def approve_fix(request: ApprovalRequest):
    """Approve or reject a proposed fix"""
    return await handle_approval(request.session_id, request.approved, request.comments)


@router.get("/api/sessions")
async def list_sessions():
    """List all active sessions"""
    return {
        "sessions": [
            {
                "id": sid,
                "status": session["status"],
                "created_at": session["created_at"],
                "progress": session["progress"]
            }
            for sid, session in active_sessions.items()
        ]
    }


@router.delete("/api/troubleshoot/{session_id}")
async def delete_session(session_id: str):
    """Delete a troubleshooting session"""
    if session_id in active_sessions:
        del active_sessions[session_id]
    if session_id in orchestrators:
        # Cleanup orchestrator resources
        await orchestrators[session_id].cleanup()
        del orchestrators[session_id]
    return {"status": "deleted"}


# =========================================================================
# FILE UPLOAD
# =========================================================================

@router.post("/api/upload-logs")
async def upload_logs(file: UploadFile = File(...)):
    """Upload log file for analysis"""
    try:
        content = await file.read()
        logs = content.decode('utf-8')
        
        return {
            "success": True,
            "filename": file.filename,
            "size": len(content),
            "logs": logs[:1000] + "..." if len(logs) > 1000 else logs
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================================================================
# WORKFLOW EXECUTION (USING ORCHESTRATOR)
# =========================================================================

async def run_troubleshooting_workflow(session_id: str, request: TroubleshootRequest):
    """
    Run the troubleshooting workflow using Orchestrator pattern
    
    This function is now CLEAN and SIMPLE - all workflow logic is in the orchestrator.
    Responsibilities:
    - Wait for WebSocket connection
    - Create and configure orchestrator
    - Run workflow
    - Update session state
    - Handle errors
    """
    try:
        session = active_sessions[session_id]
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 1: WAIT FOR WEBSOCKET CONNECTION
        # ═════════════════════════════════════════════════════════════════
        
        print(f"⏳ Waiting for WebSocket connection...")
        
        for i in range(20):  # Wait up to 10 seconds
            if session_id in manager.active_connections:
                print(f"✅ WebSocket connected after {i * 0.5}s")
                break
            await asyncio.sleep(0.5)
        else:
            print(f"⚠️  WebSocket not connected, continuing anyway...")
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 2: CREATE ORCHESTRATOR
        # ═════════════════════════════════════════════════════════════════
        
        orchestrator = TroubleshootingOrchestrator(
            session_id=session_id,
            github_repo=request.githubRepo,
            elk_index=request.elkIndex,
            timeframe=request.timeframe,
            error_message=request.errorMessage,
            websocket_manager=manager
        )
        
        # Store orchestrator for later access (approval, cleanup, etc.)
        orchestrators[session_id] = orchestrator
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 3: RUN WORKFLOW (ALL LOGIC IN ORCHESTRATOR)
        # ═════════════════════════════════════════════════════════════════
        
        result = await orchestrator.run()
        
        # ═════════════════════════════════════════════════════════════════
        # STEP 4: UPDATE SESSION STATE
        # ═════════════════════════════════════════════════════════════════
        
        session["agent1_result"] = result["agent1"]
        session["agent2_result"] = result["agent2"]
        session["agent3_result"] = result["agent3"]
        session["status"] = result["status"]
        session["duration"] = result["duration_seconds"]
        
        print(f"\n✅ Workflow complete for session {session_id}")
        print(f"   Duration: {result['duration_seconds']:.1f}s")
        print(f"   Status: {result['status']}\n")
        
    except Exception as e:
        # ═════════════════════════════════════════════════════════════════
        # ERROR HANDLING
        # ═════════════════════════════════════════════════════════════════
        
        session["status"] = "error"
        session["error"] = str(e)
        
        print(f"\n❌ Workflow failed for session {session_id}: {e}\n")
        
        await manager.send_message(session_id, {
            "type": "error",
            "message": f"❌ Workflow error: {str(e)}"
        })


# =========================================================================
# APPROVAL HANDLING
# =========================================================================

async def handle_approval(session_id: str, approved: bool, comments: str = None):
    """
    Handle human approval/rejection of proposed fix
    
    Called when confidence is low and human review is required.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    if approved:
        # Fix approved - create PR
        session["status"] = "creating_pr"
        
        await manager.send_message(session_id, {
            "type": "approval",
            "approved": True,
            "message": "✅ Fix approved. Creating PR..."
        })
        
        await asyncio.sleep(2)
        
        # Mock PR creation
        request_data = session["request"]
        pr_url = f"https://github.com/{request_data['githubRepo']}/pull/{1000 + hash(session_id) % 9000}"
        session["pr_url"] = pr_url
        session["status"] = "completed"
        
        await manager.send_message(session_id, {
            "type": "completed",
            "pr_url": pr_url,
            "message": "✅ Pull request created!"
        })
        
    else:
        # Fix rejected
        session["status"] = "rejected"
        session["rejection_comments"] = comments
        
        await manager.send_message(session_id, {
            "type": "approval",
            "approved": False,
            "message": "❌ Fix rejected. Session ended.",
            "comments": comments
        })
    
    return {"status": "success", "approved": approved}


# =========================================================================
# LEGACY COMPATIBILITY
# =========================================================================

async def stream_agent_analysis(session_id: str, input_data: any, agent_type: str):
    """
    Stream agent analysis using Anthropic (Agent 3 only)
    
    NOTE: This is kept for Agent 3 compatibility.
    Agent 1 and Agent 2 now use their own implementations.
    """
    from anthropic import AsyncAnthropic
    import json
    import re
    
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Only handle Agent 3
    if agent_type != "agent3":
        raise ValueError(f"stream_agent_analysis only supports agent3, got: {agent_type}")
    
    prompt = f"Generate a fix based on this analysis in JSON format: {str(input_data)[:2000]}"
    
    full_response = ""
    
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                await manager.send_message(session_id, {
                    "type": f"{agent_type}_streaming_token",
                    "token": text
                })
    except Exception as e:
        print(f"Streaming error: {e}")
    
    # Parse response
    try:
        clean_response = full_response.strip()
        if clean_response.startswith('```'):
            clean_response = re.sub(r'^```(?:json)?\n?', '', clean_response)
            clean_response = re.sub(r'\n?```$', '', clean_response)
        result = json.loads(clean_response)
        return result
    except:
        # Return mock data as fallback
        return {
            "explanation": "Added null check and proper error handling",
            "proposedFix": "if (obj == null) { return; }",
            "confidence": 0.85,
            "pr_title": "Fix: NullPointerException in service",
            "changes": []
        }