# -*- coding: utf-8 -*-
from typing import Dict, Type, Optional, List, Callable, Any
from .tool_window import ToolWindow, DockPosition, PluginManifest, PluginProtocol


class SideDockRegistry:
    _instance = None
    _registries: Dict[str, Dict[str, "DockEntry"]] = {}
    _plugin_classes: Dict[str, Type[ToolWindow]] = {}
    _active_plugins: Dict[str, Any] = {}

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
    def clear_context(cls, context_id: str):
        cls._registries.pop(context_id, None)


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
