# -*- coding: utf-8 -*-
import importlib
import inspect
import os
from pathlib import Path
from typing import Optional, Dict, List, Type, Any, Union

from loguru import logger

from app.plugins.constants import PluginType
from app.plugins.node_plugins.base import BaseNodePlugin
from app.plugins.trigger_plugins.base import BaseTriggerPlugin


class UnifiedPluginManager:
    """
    统一插件管理器：同时管理节点插件和触发器插件
    单例模式，支持类型感知加载与查询
    """
    _instance: Optional['UnifiedPluginManager'] = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if self._initialized:
            return
        self._initialized = True

        # 分类存储：plugin_name -> instance
        self._node_plugins: Dict[str, BaseNodePlugin] = {}
        self._trigger_plugins: Dict[str, BaseTriggerPlugin] = {}

        # 反向索引：plugin_id -> plugin_name（兼容旧接口）
        self._id_to_name: Dict[str, str] = {}

        # 已加载的模块缓存，避免重复导入
        self._loaded_modules: set = set()

        logger.info("UnifiedPluginManager initialized")

    @classmethod
    def get_instance(cls) -> 'UnifiedPluginManager':
        """获取单例实例"""
        return cls()

    # ==================== 核心加载逻辑 ====================

    def load_plugins(self, root_dir: str, plugin_type: Optional[PluginType] = None) -> Dict[str, int]:
        """
        统一加载入口：递归扫描目录并加载插件

        :param root_dir: 插件根目录绝对路径
        :param plugin_type: 可选，指定只加载某类插件；None 则自动识别
        :return: { 'node': 加载数量, 'trigger': 加载数量 }
        """
        result = {'node': 0, 'trigger': 0}
        root_path = Path(root_dir).resolve()

        if not root_path.exists():
            logger.error(f"Plugin directory not found: {root_dir}")
            return result

        # 1. 确定根包名（兼容原有逻辑）
        base_package_path = self._resolve_package_path(root_dir)
        if not base_package_path:
            logger.error(f"Failed to resolve package path for {root_dir}")
            return result

        logger.info(f"Scanning plugins in {root_dir} (base_package: {base_package_path})")

        # 2. 递归遍历目录
        for py_file in root_path.rglob("*.py"):
            # 跳过 __ 开头的文件
            if py_file.name.startswith("__"):
                continue

            # 计算模块路径
            rel_path = py_file.relative_to(root_path)
            module_rel_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
            full_module_name = f"{base_package_path}.{module_rel_name}" if base_package_path else module_rel_name

            # 避免重复加载
            if full_module_name in self._loaded_modules:
                continue

            try:
                # 3. 动态导入模块
                module = importlib.import_module(full_module_name)
                self._loaded_modules.add(full_module_name)

                # 4. 扫描模块中的插件类
                loaded = self._scan_module(module, full_module_name, plugin_type)
                result['node'] += loaded.get('node', 0)
                result['trigger'] += loaded.get('trigger', 0)

            except Exception as e:
                logger.error(f"Failed to load module {full_module_name}: {e}")

        logger.info(f"Load completed: {result['node']} node plugins, {result['trigger']} trigger plugins")
        return result

    def _resolve_package_path(self, root_dir: str) -> Optional[str]:
        """
        解析根包名（兼容原有 'app' 目录定位逻辑）
        """
        parts = root_dir.replace("\\", "/").split("/")
        try:
            start_index = parts.index("app")
            return ".".join(parts[start_index:])
        except ValueError:
            # 备用方案：尝试从 sys.path 推断
            import sys
            root_path = Path(root_dir).resolve()
            for path in sys.path:
                try:
                    rel = root_path.relative_to(Path(path).resolve())
                    if rel.parts:
                        return ".".join(rel.parts)
                except ValueError:
                    continue
            logger.warning(f"Could not resolve package path for {root_dir}, using relative import")
            return None

    def _scan_module(self, module, module_name: str, filter_type: Optional[PluginType]) -> Dict[str, int]:
        """
        扫描模块中的插件类并实例化注册
        """
        result = {'node': 0, 'trigger': 0}

        for name, obj in inspect.getmembers(module, inspect.isclass):
            # 跳过基类本身
            if obj in (BaseNodePlugin, BaseTriggerPlugin):
                continue

            # 检查是否是节点插件
            if issubclass(obj, BaseNodePlugin) and hasattr(obj, 'plugin_id') and obj.plugin_id:
                if filter_type is None or filter_type == PluginType.NODE:
                    if self._register_node_plugin(obj, module_name):
                        result['node'] += 1

            # 检查是否是触发器插件
            elif issubclass(obj, BaseTriggerPlugin) and hasattr(obj, 'plugin_id') and obj.plugin_id:
                if filter_type is None or filter_type == PluginType.TRIGGER:
                    if self._register_trigger_plugin(obj, module_name):
                        result['trigger'] += 1

        return result

    # ==================== 插件注册 ====================

    def _register_node_plugin(self, plugin_class: Type[BaseNodePlugin], module_name: str) -> bool:
        """注册节点插件实例"""
        try:
            instance = plugin_class()
            plugin_name = instance.plugin_name

            if not plugin_name:
                logger.warning(f"Node plugin {plugin_class.__name__} has empty plugin_name, skipped")
                return False

            if plugin_name in self._node_plugins:
                logger.warning(f"Node plugin '{plugin_name}' already registered, skipping duplicate")
                return False

            # 注入元数据（可选）
            instance._module_name = module_name

            self._node_plugins[plugin_name] = instance
            self._id_to_name[instance.plugin_id] = plugin_name

            logger.info(f"✓ Registered node plugin [{plugin_name}] from {module_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to instantiate node plugin {plugin_class.__name__}: {e}")
            return False

    def _register_trigger_plugin(self, plugin_class: Type[BaseTriggerPlugin], module_name: str) -> bool:
        """注册触发器插件类（实例由 Manager 创建）"""
        try:
            instance = plugin_class()
            plugin_name = instance.plugin_name

            if not plugin_name:
                logger.warning(f"Trigger plugin {instance.__name__} has empty plugin_name, skipped")
                return False

            if plugin_name in self._trigger_plugins:
                logger.warning(f"Trigger plugin '{plugin_name}' already registered, skipping duplicate")
                return False
            # 存储类而非实例，由触发器 Manager 按需创建实例
            self._trigger_plugins[plugin_name] = instance
            self._id_to_name[plugin_class.plugin_id] = plugin_name

            logger.info(f"✓ Registered trigger plugin [{plugin_name}] from {module_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to register trigger plugin {plugin_class.__name__}: {e}")
            return False

    # ==================== 查询接口（兼容 + 增强） ====================

    def get_plugin(self, identifier: str, plugin_type: Optional[PluginType] = None) -> Optional[
        Union[BaseNodePlugin, BaseTriggerPlugin]]:
        """
        统一获取插件（兼容旧接口）

        :param identifier: plugin_name 或 plugin_id
        :param plugin_type: 可选，指定类型加速查找
        :return: 插件实例（节点）或插件类（触发器）
        """
        # 策略1: 直接按 plugin_name 查找
        if plugin_type is None or plugin_type == PluginType.NODE:
            if identifier in self._node_plugins:
                return self._node_plugins[identifier]

        if plugin_type is None or plugin_type == PluginType.TRIGGER:
            if identifier in self._trigger_plugins:
                return self._trigger_plugins[identifier]

        # 策略2: 按 plugin_id 反向查找
        plugin_name = self._id_to_name.get(identifier)
        if plugin_name:
            if plugin_name in self._node_plugins:
                return self._node_plugins[plugin_name]
            if plugin_name in self._trigger_plugins:
                return self._trigger_plugins[plugin_name]

        # 未找到
        logger.debug(f"Plugin '{identifier}' not found")
        return None

    def get_node_plugin(self, identifier: str) -> Optional[BaseNodePlugin]:
        """便捷方法：获取节点插件实例"""
        plugin = self.get_plugin(identifier, PluginType.NODE)
        return plugin if isinstance(plugin, BaseNodePlugin) else None

    def get_trigger_plugin(self, identifier: str) -> Optional[Type[BaseTriggerPlugin]]:
        """便捷方法：获取触发器插件类"""
        plugin = self.get_plugin(identifier, PluginType.TRIGGER)
        return plugin if inspect.isclass(plugin) and issubclass(plugin, BaseTriggerPlugin) else None

    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> Dict[str, Any]:
        """
        列出已加载插件

        :param plugin_type: None=全部, NODE=仅节点, TRIGGER=仅触发器
        :return: { plugin_name: plugin_object }
        """
        result = {}
        if plugin_type is None or plugin_type == PluginType.NODE:
            result.update(self._node_plugins)
        if plugin_type is None or plugin_type == PluginType.TRIGGER:
            result.update(self._trigger_plugins)
        return result

    def list_plugin_names(self, plugin_type: Optional[PluginType] = None) -> List[str]:
        """列出插件名称列表（用于UI下拉等）"""
        return list(self.list_plugins(plugin_type).keys())

    # ==================== 生命周期管理 ====================

    def unload_plugin(self, identifier: str) -> bool:
        """卸载单个插件"""
        plugin = self.get_plugin(identifier)
        if not plugin:
            return False

        plugin_name = identifier
        if identifier in self._id_to_name:
            plugin_name = self._id_to_name[identifier]

        # 清理节点插件
        if plugin_name in self._node_plugins:
            instance = self._node_plugins.pop(plugin_name)
            # 调用可选的 cleanup 钩子
            if hasattr(instance, 'on_unload'):
                try:
                    instance.on_unload()
                except Exception as e:
                    logger.error(f"Error during node plugin unload {plugin_name}: {e}")
            logger.info(f"Unloaded node plugin: {plugin_name}")
            return True

        # 清理触发器插件
        if plugin_name in self._trigger_plugins:
            plugin_class = self._trigger_plugins.pop(plugin_name)
            # 通知关联的 TriggerManager 清理（如果实现了 deactivate_all）
            if hasattr(plugin_class, 'manager') and plugin_class.manager:
                try:
                    # 尝试调用管理器的批量移除方法
                    if hasattr(plugin_class.manager, 'remove_by_canvas'):
                        plugin_class.manager.remove_by_canvas_for_plugin(plugin_name)
                except Exception as e:
                    logger.warning(f"Failed to cleanup trigger manager for {plugin_name}: {e}")
            logger.info(f"Unloaded trigger plugin: {plugin_name}")
            return True

        return False

    def reload_plugin(self, identifier: str) -> bool:
        """热重载插件（开发模式）"""
        plugin = self.get_plugin(identifier)
        if not plugin:
            return False

        plugin_name = identifier
        if identifier in self._id_to_name:
            plugin_name = self._id_to_name[identifier]

        # 获取模块名并重新导入
        if hasattr(plugin, '_module_name'):
            module_name = plugin._module_name
            try:
                # 卸载旧版
                self.unload_plugin(identifier)
                # 重新导入模块
                module = importlib.import_module(module_name)
                importlib.reload(module)
                # 重新扫描注册
                self._scan_module(module, module_name, None)
                logger.info(f"Reloaded plugin: {plugin_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to reload plugin {plugin_name}: {e}")
                return False

        logger.warning(f"Cannot reload plugin {plugin_name}: module info not available")
        return False

    # ==================== 触发器专用辅助 ====================

    def activate_trigger(self, plugin_name: str, canvas_name: str, node, callback: callable, properties: dict) -> bool:
        """
        激活触发器插件（创建实例并调用 activate）
        供外部 TriggerManager 调用
        """
        trigger_class = self.get_trigger_plugin(plugin_name)
        if not trigger_class:
            logger.error(f"Trigger plugin '{plugin_name}' not found")
            return False

        try:
            # 创建实例（每次激活可创建新实例，或缓存复用）
            instance = trigger_class()
            instance.manager = self  # 确保 manager 引用

            # 调用激活方法
            instance.activate(canvas_name, node, callback, properties)
            logger.debug(f"Activated trigger [{plugin_name}] for node {node}")
            return True
        except Exception as e:
            logger.error(f"Failed to activate trigger {plugin_name}: {e}")
            return False

    def callback(self, node_id: str, callback_data: dict):
        """
        触发器回调转发（兼容 BaseTriggerPlugin.callback）
        实际业务中应由具体 TriggerManager 处理
        """
        # 默认实现：日志记录 + 可扩展钩子
        logger.debug(f"Trigger callback received: node={node_id}, data={callback_data}")
        # TODO: 可添加事件总线转发等逻辑