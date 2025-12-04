# -*- coding: utf-8 -*-
from enum import Enum

from NodeGraphQt.constants import PipeLayoutEnum, ViewerEnum


# UI constants
MAX_VISIBLE_QUICK_BUTTONS = 7
CONSOLE_HEIGHT = 300
CONSOLE_SPLITTER_SIZES = [400, 400]
DEFAULT_SPLITTER_SIZES = [150, 800, 150]
HIDE_SPLITTER_SIZES = [150, 800, 0]
BUTTONS_CONTAINER_X_OFFSET = 150
NAME_LABEL_HEIGHT = 30
ENV_SELECTOR_HEIGHT = 30
PIPELINE_STYLE = {
    "折线": PipeLayoutEnum.ANGLE.value,
    "曲线": PipeLayoutEnum.CURVED.value,
    "直线": PipeLayoutEnum.STRAIGHT.value,
}
GRID_STYLE = {
    "线网格": ViewerEnum.GRID_DISPLAY_LINES.value,
    "点网格": ViewerEnum.GRID_DISPLAY_DOTS.value,
    "无网格": ViewerEnum.GRID_DISPLAY_NONE.value,
}
PIPELINE_DIRECTION = {
    "水平": 0,
    "垂直": 1
}


LLM_GRAPH_CONTEXT_NORMS = """## 节点引用规范

- 当你认为需要用户追溯到画布中实际节点时，严格按照以下格式引用:

[节点名称](jump)

- **节点名称**必须与画布中显示的名称**完全一致**(区分大小写和空格)。
- **不得修改 `(jump)`**，不要写成 `(jump:xxx)` 或其他形式。
- **仅在确实指代某个节点时才使用此格式**，普通描述无需引用。

正确示例:
- 节点 [图像预处理](jump) 的输入维度不匹配。
- 建议先运行 [数据加载器](jump) 获取样本。

错误示例:
- [jump](数据加载器):格式颠倒
- [数据加载器](jump:node_123):多了参数
- [数据加载器](inspect):不支持的操作
- [csv读取器 - 参数](jump):只支持严格节点名跳转，不能加参数

在思考中、代码、流程图中可直接使用节点名称进行代指。
"""


NODE_CREATE_CONTEXT_NORMS = """## 节点创建规范

- 当你认为想推荐用户创建某节点时，严格按照以下格式引用:

[组件名称](create)

- **组件名称**必须与当前提供的组件名称列表**完全一致**(区分大小写和空格)。
- **不得修改 `(create)`**，不要写成 `(create:xxx)` 或其他形式。
- **仅在确实指代某个组件时才使用此格式**，普通描述无需引用。

正确示例:
- 节点 [图像预处理](create) 的输入维度不匹配。
- 建议先运行 [数据加载器](create) 获取样本。

错误示例:
- [create](数据加载器):格式颠倒
- [数据加载器](create:node_123):多了参数
- [数据加载器](inspect):不支持的操作

在思考中、代码、流程图中可直接使用组件名称进行代指，只有在推荐创建组件时使用此规范。
"""