# -*- coding: utf-8 -*-
from typing import Dict, Type, Optional, List, Callable, Any
from .tool_window import ToolWindow, DockPosition, PluginManifest, PluginProtocol


class SideDockRegistry:
    _instance = None
    _registries: Dict[str, Dict[str, "DockEntry"]] = {}
    _plugin_classes: Dict[str, Type[ToolWindow]] = {}
    _active_plugins: Dict[str, Any] = {}
    _plugin_states: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        context_id: str,
        name: str,
        window_class: Type[ToolWindow],
        position: Optional[DockPosition] = None,
    ):
        if context_id not in cls._registries:
            cls._registries[context_id] = {}
        entries = cls._registries[context_id]
        if position is None:
            position = window_class.default_position
        else:
            window_class.position = position
        entries[name] = DockEntry(window_class, position)
        if context_id not in cls._plugin_states:
            cls._plugin_states[context_id] = {}
        if name not in cls._plugin_states[context_id]:
            cls._plugin_states[context_id][name] = {
                "enabled": True,
                "position": position.value if position else DockPosition.HIDDEN.value,
            }

    @classmethod
    def register_plugin(cls, context_id: str, plugin_cls: Type[ToolWindow]):
        manifest = plugin_cls.get_manifest()
        cls._plugin_classes[manifest.name] = plugin_cls
        cls.register(context_id, manifest.name, plugin_cls, manifest.position)

    @classmethod
    def get_plugin_class(cls, name: str) -> Optional[Type[ToolWindow]]:
        return cls._plugin_classes.get(name)

    @classmethod
    def activate_plugin(cls, name: str, page, button) -> Optional[ToolWindow]:
        if name in cls._active_plugins:
            return cls._active_plugins[name]

        plugin_cls = cls._plugin_classes.get(name)
        if not plugin_cls:
            return None

        manifest = plugin_cls.get_manifest()
        for dep in manifest.dependencies:
            if dep not in cls._active_plugins:
                cls.activate_plugin(dep, page, button)

        instance = plugin_cls(page, button)
        if isinstance(instance, PluginProtocol):
            instance.on_activate()
        cls._active_plugins[name] = instance
        return instance

    @classmethod
    def deactivate_plugin(cls, name: str):
        if name in cls._active_plugins:
            instance = cls._active_plugins.pop(name)
            if isinstance(instance, PluginProtocol):
                instance.on_deactivate()
            if hasattr(instance, "cleanup"):
                instance.cleanup()

    @classmethod
    def get_active_plugin(cls, name: str) -> Optional[ToolWindow]:
        return cls._active_plugins.get(name)

    @classmethod
    def get_all(cls, context_id: str):
        return cls._registries.get(context_id, {}).copy()

    @classmethod
    def get_all_entries(cls, context_id: str) -> Dict[str, "DockEntry"]:
        return cls._registries.get(context_id, {}).copy()

    @classmethod
    def clear_context(cls, context_id: str):
        cls._registries.pop(context_id, None)

    @classmethod
    def set_plugin_enabled(cls, context_id: str, plugin_name: str, enabled: bool):
        if context_id not in cls._plugin_states:
            cls._plugin_states[context_id] = {}
        if plugin_name not in cls._plugin_states[context_id]:
            cls._plugin_states[context_id][plugin_name] = {}
        cls._plugin_states[context_id][plugin_name]["enabled"] = enabled

    @classmethod
    def is_plugin_enabled(cls, context_id: str, plugin_name: str) -> bool:
        state = cls._plugin_states.get(context_id, {}).get(plugin_name, {})
        return state.get("enabled", True)

    @classmethod
    def set_plugin_position(
        cls, context_id: str, plugin_name: str, position: DockPosition
    ):
        if context_id not in cls._plugin_states:
            cls._plugin_states[context_id] = {}
        if plugin_name not in cls._plugin_states[context_id]:
            cls._plugin_states[context_id][plugin_name] = {}
        cls._plugin_states[context_id][plugin_name]["position"] = position.value

        if context_id in cls._registries and plugin_name in cls._registries[context_id]:
            cls._registries[context_id][plugin_name].position = position

    @classmethod
    def get_plugin_position(cls, context_id: str, plugin_name: str) -> DockPosition:
        state = cls._plugin_states.get(context_id, {}).get(plugin_name, {})
        pos_value = state.get("position", DockPosition.HIDDEN.value)
        return DockPosition(pos_value)

    @classmethod
    def get_plugin_state(cls, context_id: str, plugin_name: str) -> Dict[str, Any]:
        return cls._plugin_states.get(context_id, {}).get(
            plugin_name,
            {
                "enabled": True,
                "position": DockPosition.HIDDEN.value,
            },
        )

    @classmethod
    def get_all_plugin_states(cls, context_id: str) -> Dict[str, Dict[str, Any]]:
        return cls._plugin_states.get(context_id, {}).copy()

    @classmethod
    def load_states_from_config(cls, config: Dict[str, Dict[str, Any]]):
        cls._plugin_states = config.copy()

    @classmethod
    def save_states_to_config(cls) -> Dict[str, Dict[str, Any]]:
        return cls._plugin_states.copy()


def side_dock_plugin(
    name: str,
    position: DockPosition = DockPosition.HIDDEN,
    shortcut: Optional[str] = None,
    dependencies: Optional[List[str]] = None,
    singleton: bool = True,
    auto_activate: bool = True,
) -> Callable[[Type[ToolWindow]], Type[ToolWindow]]:
    def decorator(cls: Type[ToolWindow]) -> Type[ToolWindow]:
        cls._manifest = PluginManifest(
            name=name,
            display_name=getattr(cls, "display_name", name),
            icon=getattr(cls, "icon", None),
            position=position,
            shortcut=shortcut,
            dependencies=dependencies or [],
            singleton=singleton,
            auto_activate=auto_activate,
        )
        SideDockRegistry.register_plugin(cls)
        return cls

    return decorator


class DockEntry:
    def __init__(self, cls: Type[ToolWindow], position: DockPosition):
        self.cls = cls
        self.position = position
