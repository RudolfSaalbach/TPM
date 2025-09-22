"""
Tests für Hardcoded Data Validation
Sicherstellen, dass keine hardcoded Werte außerhalb von Config-Dateien existieren
"""

import os
import re
from pathlib import Path
import pytest


class TestHardcodedDataValidation:
    """Test dass keine hardcoded Daten außerhalb Config-Dateien existieren"""

    def test_no_hardcoded_api_keys_in_templates(self):
        """Sicherstellen, dass Templates keine hardcoded API-Keys haben"""
        template_dir = Path("templates")
        if not template_dir.exists():
            pytest.skip("Templates directory not found")

        # Prüfe nur echte hardcoded Strings, nicht Template-Fallbacks
        hardcoded_patterns = [
            r"'super-secret-change-me'[^}]",  # Nur echte JS-Strings, nicht Template-Fallbacks
            r"development-key-change-in-production",
            r"chronos-dev-key",
            r"test-api-key"
        ]

        violations = []
        for template_file in template_dir.glob("*.html"):
            content = template_file.read_text(encoding='utf-8')
            for pattern in hardcoded_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{template_file}: {pattern} found {len(matches)} times")

        assert not violations, f"Hardcoded API keys found in templates: {violations}"

    def test_no_hardcoded_urls_in_javascript(self):
        """Sicherstellen, dass JS keine hardcoded URLs hat"""
        static_dir = Path("static/js")
        if not static_dir.exists():
            pytest.skip("Static JS directory not found")

        hardcoded_patterns = [
            r"localhost:8080",
            r"127\.0\.0\.1:8080",
            r"http://localhost",
            r"https://localhost"
        ]

        violations = []
        for js_file in static_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8')
            for pattern in hardcoded_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{js_file}: {pattern} found {len(matches)} times")

        assert not violations, f"Hardcoded URLs found in JavaScript: {violations}"

    def test_no_hardcoded_database_urls_in_source(self):
        """Sicherstellen, dass keine hardcoded DB-URLs in Source-Code außer Config"""
        src_dir = Path("src")
        if not src_dir.exists():
            pytest.skip("Source directory not found")

        # Erlaubte Config-Dateien
        allowed_config_files = {
            "config_loader.py",
            "config_manager.py",
            "database.py",
            "database_enhanced.py"
        }

        hardcoded_patterns = [
            r"sqlite\+aiosqlite:///",
            r"postgresql://",
            r"mysql://"
        ]

        violations = []
        for py_file in src_dir.rglob("*.py"):
            if py_file.name in allowed_config_files:
                continue  # Skip erlaubte Config-Dateien

            content = py_file.read_text(encoding='utf-8')
            for pattern in hardcoded_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{py_file}: {pattern} found {len(matches)} times")

        assert not violations, f"Hardcoded database URLs found outside config: {violations}"

    def test_config_injection_in_base_template(self):
        """Teste dass base.html die zentrale Config-Injection hat"""
        base_template = Path("templates/base.html")
        if not base_template.exists():
            pytest.skip("Base template not found")

        content = base_template.read_text(encoding='utf-8')

        # Prüfe dass window.CHRONOS_CONFIG gesetzt wird
        assert "window.CHRONOS_CONFIG" in content, "Base template missing CHRONOS_CONFIG injection"
        assert "config.api.api_key" in content, "Base template missing API key injection"
        assert "config.api.host" in content, "Base template missing host injection"
        assert "config.api.port" in content, "Base template missing port injection"

    def test_dashboard_config_injection(self):
        """Teste dass Dashboard-API Config in Templates injiziert"""
        dashboard_py = Path("src/api/dashboard.py")
        if not dashboard_py.exists():
            pytest.skip("Dashboard API not found")

        content = dashboard_py.read_text(encoding='utf-8')

        # Prüfe dass load_config importiert wird
        assert "from src.config.config_loader import load_config" in content, "Dashboard missing config import"

        # Prüfe dass config in Template-Responses injiziert wird
        assert '"config": config' in content, "Dashboard missing config injection in templates"

    def test_javascript_uses_injected_config(self):
        """Teste dass JavaScript die injizierte Config verwendet"""
        main_js = Path("static/js/main.js")
        if not main_js.exists():
            pytest.skip("Main JS file not found")

        content = main_js.read_text(encoding='utf-8')

        # Prüfe dass window.CHRONOS_CONFIG verwendet wird
        assert "window.CHRONOS_CONFIG" in content, "Main JS not using injected config"

        # Prüfe dass hardcoded API-Key nur als Fallback existiert
        hardcoded_key_lines = [line for line in content.split('\n')
                              if 'development-key-change-in-production' in line]
        assert len(hardcoded_key_lines) == 0, "Main JS still has hardcoded development key"

    def test_no_production_secrets_in_main_code(self):
        """Sicherstellen, dass keine Production-Secrets im Haupt-Code stehen"""
        # Prüfe nur kritische Dateien in src/ und templates/
        include_dirs = {'src', 'templates', 'static'}
        exclude_files = {'.env', '.env.example', 'chronos.yaml', 'config_loader.py'}

        dangerous_patterns = [
            r"password\s*=\s*['\"][^'\"]{12,}['\"]",  # Lange hardcoded passwords
            r"secret\s*=\s*['\"][^'\"]{24,}['\"]",    # Lange hardcoded secrets
            r"token\s*=\s*['\"][^'\"]{32,}['\"]",     # Lange hardcoded tokens
        ]

        violations = []
        for include_dir in include_dirs:
            if not Path(include_dir).exists():
                continue

            for file_path in Path(include_dir).rglob('*'):
                if not file_path.is_file():
                    continue
                if file_path.name in exclude_files:
                    continue
                if not file_path.suffix in {'.py', '.js', '.html'}:
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8')
                    for pattern in dangerous_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            violations.append(f"{file_path}: Potential production secret found")
                except (UnicodeDecodeError, PermissionError):
                    continue

        assert not violations, f"Production secrets found in main code: {violations}"


if __name__ == "__main__":
    pytest.main([__file__])