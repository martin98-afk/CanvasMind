# -*- coding: utf-8 -*-
from enum import Enum

class CanvasGridStyle(str, Enum):
    LINES = "线网格"
    DOTS = "点网格"
    NONE = "无网格"

class CanvasPipeStyle(str, Enum):
    ANGLED = "折线"
    CURVED = "曲线"
    STRAIGHT = "直线"

class CanvasDirection(int, Enum):
    HORIZONTAL = 0
    VERTICAL = 1

# UI constants
MAX_VISIBLE_QUICK_BUTTONS = 7
CONSOLE_HEIGHT = 300
DEFAULT_SPLITTER_SIZES = [150, 800, 150]
BUTTONS_CONTAINER_X_OFFSET = 190
NAME_LABEL_HEIGHT = 30
ENV_SELECTOR_HEIGHT = 30
PIPELINE_STYLE = {
    "折线": 0,
    "曲线": 2,
    "直线": 3,
}
GRID_STYLE = {
    "线网格": 1,
    "点网格": 2,
    "无网格": 0,
}
PIPELINE_DIRECTION = {
    "水平": 0,
    "垂直": 1
}