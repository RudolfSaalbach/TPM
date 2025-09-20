"""
Production-ready Configuration Manager for Chronos Engine
Secure configuration loading with environment variable support and validation
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from cryptography.fernet import Fernet


class ConfigError(Exception):
    """Configuration-related error"""
    pass


class EnvironmentType(Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str = "sqlite+aiosqlite:///./data/chronos.db"
    max_connections: int = 20
    pool_timeout: int = 30
    echo_sql: bool = False
    backup_enabled: bool = True
    backup_schedule: str = "0 2 * * *"  # Daily at 2 AM

    def validate(self):
        """Validate database configuration"""
        if not self.url:
            raise ConfigError("Database URL is required")
        if self.max_connections < 1:
            raise ConfigError("Database max_connections must be at least 1")
        if self.pool_timeout < 1:
            raise ConfigError("Database pool_timeout must be at least 1")


@dataclass
class SecurityConfig:
    """Security configuration"""
    api_key_expiry_days: int = 365
    session_timeout_minutes: int = 480  # 8 hours
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 30
    rate_limit_per_hour: int = 1000
    require_https: bool = False  # Set to True in production
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    secret_key: Optional[str] = None
    encryption_enabled: bool = True

    def validate(self):
        """Validate security configuration"""
        if self.api_key_expiry_days < 1:
            raise ConfigError("API key expiry must be at least 1 day")
        if self.session_timeout_minutes < 1:
            raise ConfigError("Session timeout must be at least 1 minute")
        if self.rate_limit_per_hour < 1:
            raise ConfigError("Rate limit must be at least 1 per hour")


@dataclass
class SMTPConfig:
    """SMTP configuration"""
    host: str = "localhost"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30
    from_email: str = "noreply@chronos.local"
    from_name: str = "Chronos Engine"

    def validate(self):
        """Validate SMTP configuration"""
        if not self.host:
            raise ConfigError("SMTP host is required")
        if not (1 <= self.port <= 65535):
            raise ConfigError("SMTP port must be between 1 and 65535")
        if not self.from_email:
            raise ConfigError("SMTP from_email is required")


@dataclass
class APIConfig:
    """API configuration"""
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    workers: int = 1
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    max_request_size: int = 16 * 1024 * 1024  # 16MB
    timeout: int = 30

    def validate(self):
        """Validate API configuration"""
        if not (1 <= self.port <= 65535):
            raise ConfigError("API port must be between 1 and 65535")
        if self.workers < 1:
            raise ConfigError("API workers must be at least 1")
        if self.max_request_size < 1024:
            raise ConfigError("Max request size must be at least 1KB")


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_enabled: bool = True
    file_path: str = "logs/chronos.log"
    file_max_size: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5
    console_enabled: bool = True

    def validate(self):
        """Validate logging configuration"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level.upper() not in valid_levels:
            raise ConfigError(f"Log level must be one of: {valid_levels}")
        if self.file_max_size < 1024:
            raise ConfigError("Log file max size must be at least 1KB")


@dataclass
class IntegrationConfig:
    """Integration configuration"""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_chats: List[int] = field(default_factory=list)

    n8n_enabled: bool = False
    n8n_webhook_base_url: str = ""
    n8n_webhook_secret: str = ""

    def validate(self):
        """Validate integration configuration"""
        if self.telegram_enabled and not self.telegram_bot_token:
            raise ConfigError("Telegram bot token is required when Telegram is enabled")
        if self.n8n_enabled and not self.n8n_webhook_base_url:
            raise ConfigError("n8n webhook base URL is required when n8n is enabled")


