# -*- coding: utf-8 -*-
from app.widgets.side_dock_area.plugins.export_project_info.main_widget import ProjectInfoTool
from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import OpenAIChatToolWindow
from app.widgets.side_dock_area.plugins.service_request.main_widget import ServiceTestTool
from app.widgets.side_dock_area.registry import SideDockRegistry
from app.widgets.side_dock_area.tool_window import DockPosition


SideDockRegistry.register("项目管理", ProjectInfoTool.name, ProjectInfoTool, DockPosition.TOP)
SideDockRegistry.register("项目管理", ServiceTestTool.name, ServiceTestTool, DockPosition.TOP)
SideDockRegistry.register("项目管理", OpenAIChatToolWindow.name, OpenAIChatToolWindow, DockPosition.TOP)


DEFAULT_SPLITTER_SIZES = [100, 700]
HIDE_SPLITTER_SIZES = [100, 0]