"""
FastAPI Main Application
Entry point for the API server
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .pr_endpoints import router as pr_router
from datetime import datetime

from .routes import router
from .routes_v4 import router_v4
from .routes_v5 import router as v5_router
from .routes_profiles import router as profiles_router
from .routes_global_integrations import router as global_integrations_router
from .routes_audit import router as audit_router
from .websocket import manager
from src.utils.logger import get_logger

logger = get_logger("main")


def _init_stores():
    """Initialize database tables and seed defaults on startup."""
    from src.integrations.profile_store import ProfileStore, GlobalIntegrationStore
    from src.integrations.audit_store import AuditLogger

    profile_store = ProfileStore()
    profile_store._ensure_tables()

    gi_store = GlobalIntegrationStore()
    gi_store._ensure_tables()
    gi_store.seed_defaults()

    audit = AuditLogger()
    audit._ensure_tables()

    logger.info("Database tables initialized and defaults seeded")


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
    app.include_router(router_v4)
    app.include_router(v5_router)
    app.include_router(profiles_router)
    app.include_router(global_integrations_router)
    app.include_router(audit_router)

    @app.on_event("startup")
    async def startup():
        _init_stores()
        # Start session TTL cleanup loop
        from .routes_v4 import start_cleanup_task
        start_cleanup_task()

    # WebSocket endpoint
    @app.websocket("/ws/troubleshoot/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time updates"""
        await manager.connect(session_id, websocket)
        
        try:
            # Send initial connection message
            await manager.send_message(session_id, {
                "type": "connected",
                "data": {
                    "message": "WebSocket connection established",
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
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
