"""
Chronos Engine - Modular Web Routes
Updated routing for the refactored component-based interface
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Create blueprint for modular routes
modular_bp = Blueprint('modular', __name__, template_folder='templates')


@modular_bp.route('/')
@modular_bp.route('/dashboard')
def dashboard():
    """Dashboard page with component architecture"""
    try:
        # Get dashboard data (would be replaced with actual service calls)
        dashboard_data = {
            'productivity_metrics': {
                'total_events': 42,
                'completion_rate': 0.85,
                'total_hours': 156.5,
                'average_productivity': 4.2,
                'events_per_day': 6.8
            },
            'priority_distribution': {
                'High': 12,
                'Medium': 18,
                'Low': 8,
                'Urgent': 4
            },
            'recommendations': [
                {
                    'type': 'optimization',
                    'priority': 'high',
                    'message': 'Consider consolidating similar meetings into single sessions'
                },
                {
                    'type': 'scheduling',
                    'priority': 'medium',
                    'message': 'You have 2 hours available tomorrow afternoon for deep work'
                }
            ],
            'generated_at': datetime.now().isoformat()
        }

        return render_template('dashboard.html', **dashboard_data)

    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template('error.html', error="Failed to load dashboard"), 500


@modular_bp.route('/events')
def events():
    """Events page with modular components"""
    try:
        # Get initial filters from query parameters
        filters = {
            'range': request.args.get('range', '7'),
            'direction': request.args.get('direction', 'future'),
            'calendar': request.args.get('calendar', 'primary'),
            'search_query': request.args.get('q', '')
        }

        # Get available calendars (would be from service)
        calendars = [
            {'id': 'primary', 'name': 'Primary Calendar'},
            {'id': 'work', 'name': 'Work Calendar'},
            {'id': 'personal', 'name': 'Personal Calendar'}
        ]

        # User permissions (would be from auth service)
        permissions = {
            'can_create': True,
            'can_edit': True,
            'can_delete': True
        }

        return render_template('modular_events.html',
                             filters=filters,
                             calendars=calendars,
                             permissions=permissions,
                             selected_calendar=filters['calendar'])

    except Exception as e:
        logger.error(f"Events page error: {e}")
        return render_template('error.html', error="Failed to load events page"), 500


@modular_bp.route('/templates')
def templates():
    """Templates management page"""
    try:
        # Template categories and stats
        template_stats = {
            'total_templates': 24,
            'most_used': 'Weekly Team Meeting',
            'categories': ['Meeting', 'Task', 'Event', 'Reminder']
        }

        return render_template('modular_templates.html',
                             template_stats=template_stats)

    except Exception as e:
        logger.error(f"Templates page error: {e}")
        return render_template('error.html', error="Failed to load templates page"), 500


@modular_bp.route('/analytics')
def analytics():
    """Analytics and reporting page"""
    try:
        # Analytics data (would be from analytics service)
        analytics_data = {
            'time_range': request.args.get('range', '30'),
            'total_events': 156,
            'total_hours': 342.5,
            'productivity_score': 4.2,
            'trends': {
                'events_growth': 0.15,
                'productivity_change': 0.08
            }
        }

        return render_template('modular_analytics.html', **analytics_data)

    except Exception as e:
        logger.error(f"Analytics page error: {e}")
        return render_template('error.html', error="Failed to load analytics page"), 500


@modular_bp.route('/settings')
def settings():
    """Settings and preferences page"""
    try:
        # User settings (would be from user service)
        user_settings = {
            'theme': 'dark',
            'language': 'de',
            'timezone': 'Europe/Berlin',
            'notifications': True,
            'auto_sync': True,
            'sync_interval': 300000  # 5 minutes
        }

        return render_template('modular_settings.html',
                             settings=user_settings)

    except Exception as e:
        logger.error(f"Settings page error: {e}")
        return render_template('error.html', error="Failed to load settings page"), 500


# API Routes for component data
@modular_bp.route('/api/component-data/<component_name>')
def component_data(component_name):
    """Get data for specific component"""
    try:
        # Route to appropriate data provider based on component
        data_providers = {
            'event-list': get_event_list_data,
            'filter-panel': get_filter_panel_data,
            'template-modal': get_template_modal_data,
            'dashboard-stats': get_dashboard_stats_data
        }

        provider = data_providers.get(component_name)
        if not provider:
            return jsonify({'error': f'Unknown component: {component_name}'}), 404

        data = provider(request.args)
        return jsonify(data)

    except Exception as e:
        logger.error(f"Component data error for {component_name}: {e}")
        return jsonify({'error': 'Failed to get component data'}), 500


def get_event_list_data(params):
    """Get event list data for EventListComponent"""
    # Extract parameters
    calendar = params.get('calendar', 'primary')
    range_days = params.get('range', '7')
    direction = params.get('direction', 'future')
    search_query = params.get('q', '')
    page = int(params.get('page', 1))
    page_size = int(params.get('page_size', 100))

    # Mock data - would be replaced with actual service calls
    events = []
    for i in range(20):
        event = {
            'id': f'event-{i}',
            'title': f'Event {i + 1}' + (' [TASK]' if i % 3 == 0 else ''),
            'description': f'Description for event {i + 1}',
            'start_utc': (datetime.now() + timedelta(days=i)).isoformat(),
            'end_utc': (datetime.now() + timedelta(days=i, hours=1)).isoformat(),
            'all_day': i % 5 == 0,
            'all_day_date': (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d') if i % 5 == 0 else None,
            'calendar_id': calendar,
            'status': 'scheduled',
            'priority': 'high' if i % 4 == 0 else 'medium'
        }

        # Add search filtering
        if search_query and search_query.lower() not in event['title'].lower():
            continue

        events.append(event)

    return {
        'items': events,
        'total': len(events),
        'page': page,
        'page_size': page_size,
        'has_more': False
    }


def get_filter_panel_data(params):
    """Get filter panel data"""
    return {
        'available_calendars': [
            {'id': 'primary', 'name': 'Primary Calendar'},
            {'id': 'work', 'name': 'Work Calendar'},
            {'id': 'personal', 'name': 'Personal Calendar'}
        ],
        'range_options': [
            {'value': '7', 'label': '7 Days'},
            {'value': '14', 'label': '14 Days'},
            {'value': '30', 'label': '30 Days'},
            {'value': '60', 'label': '60 Days'},
            {'value': '360', 'label': '360 Days'},
            {'value': '-1', 'label': 'All Events'}
        ],
        'direction_options': [
            {'value': 'past', 'label': 'Past'},
            {'value': 'future', 'label': 'Future'},
            {'value': 'all', 'label': 'All'}
        ]
    }


def get_template_modal_data(params):
    """Get template modal data"""
    search_query = params.get('q', '')

    # Mock templates - would be from template service
    templates = []
    for i in range(10):
        template = {
            'id': f'template-{i}',
            'title': f'Template {i + 1}',
            'description': f'Description for template {i + 1}',
            'tags': ['meeting', 'work'] if i % 2 == 0 else ['personal', 'task'],
            'usage_count': (i + 1) * 3,
            'all_day': i % 3 == 0,
            'default_time': '09:00' if not (i % 3 == 0) else None,
            'duration_minutes': 60 if not (i % 3 == 0) else None
        }

        # Search filtering
        if search_query:
            search_lower = search_query.lower()
            if (search_lower not in template['title'].lower() and
                search_lower not in template['description'].lower() and
                not any(search_lower in tag.lower() for tag in template['tags'])):
                continue

        templates.append(template)

    return {
        'items': templates,
        'total': len(templates)
    }


def get_dashboard_stats_data(params):
    """Get dashboard statistics data"""
    return {
        'productivity_metrics': {
            'total_events': 42,
            'completion_rate': 0.85,
            'total_hours': 156.5,
            'average_productivity': 4.2,
            'events_per_day': 6.8
        },
        'priority_distribution': {
            'High': 12,
            'Medium': 18,
            'Low': 8,
            'Urgent': 4
        },
        'time_distribution': {
            'morning': 35,
            'afternoon': 40,
            'evening': 25
        },
        'system_status': {
            'calendar_sync': 'active',
            'analytics_engine': 'running',
            'ai_optimizer': 'ready',
            'plugin_system': 'loaded'
        }
    }


# Configuration endpoints for client-side
@modular_bp.route('/api/client-config')
def client_config():
    """Get client-side configuration"""
    try:
        config = {
            'api': {
                'baseURL': '/api/v1',
                'timeout': 30000,
                'retryAttempts': 3
            },
            'ui': {
                'theme': request.args.get('theme', 'dark'),
                'language': request.args.get('language', 'de'),
                'timezone': 'Europe/Berlin',
                'dateFormat': 'DD.MM.YYYY',
                'timeFormat': '24h'
            },
            'features': {
                'v22_enabled': True,
                'sub_tasks_enabled': True,
                'workflows_enabled': True,
                'ai_enabled': False
            },
            'debug': current_app.debug
        }

        return jsonify(config)

    except Exception as e:
        logger.error(f"Client config error: {e}")
        return jsonify({'error': 'Failed to get client config'}), 500


# Health check for components
@modular_bp.route('/api/health/components')
def components_health():
    """Health check for component system"""
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'event_bus': 'active',
                'state_manager': 'active',
                'api_service': 'active',
                'component_base': 'active'
            },
            'version': '2.2.0'
        }

        return jsonify(health_data)

    except Exception as e:
        logger.error(f"Components health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# Error handlers
@modular_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors in modular routes"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404

    return render_template('error.html',
                         error="Page not found",
                         error_code=404), 404


@modular_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors in modular routes"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500

    return render_template('error.html',
                         error="Internal server error",
                         error_code=500), 500


# Context processors for templates
@modular_bp.context_processor
def inject_global_context():
    """Inject global context variables into all templates"""
    return {
        'app_version': '2.2.0',
        'current_year': datetime.now().year,
        'api_base_url': '/api/v1',
        'debug': current_app.debug,
        'features': {
            'v22_enabled': True,
            'sub_tasks_enabled': True,
            'workflows_enabled': True,
            'ai_enabled': False
        },
        'theme': request.args.get('theme', 'dark'),
        'language': request.args.get('language', 'de'),
        'timezone': 'Europe/Berlin'
    }


# Template filters
@modular_bp.app_template_filter('datetime_format')
def datetime_format(dt, format='%Y-%m-%d %H:%M'):
    """Format datetime for templates"""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt

    if isinstance(dt, datetime):
        return dt.strftime(format)

    return dt


@modular_bp.app_template_filter('relative_time')
def relative_time(dt):
    """Get relative time string"""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt

    if not isinstance(dt, datetime):
        return dt

    now = datetime.now(dt.tzinfo)
    delta = now - dt

    if delta.days > 0:
        return f"{delta.days} days ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours} hours ago"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago"
    else:
        return "just now"


# WebSocket support for real-time updates (if using Flask-SocketIO)
try:
    from flask_socketio import emit, join_room, leave_room

    @modular_bp.route('/api/ws/events')
    def websocket_events():
        """WebSocket endpoint for real-time event updates"""
        # This would be implemented with Flask-SocketIO
        pass

except ImportError:
    # Flask-SocketIO not available
    pass