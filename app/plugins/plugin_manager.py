# -*- coding: utf-8 -*-
import importlib
import inspect
import os

from loguru import logger


class NodePluginManager:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance.plugins = {}
        return cls._instance

    def load_plugins(self, root_dir):
        """
        递归扫描目录并加载所有继承自 BaseNodePlugin 的类
        :param root_dir: 插件根目录的绝对路径
        """
        # 1. 确定根包名
        parts = root_dir.replace("\\", "/").split("/")
        try:
            # 这里自动寻找 'app' 目录作为包名起始点，你可以根据实际情况调整
            start_index = parts.index("app")
            base_package_path = ".".join(parts[start_index:])
        except ValueError:
            logger.error(f"路径 {root_dir} 中未找到 'app' 根包名，请检查目录结构")
            return

        # 2. 递归遍历目录
        for root, dirs, files in os.walk(root_dir):
            for filename in files:
                if filename.endswith(".py") and not filename.startswith("__"):
                    # 计算相对路径并转为模块路径
                    # 例如: /app/plugins/display/image_plugin.py -> app.plugins.display.image_plugin
                    rel_path = os.path.relpath(os.path.join(root, filename), root_dir)
                    module_rel_name = rel_path[:-3].replace(os.path.sep, ".")
                    full_module_name = f"{base_package_path}.{module_rel_name}"

                    try:
                        # 3. 动态加载模块
                        module = importlib.import_module(full_module_name)

                        # 4. 遍历模块中的所有类
                        for name, obj in inspect.getmembers(module):
                            if inspect.isclass(obj):
                                # 检查是否定义了 plugin_id 且不是基类本身
                                if hasattr(obj, "plugin_id") and obj.plugin_id:
                                    # 过滤掉基类
                                    if name not in ["DisplayPlugin", "InteractivePlugin", "BaseNodePlugin"]:
                                        plugin_instance = obj()
                                        self.plugins[plugin_instance.plugin_id] = plugin_instance
                                        logger.info(
                                            f"已加载插件 [{plugin_instance.plugin_id}] 来自模块: {full_module_name}")
                    except Exception as e:
                        logger.error(f"加载模块 {full_module_name} 失败: {e}")

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)