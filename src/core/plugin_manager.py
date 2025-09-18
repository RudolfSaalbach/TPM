"""
Plugin Manager for Chronos - Phase 2 Feature
Dynamic plugin loading and management system
"""

import asyncio
import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.core.models import ChronosEvent, PluginConfig


class PluginInterface(ABC):
    """Base interface for all Chronos plugins"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description"""
        pass
    
    @abstractmethod
    async def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize plugin with system context"""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup plugin resources"""
        pass


class EventPlugin(PluginInterface):
    """Base class for event processing plugins"""
    
    @abstractmethod
    async def process_event(self, event: ChronosEvent) -> ChronosEvent:
        """Process an event and return modified version"""
        pass


class SchedulingPlugin(PluginInterface):
    """Base class for scheduling plugins"""
    
    @abstractmethod
    async def suggest_schedule(
        self, 
        events: List[ChronosEvent],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Suggest scheduling modifications"""
        pass


@dataclass
class PluginInfo:
    """Plugin information"""
    name: str
    version: str
    description: str
    plugin_class: type
    instance: Optional[PluginInterface] = None
    config: Optional[PluginConfig] = None
    loaded: bool = False
    enabled: bool = True


class PluginManager:
    """Plugin management system"""
    
    def __init__(self, context: Dict[str, Any]):
        self.context = context
        self.logger = logging.getLogger(__name__)

        # Plugin storage
        self.plugins: Dict[str, PluginInfo] = {}
        self.event_processors: List[EventPlugin] = []
        self.scheduling_plugins: List[SchedulingPlugin] = []

        # Plugin hooks
        self.hooks: Dict[str, List[Callable]] = {
            'event_created': [],
            'event_updated': [],
            'event_deleted': [],
            'schedule_optimized': [],
            'conflict_detected': []
        }

    async def initialize(self) -> bool:
        """Initialize the plugin manager and load configured plugins"""
        try:
            self.logger.info("Initializing Plugin Manager...")

            # Load plugins from custom directory if configured
            config = self.context.get('plugins', {})
            custom_dir = config.get('custom_dir', 'plugins/custom')

            if Path(custom_dir).exists():
                loaded_count = await self.load_plugins_from_directory(custom_dir)
                self.logger.info(f"Loaded {loaded_count} plugins from {custom_dir}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Plugin Manager: {e}")
            return False

    async def cleanup(self):
        """Cleanup all loaded plugins"""
        try:
            for plugin_info in self.plugins.values():
                if plugin_info.loaded and plugin_info.instance:
                    await plugin_info.instance.cleanup()

            self.plugins.clear()
            self.event_processors.clear()
            self.scheduling_plugins.clear()

            self.logger.info("Plugin Manager cleaned up")

        except Exception as e:
            self.logger.error(f"Error during Plugin Manager cleanup: {e}")
        
        self.logger.info("Plugin Manager initialized")
    
    async def load_plugin_from_file(self, plugin_path: Union[str, Path]) -> bool:
        """Load a plugin from a Python file"""
        
        try:
            plugin_path = Path(plugin_path)
            
            if not plugin_path.exists() or not plugin_path.suffix == '.py':
                self.logger.error(f"Invalid plugin file: {plugin_path}")
                return False
            
            # Import the module
            spec = importlib.util.spec_from_file_location(
                plugin_path.stem, 
                plugin_path
            )
            
            if not spec or not spec.loader:
                self.logger.error(f"Could not load plugin spec: {plugin_path}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find plugin classes
            plugin_classes = []
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, PluginInterface) and 
                    obj != PluginInterface and
                    obj not in [EventPlugin, SchedulingPlugin]):
                    plugin_classes.append(obj)
            
            if not plugin_classes:
                self.logger.warning(f"No plugin classes found in {plugin_path}")
                return False
            
            # Load each plugin class
            success = True
            for plugin_class in plugin_classes:
                if not await self._load_plugin_class(plugin_class):
                    success = False
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to load plugin from {plugin_path}: {e}")
            return False
    
    async def _load_plugin_class(self, plugin_class: type) -> bool:
        """Load a plugin class"""
        
        try:
            # Create plugin instance
            plugin_instance = plugin_class()
            
            # Create plugin info
            plugin_info = PluginInfo(
                name=plugin_instance.name,
                version=plugin_instance.version,
                description=plugin_instance.description,
                plugin_class=plugin_class,
                instance=plugin_instance
            )
            
            # Initialize plugin
            if await plugin_instance.initialize(self.context):
                self.plugins[plugin_instance.name] = plugin_info
                plugin_info.loaded = True
                
                # Register plugin by type
                if isinstance(plugin_instance, EventPlugin):
                    self.event_processors.append(plugin_instance)
                
                if isinstance(plugin_instance, SchedulingPlugin):
                    self.scheduling_plugins.append(plugin_instance)
                
                self.logger.info(f"Loaded plugin: {plugin_instance.name} v{plugin_instance.version}")
                return True
            else:
                self.logger.error(f"Failed to initialize plugin: {plugin_instance.name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to load plugin class {plugin_class.__name__}: {e}")
            return False
    
    async def load_plugins_from_directory(self, directory_path: Union[str, Path]) -> int:
        """Load all plugins from a directory"""
        
        directory_path = Path(directory_path)
        
        if not directory_path.exists() or not directory_path.is_dir():
            self.logger.warning(f"Plugin directory does not exist: {directory_path}")
            return 0
        
        loaded_count = 0
        
        # Find all Python files in directory
        for plugin_file in directory_path.glob('*.py'):
            if plugin_file.name.startswith('__'):
                continue  # Skip __init__.py etc.
            
            if await self.load_plugin_from_file(plugin_file):
                loaded_count += 1
        
        self.logger.info(f"Loaded {loaded_count} plugins from {directory_path}")
        return loaded_count
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin"""
        
        if plugin_name not in self.plugins:
            return False
        
        try:
            plugin_info = self.plugins[plugin_name]
            
            if plugin_info.instance:
                # Cleanup plugin
                await plugin_info.instance.cleanup()
                
                # Remove from type-specific lists
                if isinstance(plugin_info.instance, EventPlugin):
                    self.event_processors.remove(plugin_info.instance)
                
                if isinstance(plugin_info.instance, SchedulingPlugin):
                    self.scheduling_plugins.remove(plugin_info.instance)
            
            # Remove from plugins dict
            del self.plugins[plugin_name]
            
            self.logger.info(f"Unloaded plugin: {plugin_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unload plugin {plugin_name}: {e}")
            return False
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin"""
        
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = True
        self.logger.info(f"Enabled plugin: {plugin_name}")
        return True
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin"""
        
        if plugin_name not in self.plugins:
            return False
        
        self.plugins[plugin_name].enabled = False
        self.logger.info(f"Disabled plugin: {plugin_name}")
        return True
    
    async def process_event_through_plugins(self, event: ChronosEvent) -> ChronosEvent:
        """Process event through all enabled event plugins"""
        
        processed_event = event
        
        for plugin in self.event_processors:
            plugin_info = self.plugins.get(plugin.name)
            
            if plugin_info and plugin_info.enabled:
                try:
                    processed_event = await plugin.process_event(processed_event)
                    self.logger.debug(f"Event processed by plugin: {plugin.name}")
                    
                except Exception as e:
                    self.logger.error(f"Plugin {plugin.name} failed to process event: {e}")
                    # Continue with other plugins
        
        return processed_event
    
    async def get_scheduling_suggestions(
        self, 
        events: List[ChronosEvent]
    ) -> List[Dict[str, Any]]:
        """Get scheduling suggestions from all scheduling plugins"""
        
        all_suggestions = []
        
        for plugin in self.scheduling_plugins:
            plugin_info = self.plugins.get(plugin.name)
            
            if plugin_info and plugin_info.enabled:
                try:
                    suggestions = await plugin.suggest_schedule(events, self.context)
                    
                    # Add plugin info to suggestions
                    for suggestion in suggestions:
                        suggestion['plugin_name'] = plugin.name
                        suggestion['plugin_version'] = plugin.version
                    
                    all_suggestions.extend(suggestions)
                    self.logger.debug(f"Got {len(suggestions)} suggestions from {plugin.name}")
                    
                except Exception as e:
                    self.logger.error(f"Plugin {plugin.name} failed to generate suggestions: {e}")
        
        return all_suggestions
    
    def register_hook(self, hook_name: str, callback: Callable):
        """Register a callback for a plugin hook"""
        
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        
        self.hooks[hook_name].append(callback)
        self.logger.debug(f"Registered hook callback: {hook_name}")
    
    async def trigger_hook(self, hook_name: str, *args, **kwargs):
        """Trigger all callbacks for a hook"""
        
        if hook_name not in self.hooks:
            return
        
        for callback in self.hooks[hook_name]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"Hook callback failed for {hook_name}: {e}")
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a plugin"""
        
        if plugin_name not in self.plugins:
            return None
        
        plugin_info = self.plugins[plugin_name]
        
        return {
            'name': plugin_info.name,
            'version': plugin_info.version,
            'description': plugin_info.description,
            'loaded': plugin_info.loaded,
            'enabled': plugin_info.enabled,
            'type': type(plugin_info.instance).__name__ if plugin_info.instance else None
        }
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins"""
        
        return [
            {
                'name': info.name,
                'version': info.version,
                'description': info.description,
                'loaded': info.loaded,
                'enabled': info.enabled,
                'type': type(info.instance).__name__ if info.instance else None
            }
            for info in self.plugins.values()
        ]
    
    async def cleanup_all_plugins(self):
        """Cleanup all plugins"""
        
        for plugin_name in list(self.plugins.keys()):
            await self.unload_plugin(plugin_name)
        
        self.logger.info("All plugins cleaned up")
