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
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from sqlalchemy import select, text

# Import configuration
from src.config.config_loader import load_config

# Import core components
from src.core.database import db_service
from src.core.scheduler import ChronosScheduler

# Import API routes (new modular structure)
from src.api import events, caldav, sync, commands, admin
from src.api.dependencies import init_api_dependencies
from src.api.error_handling import (
    api_error_handler, http_exception_handler, validation_exception_handler,
    general_exception_handler, APIError
)
from src.api.dashboard import ChronosDashboard
from src.api.n8n_routes import n8n_webhook_api



# Initialize basic console logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Global scheduler instance for dependency injection
_scheduler_instance = None

def get_scheduler_instance():
    """Get the global scheduler instance for dependency injection"""
    return _scheduler_instance

def setup_file_logging():
    """Set up file logging after ensuring directories exist"""
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Add file handler to existing logger
    file_handler = logging.FileHandler('logs/chronos.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    logger.info("File logging initialized")

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

        # Initialize Jinja2 templates
        self.templates = Jinja2Templates(directory="templates")
        
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
        
        # Store scheduler instance globally for dependency injection
        global _scheduler_instance
        _scheduler_instance = self.scheduler

        # Initialize API dependencies
        api_key = config.get('api', {}).get('api_key', 'development-key')
        init_api_dependencies(api_key)

        # Add enhanced error handlers
        from fastapi.exceptions import RequestValidationError

        self.app.exception_handler(APIError)(api_error_handler)
        self.app.exception_handler(HTTPException)(http_exception_handler)
        # BYPASS VALIDATION - DISABLED: self.app.exception_handler(RequestValidationError)(validation_exception_handler)
        self.app.exception_handler(Exception)(general_exception_handler)

        # Register modular API routes with versioning
        self.app.include_router(events.router, prefix="/api/v1", tags=["Events & Templates"])
        self.app.include_router(caldav.router, prefix="/api/v1/caldav", tags=["CalDAV Management"])
        self.app.include_router(sync.router, prefix="/api/v1/sync", tags=["Synchronization"])
        self.app.include_router(commands.router, prefix="/api/v1/commands", tags=["Command Queue"])
        self.app.include_router(admin.router, prefix="/api/v1/admin", tags=["Administration"])

        # Initialize dashboard
        dashboard = ChronosDashboard(
            analytics_engine=self.scheduler.analytics,
            timebox_engine=self.scheduler.timebox,
            replan_engine=self.scheduler.replan
        )

        # Register dashboard and n8n routes
        self.app.include_router(dashboard.router)
        self.app.include_router(n8n_webhook_api.router)
        
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

        # n8n Webhooks Interface
        @self.app.get("/n8n", response_class=HTMLResponse)
        async def n8n_webhooks_interface():
            """Serve the n8n webhooks management interface"""
            try:
                interface_path = Path("templates/n8n_webhooks.html")
                if interface_path.exists():
                    return interface_path.read_text(encoding='utf-8')
                else:
                    return '''
                    <!DOCTYPE html>
                    <html>
                    <head><title>n8n Interface Not Found</title></head>
                    <body>
                        <h1>n8n Webhooks Interface Not Found</h1>
                        <p>The n8n webhooks interface template file is missing.</p>
                        <a href="/">Return to Home</a>
                    </body>
                    </html>
                    '''
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to load n8n interface: {e}")
        
        # Root endpoint
        @self.app.get("/", response_class=RedirectResponse)
        async def root():
            """Root endpoint - redirect to dashboard"""
            return RedirectResponse(url="/dashboard", status_code=307)

    
    async def startup(self):
        """Application startup"""
        logger.info("Starting Chronos Engine v2.1...")

        # Create necessary directories first
        Path("logs").mkdir(exist_ok=True)
        Path("data").mkdir(exist_ok=True)
        Path("config").mkdir(exist_ok=True)

        # Set up file logging after directories exist
        setup_file_logging()
        
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
