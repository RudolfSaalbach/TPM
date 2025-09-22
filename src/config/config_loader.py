"""
Configuration loader for Chronos Engine v2.1
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from environment and YAML files"""
    
    # Load environment variables
    load_dotenv()
    
    # Default configuration
    config = {
        'general': {
            'timezone': 'UTC',
            'working_hours': {
                'start': 9,
                'end': 18,
                'break_start': 12,
                'break_end': 13,
                'working_days': [0, 1, 2, 3, 4]  # Monday=0 to Friday=4
            }
        },
        'database': {
            'url': 'sqlite+aiosqlite:///./data/chronos.db',
            'echo': False
        },
        'calendar': {
            'credentials_file': 'config/credentials.json',
            'token_file': 'config/token.json',
            'default_calendar_id': 'primary',
            'sync_interval_minutes': 5
        },
        'api': {
            'host': '0.0.0.0',
            'port': 8080,
            'api_key': 'development-key-change-in-production',
            'cors_origins': ['*']
        },
        'scheduler': {
            'sync_interval': 300,  # 5 minutes
            'replan': {
                'enabled': True,
                'time': '06:00',
                'strategy': 'priority_first'
            },
            'auto_conflict_resolution': False
        },
        'analytics': {
            'retention_days': 365,
            'enable_metrics': True
        },
        'ai': {
            'optimization': {
                'enabled': True,
                'confidence_threshold': 0.7,
                'max_suggestions': 10
            },
            'timebox': {
                'enabled': True,
                'min_block_minutes': 15,
                'max_block_hours': 4,
                'focus_block_min_hours': 2
            }
        },
        'notifications': {
            'enabled': True,
            'channels': {
                'webhook': {
                    'enabled': False,
                    'url': '',
                    'api_key': ''
                }
            }
        }
    }
    
    # Load YAML configuration from standardized location
    # Single source of truth: config/chronos.yaml
    yaml_path = Path('config/chronos.yaml')

    if yaml_path.exists():
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    _deep_update(config, yaml_config)
                    logger.info(f"Configuration loaded from {yaml_path}")

                    # Log calendar configuration for debugging
                    caldav_config = yaml_config.get('caldav', {})
                    calendars = caldav_config.get('calendars', [])
                    if calendars:
                        logger.info(f"Found {len(calendars)} Radicale calendars configured: {[cal.get('alias', cal.get('id')) for cal in calendars]}")
                    else:
                        logger.warning("No Radicale calendars found in configuration")

        except Exception as e:
            logger.error(f"Failed to load configuration from {yaml_path}: {e}")
            logger.error("Using default configuration - some features may not work correctly")
    else:
        logger.error(f"Configuration file {yaml_path} not found!")
        logger.error("Using default configuration - calendar sync will not work")
    
    # Override with environment variables
    if os.getenv('CHRONOS_API_KEY'):
        config['api']['api_key'] = os.getenv('CHRONOS_API_KEY')
    
    if os.getenv('LOG_LEVEL'):
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))
    
    if os.getenv('DATABASE_URL'):
        config['database']['url'] = os.getenv('DATABASE_URL')
    
    if os.getenv('CHRONOS_WEBHOOK_URL'):
        config['notifications']['channels']['webhook']['url'] = os.getenv('CHRONOS_WEBHOOK_URL')
        config['notifications']['channels']['webhook']['enabled'] = True
    
    if os.getenv('CHRONOS_WEBHOOK_API_KEY'):
        config['notifications']['channels']['webhook']['api_key'] = os.getenv('CHRONOS_WEBHOOK_API_KEY')
    
    logger.info("Configuration loaded successfully")
    return config


def _deep_update(base_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> None:
    """Deep update nested dictionary"""
    for key, value in update_dict.items():
        if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
            _deep_update(base_dict[key], value)
        else:
            base_dict[key] = value