@dataclass
class ChronosConfig:
    """Main configuration class"""
    environment: EnvironmentType = EnvironmentType.DEVELOPMENT
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    smtp: SMTPConfig = field(default_factory=SMTPConfig)
    api: APIConfig = field(default_factory=APIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    integrations: IntegrationConfig = field(default_factory=IntegrationConfig)

    def validate(self):
        """Validate entire configuration"""
        self.database.validate()
        self.security.validate()
        self.smtp.validate()
        self.api.validate()
        self.logging.validate()
        self.integrations.validate()

        # Environment-specific validations
        if self.environment == EnvironmentType.PRODUCTION:
            if self.api.debug:
                raise ConfigError("Debug mode must be disabled in production")
            if not self.security.require_https:
                logging.warning("HTTPS is recommended in production")
            if "*" in self.security.allowed_origins:
                logging.warning("Wildcard CORS origins are not recommended in production")


class ConfigManager:
    """Configuration manager with secure loading and validation"""

    def __init__(self, config_file: Optional[str] = None,
                 env_prefix: str = "CHRONOS_"):
        self.config_file = config_file or self._find_config_file()
        self.env_prefix = env_prefix
        self.logger = logging.getLogger(__name__)
        self._config: Optional[ChronosConfig] = None
        self._encrypted_fields = {
            'database.url', 'smtp.password', 'security.secret_key',
            'integrations.telegram_bot_token', 'integrations.telegram_webhook_secret',
            'integrations.n8n_webhook_secret'
        }

    def _find_config_file(self) -> Optional[str]:
        """Find configuration file in standard locations"""
        possible_files = [
            "config.yaml",              # NEW: Unified config at root
            "chronos.yaml",
            "chronos.yml",
            "config/chronos.yaml",      # Legacy location
            "config/chronos.yml",
            "/etc/chronos/config.yaml",
            "/etc/chronos/chronos.yaml"
        ]

        for file_path in possible_files:
            if Path(file_path).exists():
                return file_path

        return None

    def load_config(self) -> ChronosConfig:
        """Load and validate configuration from file and environment"""
        try:
            # Start with default configuration
            config_dict = {}

            # Load from YAML file if it exists
            if self.config_file and Path(self.config_file).exists():
                config_dict = self._load_from_file(self.config_file)
                self.logger.info(f"Loaded configuration from {self.config_file}")

            # Override with environment variables
            env_overrides = self._load_from_environment()
            config_dict = self._deep_merge(config_dict, env_overrides)

            # Decrypt sensitive fields
            config_dict = self._decrypt_sensitive_fields(config_dict)

            # Create configuration object
            self._config = self._dict_to_config(config_dict)

            # Validate configuration
            self._config.validate()

            self.logger.info(f"Configuration loaded successfully for environment: {self._config.environment.value}")
            return self._config

        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise ConfigError(f"Configuration loading failed: {e}")

    def _load_from_file(self, file_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.endswith(('.yaml', '.yml')):
                    return yaml.safe_load(f) or {}
                elif file_path.endswith('.json'):
                    return json.load(f) or {}
                else:
                    raise ConfigError(f"Unsupported config file format: {file_path}")

        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in config file: {e}")
        except IOError as e:
            raise ConfigError(f"Cannot read config file: {e}")

    def _load_from_environment(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        config_dict = {}

        # Define environment variable mappings
        env_mappings = {
            f"{self.env_prefix}ENVIRONMENT": "environment",
            f"{self.env_prefix}DB_URL": "database.url",
            f"{self.env_prefix}DATABASE_URL": "database.url",
            f"{self.env_prefix}DB_MAX_CONNECTIONS": "database.max_connections",
            f"{self.env_prefix}API_HOST": "api.host",
            f"{self.env_prefix}API_PORT": "api.port",
            f"{self.env_prefix}API_DEBUG": "api.debug",
            f"{self.env_prefix}SECURITY_REQUIRE_HTTPS": "security.require_https",
            f"{self.env_prefix}SECURITY_SECRET_KEY": "security.secret_key",
            f"{self.env_prefix}SMTP_HOST": "smtp.host",
            f"{self.env_prefix}SMTP_PORT": "smtp.port",
            f"{self.env_prefix}SMTP_USERNAME": "smtp.username",
            f"{self.env_prefix}SMTP_PASSWORD": "smtp.password",
            f"{self.env_prefix}SMTP_FROM_EMAIL": "smtp.from_email",
            f"{self.env_prefix}LOG_LEVEL": "logging.level",
            f"{self.env_prefix}LOG_FILE_PATH": "logging.file_path",
            f"{self.env_prefix}TELEGRAM_BOT_TOKEN": "integrations.telegram_bot_token",
            f"{self.env_prefix}N8N_WEBHOOK_URL": "integrations.n8n_webhook_base_url",
        }

        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert value to appropriate type
                value = self._convert_env_value(value, config_path)
                self._set_nested_value(config_dict, config_path, value)

        return config_dict

    def _convert_env_value(self, value: str, config_path: str) -> Any:
        """Convert environment variable string to appropriate type"""
        # Boolean values
        if config_path.endswith(('debug', 'enabled', 'require_https', 'use_tls', 'use_ssl')):
            return value.lower() in ('true', '1', 'yes', 'on')

        # Integer values
        if config_path.endswith(('port', 'max_connections', 'timeout', 'workers')):
            try:
                return int(value)
            except ValueError:
                raise ConfigError(f"Invalid integer value for {config_path}: {value}")

        # List values (comma-separated)
        if config_path.endswith(('allowed_chats', 'cors_origins', 'allowed_origins')):
            return [item.strip() for item in value.split(',') if item.strip()]

        # String values
        return value

    def _set_nested_value(self, config_dict: Dict[str, Any], path: str, value: Any):
        """Set nested dictionary value using dot notation"""
        keys = path.split('.')
        current = config_dict

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _decrypt_sensitive_fields(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive configuration fields"""
        # This would implement field-level encryption for sensitive data
        # For now, just return as-is
        return config_dict

    def _dict_to_config(self, config_dict: Dict[str, Any]) -> ChronosConfig:
        """Convert dictionary to configuration object"""
        try:
            # Handle environment enum
            env_str = config_dict.get('environment', 'development')
            if isinstance(env_str, str):
                environment = EnvironmentType(env_str.lower())
            else:
                environment = EnvironmentType.DEVELOPMENT

            # Create sub-configurations
            db_config = DatabaseConfig(**config_dict.get('database', {}))
            security_config = SecurityConfig(**config_dict.get('security', {}))
            smtp_config = SMTPConfig(**config_dict.get('smtp', {}))
            api_config = APIConfig(**config_dict.get('api', {}))
            logging_config = LoggingConfig(**config_dict.get('logging', {}))
            integrations_config = IntegrationConfig(**config_dict.get('integrations', {}))

            return ChronosConfig(
                environment=environment,
                database=db_config,
                security=security_config,
                smtp=smtp_config,
                api=api_config,
                logging=logging_config,
                integrations=integrations_config
            )

        except TypeError as e:
            raise ConfigError(f"Invalid configuration structure: {e}")

    def save_config(self, config: ChronosConfig, file_path: Optional[str] = None):
        """Save configuration to file"""
        if not file_path:
            file_path = self.config_file or "config.yaml"

        try:
            # Convert to dictionary
            config_dict = self._config_to_dict(config)

            # Encrypt sensitive fields
            config_dict = self._encrypt_sensitive_fields(config_dict)

            # Ensure directory exists
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)

            # Set secure file permissions
            os.chmod(file_path, 0o600)

            self.logger.info(f"Configuration saved to {file_path}")

        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}")

    def _config_to_dict(self, config: ChronosConfig) -> Dict[str, Any]:
        """Convert configuration object to dictionary"""
        # This would implement proper serialization
        # For now, a simplified version
        return {
            'environment': config.environment.value,
            'database': {
                'url': config.database.url,
                'max_connections': config.database.max_connections,
                'pool_timeout': config.database.pool_timeout,
                'echo_sql': config.database.echo_sql,
                'backup_enabled': config.database.backup_enabled,
                'backup_schedule': config.database.backup_schedule
            },
            'api': {
                'host': config.api.host,
                'port': config.api.port,
                'debug': config.api.debug,
                'workers': config.api.workers,
                'cors_origins': config.api.cors_origins
            },
            'security': {
                'api_key_expiry_days': config.security.api_key_expiry_days,
                'require_https': config.security.require_https,
                'rate_limit_per_hour': config.security.rate_limit_per_hour
            },
            'smtp': {
                'host': config.smtp.host,
                'port': config.smtp.port,
                'username': config.smtp.username,
                'from_email': config.smtp.from_email
            },
            'logging': {
                'level': config.logging.level,
                'file_enabled': config.logging.file_enabled,
                'file_path': config.logging.file_path
            }
        }

    def _encrypt_sensitive_fields(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive fields in configuration"""
        # This would implement field-level encryption
        # For now, just return as-is
        return config_dict

    def get_config(self) -> ChronosConfig:
        """Get current configuration"""
        if not self._config:
            raise ConfigError("Configuration not loaded")
        return self._config

    def reload_config(self) -> ChronosConfig:
        """Reload configuration from file and environment"""
        self._config = None
        return self.load_config()


# Global configuration manager
config_manager = ConfigManager()


def load_config() -> ChronosConfig:
    """Load configuration using global manager"""
    return config_manager.load_config()


def get_config() -> ChronosConfig:
    """Get current configuration"""
    return config_manager.get_config()


# Example configuration file template
CONFIG_TEMPLATE = """
# Chronos Engine Configuration
environment: development

database:
  url: sqlite+aiosqlite:///./data/chronos.db
  max_connections: 20
  pool_timeout: 30
  echo_sql: false
  backup_enabled: true
  backup_schedule: "0 2 * * *"

api:
  host: 0.0.0.0
  port: 8080
  debug: false
  workers: 1
  cors_origins: ["*"]
  max_request_size: 16777216  # 16MB
  timeout: 30

security:
  api_key_expiry_days: 365
  session_timeout_minutes: 480
  max_failed_attempts: 5
  lockout_duration_minutes: 30
  rate_limit_per_hour: 1000
  require_https: false
  allowed_origins: ["*"]
  encryption_enabled: true

smtp:
  host: localhost
  port: 587
  username: ""
  password: ""
  use_tls: true
  use_ssl: false
  timeout: 30
  from_email: noreply@chronos.local
  from_name: Chronos Engine

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_enabled: true
  file_path: logs/chronos.log
  file_max_size: 10485760  # 10MB
  file_backup_count: 5
  console_enabled: true

integrations:
  telegram_enabled: false
  telegram_bot_token: ""
  telegram_webhook_secret: ""
  telegram_allowed_chats: []

  n8n_enabled: false
  n8n_webhook_base_url: ""
  n8n_webhook_secret: ""
"""