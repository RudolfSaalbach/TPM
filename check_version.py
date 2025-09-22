#!/usr/bin/env python3
"""
Version Checker for Chronos Engine
Compares local and production server versions
"""

import requests
import json
import sys
from datetime import datetime

def check_version(url, name="Server"):
    """Check version for a given server URL"""
    try:
        response = requests.get(f"{url}/version", timeout=5)
        if response.status_code == 200:
            version_data = response.json()
            print(f"\n{name} ({url}):")
            print(f"  Version: {version_data.get('version', 'unknown')}")
            print(f"  Timestamp: {version_data.get('timestamp', 'unknown')}")

            build_info = version_data.get('build_info', {})
            if build_info:
                print("  Build Info:")
                for key, value in build_info.items():
                    print(f"    {key}: {value}")

            return version_data
        else:
            print(f"\n{name} ({url}): ERROR - HTTP {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"\n{name} ({url}): ERROR - {e}")
        return None

def main():
    """Main version checking function"""
    print("Chronos Engine Version Checker")
    print("=" * 40)
    print(f"Check time: {datetime.now().isoformat()}")

    # Check local development server
    local_version = check_version("http://localhost:8080", "Local Development")

    # Check production server (if provided as argument)
    if len(sys.argv) > 1:
        production_url = sys.argv[1]
        production_version = check_version(production_url, "Production Server")

        # Compare versions
        if local_version and production_version:
            local_ver = local_version.get('version', '')
            prod_ver = production_version.get('version', '')

            print(f"\n{'='*40}")
            print("VERSION COMPARISON:")
            if local_ver != prod_ver:
                print(f"⚠️  VERSION MISMATCH DETECTED!")
                print(f"   Local:      {local_ver}")
                print(f"   Production: {prod_ver}")
                if 'legacy' in prod_ver:
                    print("   → Production appears to be running an older version without version tracking")
                else:
                    print("   → Versions differ - consider updating production")
            else:
                print(f"✅ Versions match: {local_ver}")
    else:
        print(f"\nUsage: {sys.argv[0]} <production-server-url>")
        print(f"Example: {sys.argv[0]} http://your-server.com:8080")

if __name__ == "__main__":
    main()