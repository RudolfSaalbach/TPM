# Chronos Engine - Archived Files

This directory contains archived files from various development iterations of Chronos Engine.

## Archived Configuration Files (archive/configs/)

The following configuration files have been consolidated into the unified `config.yaml` at the project root:

- `chronos.yaml.bak` - Original main configuration
- `chronos_broken.yaml.bak` - Broken/alternative configuration
- `chronos_v22.yaml.bak` - v2.2 feature configuration
- `alembic_broken.ini` - Broken Alembic database migration configuration

**Current Configuration:** All settings are now unified in `/config/chronos.yaml`

## Archived Route Files (archive/routes/)

The following route files have been consolidated into the unified `src/api/routes.py`:

- `enhanced_routes.py` - Template management and advanced filtering routes
- `enhanced_routes_fixed.py` - Fixed async database handling + external commands
- `routes_broken.py` - Transactional atomicity routes
- `v22_routes.py` - v2.2 features (event links, availability, workflows)

**Current API:** All routes are now accessible through `ChronosUnifiedAPIRoutes` in `/src/api/routes.py`

## Migration Summary

### What was consolidated:
✅ **API Routes** - All route files merged into single unified API
✅ **Configuration** - All YAML configs merged into single `config.yaml`
✅ **Backward Compatibility** - Legacy parameters and factory functions maintained
✅ **Error Handling** - Centralized exception handling across all endpoints

### Key Benefits:
- Eliminated duplicate routes and functionality
- Unified configuration management
- Simplified deployment and maintenance
- Backward compatibility maintained
- Single point of truth for API definitions

### Archive Date
**Date:** 2025-01-20
**Version:** v2.1 CalDAV Integration
**Status:** Archived for reference

## Recovery Instructions

If you need to restore any of these files for reference or troubleshooting:

1. **For Configuration:** Copy the desired `.bak` file from `archive/configs/` and remove the `.bak` extension
2. **For Routes:** Copy route files from `archive/routes/` back to `src/api/` and update imports in `main.py`

**Note:** The current unified system is the recommended approach. These archived files are kept for reference only.