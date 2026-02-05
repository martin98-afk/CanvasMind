from app.widgets.side_dock_area.plugins.canvas_execution_records.main_widget import ExecutionHistoryWindow
from app.widgets.side_dock_area.plugins.canvas_node_log.main_widget import LogToolWindow
from app.widgets.side_dock_area.plugins.component_readme.main_widget import NodeDocToolWindow
from app.widgets.side_dock_area.plugins.dependency_check.main_widget import DependencyToolWindow
from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import OpenAIChatToolWindow
from app.widgets.side_dock_area.plugins.plugin_template_tool.main_widget import PluginTemplateToolWindow
from app.widgets.side_dock_area.plugins.property_panel.main_widget import PropertyToolWindow
from app.widgets.side_dock_area.plugins.standalone_ipython_console.ipython_console import IPythonConsoleToolWindow
from app.widgets.side_dock_area.registry import SideDockRegistry
from app.widgets.side_dock_area.tool_window import DockPosition

category = "运行画布"

SideDockRegistry.register(category, PropertyToolWindow.name, PropertyToolWindow)
SideDockRegistry.register(category, DependencyToolWindow.name, DependencyToolWindow)
SideDockRegistry.register(category, NodeDocToolWindow.name, NodeDocToolWindow)
SideDockRegistry.register(category, PluginTemplateToolWindow.name, PluginTemplateToolWindow, DockPosition.TOP)


SideDockRegistry.register(category, OpenAIChatToolWindow.name, OpenAIChatToolWindow)
SideDockRegistry.register(category, IPythonConsoleToolWindow.name, IPythonConsoleToolWindow)
SideDockRegistry.register(category, ExecutionHistoryWindow.name, ExecutionHistoryWindow)
SideDockRegistry.register(category, LogToolWindow.name, LogToolWindow)