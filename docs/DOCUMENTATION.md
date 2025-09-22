# Chronos Engine v2.2 - Documentation Index

This document provides a complete overview of all available documentation for Chronos Engine v2.2.

## 📚 Documentation Structure

### Core Documentation
- **[README.md](README.md)** - Project overview, quick start, and architecture
- **[FEATURES.md](FEATURES.md)** - Complete feature overview and capabilities
- **[DOCUMENTATION.md](DOCUMENTATION.md)** - This index (you are here)

### CalDAV Integration (Primary Focus)
- **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - Complete CalDAV setup and usage guide
- **[docs/CalDAV_API_Reference.md](docs/CalDAV_API_Reference.md)** - Full API reference for CalDAV endpoints

### Configuration
- **[config/chronos.yaml](config/chronos.yaml)** - Unified configuration file (UTF-8 encoded)
- **[demo/README.md](demo/README.md)** - Demo scripts documentation
- **[demo/create_test_events.py](demo/create_test_events.py)** - Calendar test event generation

### Development & Testing
- **[demo/](demo/)** - Demo scripts and examples for testing and development

### Requirements & Specifications
- **[RadicaleSupport.md](RadicaleSupport.md)** - Original CalDAV implementation requirements

## 🎯 Quick Navigation

### New to Chronos Engine?
1. Start with **[README.md](README.md)** for project overview
2. Read **[FEATURES.md](FEATURES.md)** to understand capabilities
3. Follow **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** for setup

### Setting Up CalDAV?
1. **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - Complete setup guide
2. **[config/examples/caldav_basic.yaml](config/examples/caldav_basic.yaml)** - Basic configuration
3. **[docs/CalDAV_API_Reference.md](docs/CalDAV_API_Reference.md)** - API usage examples

### Need API Documentation?
1. **[docs/CalDAV_API_Reference.md](docs/CalDAV_API_Reference.md)** - CalDAV-specific endpoints
2. **Interactive docs** at `http://localhost:8080/docs` when running
3. **ReDoc** at `http://localhost:8080/redoc` for alternative API docs

### Configuration Help?
1. **[config/chronos.yaml](config/chronos.yaml)** - Main configuration file
2. **[config/examples/](config/examples/)** - Environment-specific examples
3. **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - Configuration sections

## 📖 Documentation by Topic

### Architecture & Design
- **[README.md](README.md)** - Architecture overview
- **[FEATURES.md](FEATURES.md)** - Technical capabilities
- **[RadicaleSupport.md](RadicaleSupport.md)** - CalDAV integration design

### Installation & Setup
- **[README.md](README.md)** - Quick start guide
- **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - Detailed setup
- **[config/examples/](config/examples/)** - Configuration examples

### API Usage
- **[docs/CalDAV_API_Reference.md](docs/CalDAV_API_Reference.md)** - Complete API reference
- **Interactive Swagger UI** - Available at `/docs` endpoint
- **ReDoc Interface** - Available at `/redoc` endpoint

### Configuration Management
- **[config/chronos.yaml](config/chronos.yaml)** - Default configuration
- **[config/examples/](config/examples/)** - Scenario-specific configs
- **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - Configuration guide

### Troubleshooting
- **[README.md](README.md)** - Common troubleshooting
- **[docs/CalDAV_Integration_Guide.md](docs/CalDAV_Integration_Guide.md)** - CalDAV-specific issues
- **Health endpoints** - `/health` for system status

## 🔧 Development Documentation

### Code Structure
```
src/
├── api/                    # FastAPI routers and endpoints
├── core/                   # Core business logic
│   ├── source_adapter.py   # Unified backend interface
│   ├── caldav_adapter.py   # CalDAV implementation
│   ├── google_adapter.py   # Google Calendar implementation
│   ├── calendar_source_manager.py  # Backend management
│   ├── scheduler.py        # Event synchronization
│   └── calendar_repairer.py # Event processing and repair
├── config/                 # Configuration management
└── main.py                 # Application entry point

tests/
├── unit/                   # Unit tests
├── test_caldav_*.py       # CalDAV integration tests
├── conftest.py            # Test fixtures and configuration
└── README.md              # Testing documentation
```

### Testing
- **Unit Tests**: `pytest tests/unit/`
- **Integration Tests**: `pytest tests/test_caldav_*.py`
- **API Tests**: `pytest tests/test_caldav_api.py`
- **E2E Tests**: `pytest tests/test_caldav_e2e.py`

### Configuration Files
- **Main Config**: `config/chronos.yaml`
- **Examples**: `config/examples/*.yaml`
- **Test Config**: Generated dynamically in tests

## 🌟 Features by Version

### v2.2 (Current)
- ✅ **Unified Configuration** - Single `config/chronos.yaml` file with UTF-8 support
- ✅ **Enhanced Calendar Detection** - Improved CalDAV recognition and error handling
- ✅ **Demo Framework** - Complete test event generation scripts
- ✅ **Production Data Integration** - Real data throughout application
- ✅ **CalDAV/Radicale Integration** - Primary backend with full feature support
- ✅ **Unified Backend Architecture** - SourceAdapter interface
- ✅ **Event Data Portability** - JSON export/import
- ✅ **Backend-Agnostic Processing** - Unified calendar repair
- ✅ **Comprehensive API** - CalDAV management endpoints
- ✅ **Multi-Calendar Support** - Multiple CalDAV collections
- ✅ **ETag Conflict Resolution** - Safe concurrent updates

### v2.1
- CalDAV/Radicale integration foundation
- Backend switching capabilities
- Advanced event processing

### Legacy (Pre-v2.1)
- Google Calendar as primary backend
- Basic event synchronization
- Command processing system
- SQLite database foundation

## 📋 Documentation Standards

### File Organization
- **Root level**: Project overview and quick reference
- **docs/**: Detailed guides and references
- **config/**: Configuration files and examples
- **tests/**: Test documentation and examples

### Documentation Format
- **Markdown**: All documentation in GitHub-flavored markdown
- **YAML**: Configuration files with extensive comments
- **Code Examples**: Working examples in all guides
- **API Examples**: cURL and SDK examples provided

### Maintenance
- **Version Alignment**: All docs reflect current v2.1 state
- **Example Validation**: All configuration examples tested
- **Link Verification**: Internal links verified and working
- **Content Accuracy**: Regular review for technical accuracy

## 🔗 External Resources

### CalDAV Standards
- **RFC 4791**: CalDAV protocol specification
- **RFC 6578**: Collection synchronization for WebDAV
- **RFC 5545**: iCalendar format specification

### Development Tools
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org/
- **Radicale Server**: https://radicale.org/

### Calendar Applications
- **Thunderbird**: CalDAV client for desktop
- **DAVx⁵**: CalDAV sync for Android
- **Calendar.app**: macOS CalDAV support

## 📝 Contributing to Documentation

### Documentation Updates
1. Keep all docs aligned with current v2.1 architecture
2. Update examples when configuration changes
3. Maintain consistency across all documentation files
4. Test all code examples before committing

### New Documentation
1. Follow existing markdown format and style
2. Include working code examples
3. Add appropriate cross-references
4. Update this index when adding new files

---

**Documentation Version**: v2.2
**Last Updated**: 2025-09-22
**Maintainer**: Chronos Engine Team

For questions or documentation issues, please refer to the project repository or submit an issue.