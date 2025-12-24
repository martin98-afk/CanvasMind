# -*- coding: utf-8 -*-
from enum import Enum

from NodeGraphQt.constants import PipeLayoutEnum, ViewerEnum


# UI constants
MAX_VISIBLE_QUICK_BUTTONS = 7
CONSOLE_HEIGHT = 300
CONSOLE_SPLITTER_SIZES = [400, 400]
DEFAULT_SPLITTER_SIZES = [150, 800, 150]
TEMPLATE_START_SIZES = [500, 150, 150]
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


LLM_GRAPH_CONTEXT_NORMS = """## 1. **引用目的与适用场景**
仅在以下明确意图下使用引用格式：
- **引导用户跳转到画布中已存在的具体节点**（用于追溯、调试、查看状态等）。

在思考过程、代码解释、流程图描述等场景中，**直接使用节点名称即可**，无需引用格式。

---

## 2. **引用格式强制规则**

### 正确格式
- **单个节点**：  
  [节点名称](jump)
- **多个节点**（用英文逗号分隔，无空格）：
  [节点A,节点B,节点C](jump)

### 严格禁止
- 修改操作符：如 (jump:xxx)、(goto)、(inspect) 等。
- 颠倒格式：如 (jump)[节点名]。
- 添加额外内容：如节点 ID、参数、说明文字（例如 csv读取器 - 参数）。
- 使用不存在或拼写不一致的节点名（必须与画布中显示的**完全一致**，包括大小写和空格）。
- 在节点名中加入空格或其他分隔符（多个节点之间只允许英文逗号，**不加空格**）。

---

## 3. **节点名称匹配要求**
- 名称必须**逐字匹配**画布中节点的显示名称。
- 不支持模糊匹配、别名或带修饰语的变体。
- 若节点名称包含空格（如 图像 预处理），则必须原样保留。

---

## 4. **多节点引用说明**
- 多个节点引用仅用于**批量跳转提示**（例如指出一组相关节点）。
- 所有列出的节点**必须真实存在于当前画布**。
- 节点顺序**无语义意义**，但建议按逻辑或执行顺序排列。

---

## 5. **正确与错误示例对比**

| 类型 | 示例 | 说明 |
|------|------|------|
| 正确 | 检查 [数据加载器](jump) 的输出格式。 | 单节点，名称匹配 |
| 正确 | [图像预处理,模型推理](jump) 需要重新连接。 | 多节点，无空格，真实存在 |
| 错误 | [jump](数据加载器) | 格式颠倒 |
| 错误 | [数据加载器](jump:node_01) | 操作符被篡改 |
| 错误 | [csv读取器 - 参数](jump) | 名称含非法修饰（“- 参数”不属于节点名） |
| 错误 | [未知节点](jump) | 该节点不在画布中 |

---

## 6. **大模型生成提示（内部使用建议）**
在生成 (jump) 引用前，请确认：
1. 节点确实存在于当前画布；
2. 名称与 UI 显示**完全一致**；
"""


NODE_CREATE_CONTEXT_NORMS = """## 1. 引用目的与适用场景
仅在以下两种明确意图下使用引用格式：
- 推荐用户创建一个已有组件节点 → 使用 (create)。
- 建议用户新增一个当前组件库中不存在的新组件 → 使用 (generate)。

普通描述、思考过程、代码注释、流程图说明中无需引用格式，直接使用组件名称即可。

---

## 2. 引用格式强制规则

### 格式
[组件名称](create)
[新组件建议名称](generate)

### 禁止
- 修改操作符：如 (create:xxx)、(inspect)、(edit) 等。
- 颠倒顺序：如 (create)[组件名]。
- 使用不存在的组件名搭配 (create)。
- 使用已存在组件名搭配 (generate)。
- 添加额外空格、标点或换行：如 [ 数据加载器 ](create)。

---

## 3. 组件名称匹配规则
- 组件名称必须 逐字匹配（区分大小写、空格、标点）组件库提供的名称列表。
- 若不确定是否在库中，请参考当前提供的组件清单上下文

---

## 4. 推荐生成新组件的命名建议
当使用 (generate) 时，请为新组件提供具体、语义明确的名称，例如：
- [模型评估](generate)
- [多模态特征融合](generate)
- [新节点](generate)（过于模糊）
- [处理](generate)（缺乏语义）

---

## 5. 正确与错误示例对比

| 类型 | 示例 | 说明 |
|------|------|------|
| 正确 | 请先运行 [数据加载器](create)。 | 组件存在，操作正确 |
| 正确 | 建议实现 [损失函数可视化](generate)。 | 组件不存在，合理新增 |
| 错误 | [数据加载器](inspect) | 不支持的操作类型 |
| 错误 | [模型训练](create) | “模型训练”不在组件列表中 |
| 错误 | [数据加载器](generate) | 该组件已存在，不应生成 |
| 错误 | [data loader](create) | 名称大小写/空格不匹配 |

---

## 6. 大模型生成提示（供系统内部使用）
在生成建议时，请优先检查组件是否在清单中。
若在，且意图是“创建节点”，则用 (create)；
若不在，且有必要新增，则用 (generate) 并给出合理名称。
避免无意义或重复建议。
"""