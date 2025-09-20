"""
Main entry point for Chronos Engine v2.1 - Database Integration
Initializes database and starts all services
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import select, text

# Import configuration
from src.config.config_loader import load_config

# Import core components
from src.core.database import db_service
from src.core.scheduler import ChronosScheduler

# Import API routes
from src.api.routes import ChronosUnifiedAPIRoutes
from src.api.dashboard import ChronosDashboard


# Configure logging with writable location
log_dir = Path("/tmp")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/chronos.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global app instance for lifespan access
app_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown"""
    global app_instance

    # Startup
    logger.info("Starting Chronos Engine v2.1...")
    await app_instance.startup()
    logger.info("Chronos Engine v2.1 started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Chronos Engine v2.1...")
    await app_instance.shutdown()
    logger.info("Chronos Engine v2.1 shutdown complete")


class ChronosApp:
    """Main Chronos Engine Application with Database Integration"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scheduler = ChronosScheduler(config)
        
        # Create FastAPI app with lifespan
        self.app = FastAPI(
            title="Chronos Engine v2.1",
            description="Advanced Calendar Management with AI-powered optimization and Database Persistence",
            version="2.1.0",
            lifespan=lifespan
        )
        
        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=config.get('api', {}).get('cors_origins', ["*"]),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
        
        # Initialize unified API routes
        unified_routes = ChronosUnifiedAPIRoutes(
            scheduler=self.scheduler,
            api_key=config.get('api', {}).get('api_key', 'development-key')
        )
        
        # Initialize dashboard
        dashboard = ChronosDashboard(
            analytics_engine=self.scheduler.analytics,
            timebox_engine=self.scheduler.timebox,
            replan_engine=self.scheduler.replan
        )
        
        # Register routes
        self.app.include_router(unified_routes.router, prefix="/api")
        self.app.include_router(dashboard.router)
        
        # Serve static files
        static_dir = Path("static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory="static"), name="static")
        
        # Health check endpoint
        @self.app.get("/health")
        async def health_check():
            """Enhanced health check endpoint with database and FTS5 validation"""
            try:
                health_status = {
                    "status": "healthy",
                    "version": "2.1.0",
                    "timestamp": datetime.utcnow().isoformat()
                }

                # Check database connectivity
                try:
                    from src.core.models import ChronosEventDB

                    async with db_service.get_session() as session:
                        # Test a simple query using async SQLAlchemy API
                        result = await session.execute(select(ChronosEventDB).limit(1))
                        _ = result.scalars().first()

                    health_status["database"] = {
                        "status": "connected",
                        "type": "sqlite",
                        "tables": "accessible"
                    }
                except Exception as db_e:
                    health_status["database"] = {
                        "status": "error",
                        "type": "sqlite",
                        "error": str(db_e)
                    }
                    health_status["status"] = "degraded"

                # Check FTS5 support (optional)
                try:
                    async with db_service.get_session() as session:
                        result = await session.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'")
                        )
                        fts_test = result.fetchall()
                    health_status["fts5"] = {
                        "status": "available" if fts_test else "not_configured",
                        "tables": len(fts_test)
                    }
                except Exception as fts_e:
                    health_status["fts5"] = {
                        "status": "unavailable",
                        "error": str(fts_e)
                    }

                # Check scheduler status
                try:
                    scheduler_status = await self.scheduler.get_health_status()
                    health_status["scheduler"] = scheduler_status
                except Exception as sched_e:
                    health_status["scheduler"] = {
                        "status": "error",
                        "error": str(sched_e)
                    }
                    health_status["status"] = "degraded"

                # Set overall status
                if health_status["status"] == "degraded":
                    raise HTTPException(status_code=503, detail="Service degraded")

                return health_status

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")

        # GUI Client endpoint
        @self.app.get("/client", response_class=HTMLResponse)
        async def gui_client():
            """Serve the GUI client"""
            try:
                client_path = Path("templates/chronos_gui_client.html")
                if client_path.exists():
                    return client_path.read_text(encoding='utf-8')
                else:
                    return '''
                    <!DOCTYPE html>
                    <html>
                    <head><title>Client Not Found</title></head>
                    <body>
                        <h1>GUI Client Not Found</h1>
                        <p>The GUI client template file is missing.</p>
                        <a href="/">Return to Home</a>
                    </body>
                    </html>
                    '''
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to load client: {e}")
        
        # Root endpoint
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """Root endpoint - redirect to dashboard"""
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Chronos Engine v2.1</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .container { max-width: 600px; margin: 0 auto; }
                    .logo { font-size: 2.5em; color: #667eea; margin-bottom: 20px; }
                    .version { color: #666; margin-bottom: 30px; }
                    .links a { display: inline-block; margin: 10px; padding: 10px 20px; 
                              background: #667eea; color: white; text-decoration: none; 
                              border-radius: 5px; }
                    .links a:hover { background: #5a6fd8; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">Chronos Engine</div>
                    <div class="version">Version 2.1.0 - Database Edition</div>
                    <div class="links">
                        <a href="/client">GUI Client</a>
                        <a href="/dashboard">Dashboard</a>
                        <a href="/docs">API Docs</a>
                        <a href="/health">Health Check</a>
                    </div>
                    <p><strong>New in v2.1:</strong> Full SQLite database persistence, OAuth2 Google Calendar integration</p>
                </div>
            </body>
            </html>
            '''
    
    async def startup(self):
        """Application startup"""
        logger.info("Starting Chronos Engine v2.1...")
        
        # Create necessary directories with proper permissions
        Path("/tmp").mkdir(exist_ok=True)
        Path("data").mkdir(exist_ok=True)
        Path("config").mkdir(exist_ok=True)

        # Create logs directory as fallback (but use /tmp by default)
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        try:
            # Try to make it writable
            logs_dir.chmod(0o755)
        except (OSError, PermissionError):
            logger.warning("Could not set permissions on logs directory, using /tmp instead")
        
        # Initialize database
        await db_service.create_tables()
        logger.info("Database initialized")
        
        # Start scheduler
        await self.scheduler.start()
        logger.info("Scheduler started")
        
        logger.info("Chronos Engine v2.1 started successfully")
    
    async def shutdown(self):
        """Application shutdown"""
        logger.info("Shutting down Chronos Engine...")
        
        # Stop scheduler
        await self.scheduler.stop()
        logger.info("Scheduler stopped")
        
        # Close database
        await db_service.close()
        logger.info("Database closed")
        
        logger.info("Chronos Engine shutdown complete")


# Global app instance
app_instance = None


def create_app(config: Dict[str, Any] = None) -> FastAPI:
    """Create and configure the FastAPI application"""
    global app_instance

    if config is None:
        config = load_config()

    app_instance = ChronosApp(config)

    return app_instance.app


def main():
    """Main entry point"""
    try:
        # Load configuration
        config = load_config()
        
        # Create app
        app = create_app(config)
        
        # Get server config
        api_config = config.get('api', {})
        host = api_config.get('host', '0.0.0.0')
        port = api_config.get('port', 8080)
        
        logger.info(f"Starting Chronos Engine v2.1 on {host}:{port}")
        
        # Run server
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Failed to start Chronos Engine: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
