"""
FastAPI Main Application
Entry point for the API server
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .pr_endpoints import router as pr_router 
from datetime import datetime

from .routes import router
from .websocket import manager


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="AI Multi-Agent Troubleshooting API",
        description="Intelligent troubleshooting with LangGraph orchestration",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:3001"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routes
    app.include_router(router)
    app.include_router(pr_router, prefix="/api")

    # WebSocket endpoint
    @app.websocket("/ws/troubleshoot/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time updates"""
        await manager.connect(session_id, websocket)
        
        try:
            # Send initial connection message
            await manager.send_message(session_id, {
                "type": "connected",
                "message": "WebSocket connection established",
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            })
            
            # Keep connection alive and receive messages
            while True:
                try:
                    data = await websocket.receive_json()
                    
                    # Handle approval messages
                    if data.get("type") == "approval":
                        from .routes import handle_approval
                        await handle_approval(
                            session_id,
                            data.get("approved", False),
                            data.get("comments")
                        )
                
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    print(f"WebSocket error: {e}")
                    break
        
        finally:
            manager.disconnect(session_id)
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting AI Multi-Agent Troubleshooting API...")
    print("📍 API: http://localhost:8000")
    print("📖 Docs: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws/troubleshoot/{session_id}")
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
