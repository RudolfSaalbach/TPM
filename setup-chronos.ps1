<#
.SYNOPSIS
    Chronos Engine Setup Script
    
.DESCRIPTION
    Sets up the Chronos Engine project structure and initializes the environment.
    This script creates all necessary directories, copies configuration files,
    and prepares the system for first run.
    
.PARAMETER ProjectPath
    Path where to create the Chronos project (default: current directory)
    
.PARAMETER Environment
    Environment type: Development, Production (default: Development)
    
.EXAMPLE
    .\setup-chronos.ps1
    
.EXAMPLE
    .\setup-chronos.ps1 -ProjectPath "C:\Projects\Chronos" -Environment Production
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectPath = (Get-Location).Path,
    
    [Parameter(Mandatory = $false)]
    [ValidateSet("Development", "Production")]
    [string]$Environment = "Development"
)

# Set error handling
$ErrorActionPreference = "Stop"

# Colors for output
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    
    $originalColor = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $Color
    Write-Host $Message
    $Host.UI.RawUI.ForegroundColor = $originalColor
}

function Write-Step {
    param([string]$Message)
    Write-ColorOutput "🔧 $Message" "Cyan"
}

function Write-Success {
    param([string]$Message)
    Write-ColorOutput "✅ $Message" "Green"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "⚠️  $Message" "Yellow"
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "❌ $Message" "Red"
}

# Main setup function
function Setup-ChronosEngine {
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════════╗
║                     CHRONOS ENGINE SETUP                     ║
║                   Advanced Calendar Management                ║
║                         Version 2.0.0                        ║
╚═══════════════════════════════════════════════════════════════╝
"@ "Magenta"

    Write-Host ""
    Write-Step "Starting Chronos Engine setup..."
    Write-Host "Project Path: $ProjectPath"
    Write-Host "Environment: $Environment"
    Write-Host ""

    try {
        # Create project directory structure
        Create-ProjectStructure
        
        # Create configuration files
        Create-ConfigurationFiles
        
        # Setup Python virtual environment
        Setup-PythonEnvironment
        
        # Create sample plugins
        Create-SamplePlugins
        
        # Setup Docker files
        Setup-DockerFiles
        
        # Create startup scripts
        Create-StartupScripts
        
        # Final setup steps
        Complete-Setup
        
        Write-Success "✨ Chronos Engine setup completed successfully!"
        Show-NextSteps
        
    }
    catch {
        Write-Error "Setup failed: $($_.Exception.Message)"
        exit 1
    }
}

function Create-ProjectStructure {
    Write-Step "Creating project directory structure..."
    
    $directories = @(
        "src",
        "src/core",
        "src/api", 
        "tests",
        "tests/unit",
        "tests/integration",
        "logs",
        "data",
        "data/analytics",
        "config",
        "templates",
        "static",
        "static/css",
        "static/js",
        "plugins",
        "plugins/custom",
        "docs"
    )
    
    foreach ($dir in $directories) {
        $fullPath = Join-Path $ProjectPath $dir
        if (!(Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
            Write-Host "  📁 Created: $dir"
        }
    }
    
    Write-Success "Project structure created"
}

function Create-ConfigurationFiles {
    Write-Step "Creating configuration files..."
    
    # Create .env file
    $envContent = @"
# Chronos Engine Configuration - $Environment

# API Configuration
CHRONOS_API_KEY=chronos-dev-key-$(Get-Random -Minimum 1000 -Maximum 9999)
LOG_LEVEL=INFO

# Timezone
TZ=UTC

# Notification Configuration
CHRONOS_WEBHOOK_URL=https://webhook.site/unique-id-here
CHRONOS_WEBHOOK_API_KEY=webhook-key-$(Get-Random -Minimum 1000 -Maximum 9999)

# Environment
ENVIRONMENT=$Environment
"@

    $envPath = Join-Path $ProjectPath ".env"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Write-Host "  📄 Created: .env"
    
    # Create empty credentials.json placeholder
    $credentialsContent = @"
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR-PRIVATE-KEY\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
}
"@

    $credentialsPath = Join-Path $ProjectPath "config/credentials.json.example"
    Set-Content -Path $credentialsPath -Value $credentialsContent -Encoding UTF8
    Write-Host "  📄 Created: config/credentials.json.example"
    
    Write-Success "Configuration files created"
}

function Setup-PythonEnvironment {
    Write-Step "Setting up Python environment..."
    
    # Check if Python is installed
    try {
        $pythonVersion = python --version 2>&1
        Write-Host "  🐍 Found: $pythonVersion"
    }
    catch {
        Write-Warning "Python not found. Please install Python 3.11+ before continuing."
        return
    }
    
    # Create virtual environment
    $venvPath = Join-Path $ProjectPath "venv"
    if (!(Test-Path $venvPath)) {
        Write-Host "  📦 Creating virtual environment..."
        python -m venv $venvPath
        Write-Host "  📄 Created: venv/"
    }
    
    # Create activation script
    $activateScript = @"
@echo off
echo Activating Chronos Engine virtual environment...
call venv\Scripts\activate.bat
echo.
echo ✅ Virtual environment activated!
echo 📍 Project: Chronos Engine v2.0.0
echo 📁 Path: %CD%
echo.
echo Available commands:
echo   python -m src.main          - Start Chronos Engine
echo   python -m src.cli sync      - Sync calendar
echo   python -m src.cli status    - Show system status
echo   docker-compose up           - Start with Docker
echo.
"@

    $activatePath = Join-Path $ProjectPath "activate.bat"
    Set-Content -Path $activatePath -Value $activateScript -Encoding ASCII
    Write-Host "  📄 Created: activate.bat"
    
    Write-Success "Python environment setup completed"
}

