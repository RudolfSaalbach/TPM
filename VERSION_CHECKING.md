# Chronos Engine Version Checking System

This system allows you to check which version of Chronos Engine is running on your development and production servers.

## Quick Start

### Check Local Version Only
```bash
# Direct API call
curl http://localhost:8080/version

# Using the version checker script
python check_version.py

# Windows batch file
check_version.bat
```

### Compare Local vs Production
```bash
# Using the version checker script
python check_version.py http://your-production-server.com:8080

# Windows batch file
check_version.bat http://your-production-server.com:8080
```

## Version Information Format

The `/version` endpoint returns JSON with this structure:

```json
{
    "timestamp": "2025-09-22T19:17:12.918862",
    "version": "2.1.1-COMPLETE-VERSION-TRACKING",
    "build_info": {
        "build_date": "2025-09-22T19:16:00Z",
        "commit": "856ec6262a438f1ae99ed2a60693862978fd94ad",
        "features": "create-event-modal,api-validation-bypass,responsive-layout,template-integration,version-tracking"
    }
}
```

## Legacy Servers

If a server doesn't have the VERSION file (older installations), it will return:

```json
{
    "timestamp": "2025-09-22T19:15:54.266493",
    "version": "2.1.0-legacy",
    "build_info": {
        "note": "VERSION file not found - legacy installation"
    }
}
```

## Files

- `VERSION` - Contains version information, commit hash, and feature flags
- `check_version.py` - Python script for version comparison
- `check_version.bat` - Windows batch file wrapper
- `/version` API endpoint in main.py

## Usage Scenarios

1. **Before deployment**: Check if production is running the expected version
2. **After deployment**: Verify the new version was deployed successfully
3. **Troubleshooting**: Identify version mismatches between environments
4. **Feature verification**: Check which features are available on each server

## Docker Production Example

```bash
# Check your production Docker container
python check_version.py http://your-docker-host:8080

# Should show version comparison like:
# ⚠️  VERSION MISMATCH DETECTED!
#    Local:      2.1.1-COMPLETE-VERSION-TRACKING
#    Production: 2.1.0-legacy
#    → Production appears to be running an older version
```