function Create-SamplePlugins {
    Write-Step "Creating sample plugins..."
    
    # Create a sample plugin
    $samplePluginContent = @"
"""
Sample Plugin for Chronos Engine
This is a template for creating custom plugins.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any

from src.core.models import ChronosEvent
from src.core.plugin_manager import EventPlugin


class SampleEventPlugin(EventPlugin):
    """Sample event processing plugin"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @property
    def name(self) -> str:
        return "sample_event_plugin"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Sample plugin that demonstrates event processing"
    
    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin"""
        self.logger.info("Sample Event Plugin initialized")
        return True
    
    async def cleanup(self):
        """Cleanup plugin resources"""
        self.logger.info("Sample Event Plugin cleaned up")
    
    async def process_event(self, event: ChronosEvent) -> ChronosEvent:
        """Process an event - add sample tag"""
        
        if "sample" not in event.tags:
            event.tags.append("sample")
            self.logger.debug(f"Added 'sample' tag to event: {event.title}")
        
        return event
"@

    $pluginPath = Join-Path $ProjectPath "plugins/custom/sample_plugin.py"
    Set-Content -Path $pluginPath -Value $samplePluginContent -Encoding UTF8
    Write-Host "  📄 Created: plugins/custom/sample_plugin.py"
    
    Write-Success "Sample plugins created"
}

function Setup-DockerFiles {
    Write-Step "Setting up Docker configuration..."
    
    # Create docker-compose.override.yml for development
    if ($Environment -eq "Development") {
        $dockerOverrideContent = @"
version: '3.8'

services:
  chronos-engine:
    environment:
      - LOG_LEVEL=DEBUG
    volumes:
      - .:/app
    ports:
      - "8080:8080"
      - "5678:5678"  # Debug port
    command: ["python", "-m", "src.main"]
"@

        $overridePath = Join-Path $ProjectPath "docker-compose.override.yml"
        Set-Content -Path $overridePath -Value $dockerOverrideContent -Encoding UTF8
        Write-Host "  📄 Created: docker-compose.override.yml"
    }
    
    Write-Success "Docker configuration completed"
}

function Create-StartupScripts {
    Write-Step "Creating startup scripts..."
    
    # Windows batch script
    $batchScript = @"
@echo off
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                     CHRONOS ENGINE                           ║
echo ║                Advanced Calendar Management                   ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo 🚀 Starting Chronos Engine...
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo ❌ Virtual environment not found!
    echo Please run setup-chronos.ps1 first
    pause
    exit /b 1
)

REM Activate virtual environment and start
call venv\Scripts\activate.bat
python -m src.main

pause
"@

    $batchPath = Join-Path $ProjectPath "start-chronos.bat"
    Set-Content -Path $batchPath -Value $batchScript -Encoding ASCII
    Write-Host "  📄 Created: start-chronos.bat"
    
    # PowerShell startup script
    $psScript = @"
# Chronos Engine Startup Script

Write-Host @"
╔═══════════════════════════════════════════════════════════════╗
║                     CHRONOS ENGINE                           ║
║                Advanced Calendar Management                   ║
╚═══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Magenta

Write-Host ""
Write-Host "🚀 Starting Chronos Engine..." -ForegroundColor Cyan

# Change to script directory
Set-Location `$PSScriptRoot

# Check virtual environment
if (!(Test-Path "venv")) {
    Write-Host "❌ Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run setup-chronos.ps1 first" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Activate virtual environment and start
& "venv\Scripts\Activate.ps1"
python -m src.main
"@

    $psPath = Join-Path $ProjectPath "start-chronos.ps1"
    Set-Content -Path $psPath -Value $psScript -Encoding UTF8
    Write-Host "  📄 Created: start-chronos.ps1"
    
    Write-Success "Startup scripts created"
}

function Complete-Setup {
    Write-Step "Completing setup..."
    
    # Create README.md
    $readmeContent = @"
# Chronos Engine v2.0.0

Advanced Calendar Management System with AI-powered optimization.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional)
- Google Calendar API credentials (for production)

### Development Setup
1. Run the setup script:
   ``````
   .\setup-chronos.ps1
   ``````

2. Activate the environment:
   ``````
   .\activate.bat
   ``````

3. Install dependencies:
   ``````
   pip install -r requirements.txt
   ``````

4. Start the application:
   ``````
   .\start-chronos.bat
   ``````

### Docker Setup
``````
docker-compose up --build
``````

## 📚 Documentation

### API Endpoints
- **Dashboard**: http://localhost:8080/
- **API Docs**: http://localhost:8080/docs
- **Health Check**: http://localhost:8080/sync/health

### Key Features
- 📅 Google Calendar integration
- 🤖 AI-powered schedule optimization
- 📊 Advanced analytics and reporting
- ⚡ Smart timeboxing and conflict resolution
- 🔌 Plugin system for extensibility
- 📱 Web-based dashboard

### Configuration
Edit ``config/chronos.yaml`` for custom configuration.

### Environment Variables
Copy ``.env.example`` to ``.env`` and customize:
- ``CHRONOS_API_KEY``: API authentication key
- ``LOG_LEVEL``: Logging level (DEBUG, INFO, WARNING, ERROR)
- ``TZ``: Timezone setting

## 🔧 Development

### CLI Commands
``````
python -m src.cli sync          # Sync calendar
python -m src.cli analytics     # Generate analytics
python -m src.cli status        # System status
``````

### Testing
``````
pytest tests/
``````

### Plugin Development
See ``plugins/custom/sample_plugin.py`` for plugin template.

## 📦 Project Structure
``````
chronos-engine/
├── src/                    # Source code
│   ├── core/              # Core business logic
│   ├── api/               # REST API
│   └── main.py            # Application entry point
├── config/                # Configuration files
├── plugins/               # Custom plugins
├── tests/                 # Test suite
├── logs/                  # Application logs
├── data/                  # Data storage
└── docs/                  # Documentation
``````

## 🐳 Docker

### Build and Run
``````
docker-compose up --build
``````

### Production Deployment
``````
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up
``````

## 🔒 Security

- Change default API keys in production
- Use environment variables for sensitive data
- Enable HTTPS in production environments
- Regular security updates

## 📝 License

This project is licensed under the MIT License.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## ⚡ Performance

- Optimized for Docker containers
- Compatible with Raspberry Pi (ARM64)
- Low memory footprint (~100MB)
- Async processing for high throughput

## 🆘 Troubleshooting

### Common Issues

**Calendar Authentication Failed**
- Verify credentials.json is valid
- Check token.json permissions
- Re-run OAuth flow if needed

**Port Already in Use**
- Change port in docker-compose.yml
- Kill existing processes on port 8080

**Plugin Load Errors**
- Check plugin syntax
- Verify plugin dependencies
- Review logs in logs/chronos.log

### Support
- Check logs in ``logs/`` directory
- Review configuration in ``config/chronos.yaml``
- Test with ``python -m src.cli status``

---
**Chronos Engine** - Intelligent Calendar Management for the Future
"@

    $readmePath = Join-Path $ProjectPath "README.md"
    Set-Content -Path $readmePath -Value $readmeContent -Encoding UTF8
    Write-Host "  📄 Created: README.md"
    
    Write-Success "Setup completed"
}

function Show-NextSteps {
    Write-Host ""
    Write-ColorOutput @"
╔═══════════════════════════════════════════════════════════════╗
║                        NEXT STEPS                            ║
╚═══════════════════════════════════════════════════════════════╝
"@ "Green"

    Write-Host ""
    Write-Host "1. 🔧 Activate the environment:" -ForegroundColor Yellow
    Write-Host "   .\activate.bat" -ForegroundColor White
    Write-Host ""
    
    Write-Host "2. 📦 Install dependencies:" -ForegroundColor Yellow
    Write-Host "   pip install -r requirements.txt" -ForegroundColor White
    Write-Host ""
    
    Write-Host "3. ⚙️ Configure your settings:" -ForegroundColor Yellow
    Write-Host "   Edit .env and config/chronos.yaml" -ForegroundColor White
    Write-Host ""
    
    Write-Host "4. 🚀 Start Chronos Engine:" -ForegroundColor Yellow
    Write-Host "   .\start-chronos.bat" -ForegroundColor White
    Write-Host "   OR" -ForegroundColor Gray
    Write-Host "   docker-compose up" -ForegroundColor White
    Write-Host ""
    
    Write-Host "5. 🌐 Access the dashboard:" -ForegroundColor Yellow
    Write-Host "   http://localhost:8080/" -ForegroundColor White
    Write-Host ""
    
    Write-Host "6. 📚 Read the documentation:" -ForegroundColor Yellow
    Write-Host "   README.md" -ForegroundColor White
    Write-Host ""
    
    if ($Environment -eq "Production") {
        Write-Host "⚠️ PRODUCTION NOTES:" -ForegroundColor Red
        Write-Host "  - Change default API keys in .env" -ForegroundColor Yellow
        Write-Host "  - Setup proper SSL certificates" -ForegroundColor Yellow
        Write-Host "  - Configure real Google Calendar credentials" -ForegroundColor Yellow
        Write-Host "  - Review security settings" -ForegroundColor Yellow
        Write-Host ""
    }
    
    Write-ColorOutput "Happy scheduling! 🎯" "Magenta"
}

# Run the setup
Setup-ChronosEngine
