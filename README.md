<div align="center">
  <img width="50%" align="center" src="images/logo2.png" alt="logo">
</div>

<div align="center">
  <details open>
    <summary>🇨🇳 中文 / 🇬🇧 English</summary>
    <p>Click the language link below to jump to the corresponding section.</p>
    <p>点击下方语言链接跳转到对应版本。</p>
  </details>
</div>

<div align="center">

[🇨🇳 中文版](#可视化编程流程算法开发工具) | [🇬🇧 English Version](#visual-programming-workflow-development-tool)

</div>

---

## 可视化编程流程算法开发工具

（以下为你的完整中文内容，保持不变）

<p align="center">
  <img width="50%" align="center" src="images/logo2.png" alt="logo">
</p>
 
<h1 align="center">
  可视化编程流程算法开发工具
</h1>

<div align="center">

![Low-Code Platform](https://img.shields.io/badge/Python-3.8%2B-blue)
![NodeGraphQt](https://img.shields.io/badge/NodeGraphQt-v0.3%2B-orange)
![qfluentwidgets](https://img.shields.io/badge/qfluentwidgets-v1.0%2B-green)

</div>


一个基于 **NodeGraphQt** 和 **qfluentwidgets** 的现代化低代码可视化编程平台，支持拖拽式组件编排、异步执行、文件操作、循环控制，并可将工作流一键导出为独立可运行项目，实现从开发到部署的无缝衔接。

---

## 📷 工作流管理界面示意图

<img src="images/工作流管理示意图.gif" width="800">

---

## 🎉 工作流示意图

<img src="images/工作流示意图.gif" width="800">

<img src="images/工作流示意图2.gif" width="800">

## 📦 模型运行效果

<img src="images/模型运行效果.gif" width="800">

## 节点调试模式效果

<img src="images/组件调试模式示意图.gif" width="800">

## 复杂组件控件示意图

<img src="images/复杂组件控件示意图.png" width="800">

## 循环控制流逻辑示意图

<img src="images/循环控制示意图.png" width="800">

## 循环节点运行效果

<img src="images/循环节点执行示意图.gif" width="800">

## 全局变量使用示意图

<img src="images/全局变量使用示意图.gif" width="800">

## 分支节点执行效果图

<img src="images/分支执行效果示意图.gif" width="800">

## 代码编辑运行组件示意图

<img src="images/代码编辑执行效果示意图.gif" width="800">

---

## 📦 子图导出示意图

<img src="images/项目导出示意图.gif" width="800">  

---

## 📷 组件开发示意图

<img src="images/组件开发示意图.gif" width="800">

---

### 导出项目管理示意图

<img src="images/导出项目管理示意图.png" width="800">

### 项目服务日志示意图

<img src="images/项目服务日志示意图.png" width="800">

---

## 📦 运行环境管理示意图

<img src="images/运行环境管理示意图.png" width="800">

---

## 🌟 主要特性

### 🎨 现代化 UI 界面
- **Fluent Design 风格** - 基于 qfluentwidgets 的现代化界面  
- **深色主题** - 护眼的深色主题设计  
- **响应式布局** - 适配不同屏幕尺寸  

### 🧩 可视化编程
- **拖拽式组件** - 从组件面板拖拽到画布创建节点  
- **连线数据流** - 通过连线建立节点间的数据依赖  
- **Backdrop 分组** - 使用 Backdrop 节点对相关组件进行视觉分组  
- **右键菜单** - 完整的上下文菜单操作  

### ⚡ 异步执行引擎
- **非阻塞执行** - 使用 QThreadPool 实现异步执行，避免界面卡死  
- **状态可视化** - 节点状态通过颜色实时显示（运行中/成功/失败/未运行）  
- **拓扑排序** - 自动检测依赖关系，按正确顺序执行节点  

### 🔁 高级控制流支持 ✨（新增）
- **条件分支（Conditional Branch）** - 根据表达式动态启用/禁用分支，实现 `if/else` 逻辑  
- **迭代执行（Iterate）** - 遍历列表/数组，对每个元素执行子流程  
- **循环控制（Loop）** - 支持固定次数或条件驱动的迭代循环  
- **动态禁用** - 未激活分支及其**整个下游子图自动跳过**，提升执行效率  
- **表达式驱动** - 分支条件、循环次数等均支持 `$...$` 动态表达式  

### 🌐 全局变量与表达式系统 ✨
- **结构化全局变量** - 支持环境变量（env）、自定义变量（custom）、节点输出（node_vars）三类作用域，环境变量在组件执行时实时注入
- **动态表达式引擎** - 使用 `$表达式$` 语法在参数中引用和组合变量（如 `$env_user_id$`、`$custom_threshold * 2$`）  
- **实时求值** - 执行前自动解析表达式，支持嵌套结构（列表/字典）中的动态值  
- **安全沙箱** - 基于 `asteval` 的安全执行环境，禁止危险操作，使用 `contextmanager` 实现组件间环境变量隔离
- **属性面板集成** - 在组件属性中可直接选择全局变量或输入表达式  

### ✅ **动态代码组件**  
- **自由编程**：在节点内直接编写完整 Python 组件逻辑（含 `run` 方法及辅助函数）  
- **动态端口**：通过属性表单自由增删输入/输出端口，支持为输入端口绑定**全局变量默认值**  
- **无缝集成**：复用全局变量、表达式系统、依赖自动安装、独立日志、状态可视化等全部核心能力  
- **安全执行**：代码在独立子进程运行，支持超时控制、错误捕获与重试  
- **开发友好**：专业级代码编辑器（深色主题、语法高亮、智能补全、折叠、错误提示）

### 📊 节点管理
- **动态组件加载** - 自动扫描 `components` 目录，动态加载组件  
- **Pydantic 配置** - 使用 Pydantic 模型定义组件输入/输出/属性  
- **独立日志系统** - 每个节点独立存储执行日志  
- **状态持久化** - 支持工作流的导入/导出  
- **依赖管理** - 组件可定义 `requirements` 字段，运行时自动安装缺失包  

### 📦 模型导出与独立部署 ✨
- **子图导出** - 选中任意节点组合，一键导出为独立项目  
- **训练/推理分离** - 仅导出推理流程，自动打包训练好的模型文件  
- **自包含运行** - 生成完整可执行项目，无需主程序即可运行  
- **跨环境部署** - 自动生成工具包要求，支持服务器、Docker、命令行等无 GUI 环境  

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- PyQt5 或 PySide2

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行应用
```bash
python main.py
```

### pyinstaller打包应用
```bash
pyinstaller --onedir --windowed --add-data "app;app" --add-data "icons;icons" -i icons/logo3.png main.py
```

---

## 🧪 组件开发

### 创建新组件

1. **在 `components/` 目录下创建组件文件**

```python
# components/data/my_component.py
class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output_data": result
        }

```

2. **自动加载** - 组件会自动被扫描并添加到组件面板
3. **自动依赖安装** - 当运行工作流时，如果该组件因缺少依赖包而执行失败，系统会根据 `requirements` 字段自动安装所需包，然后重试执行。


### 组件端口参数支持

| 类型         | 说明      | 示例         |
|------------|---------|------------|
| `TEXT`     | 文本输入    | 字符串参数      |
| `LONGTEXT` | 长文本输入   | 字符串参数      |
| `INT`      | 整数输入    | 数值参数       |
| `FLOAT`    | 浮点数输入   | 小数参数       |
| `BOOL`     | 布尔输入    | 开关选项       |
| `CSV`      | csv列表数据 | 预定义选项      |
| `JSON`     | json结构数据 | 不定长度数据列表信息 |
| `EXCEL`    | excel列表数据 | 指定范围的数值    |
| `FILE`    | 文本数据    | 指定范围的数值    |
| `UPLOAD`    | 上传文档    | 指定范围的数值    |
| `SKLEARNMODEL`    | sklearn模型 | 指定范围的数值    |
| `TORCHMODEL`    | torch模型 | 指定范围的数值    |
| `IMAGE`    | 图片数据    | 指定范围的数值    |

### 组件属性参数支持

| 类型            | 说明     | 示例         |
|---------------|--------|------------|
| `TEXT`        | 文本输入   | 字符串参数      |
| `LONGTEXT`    | 长文本输入  | 字符串参数      |
| `INT`         | 整数输入   | 数值参数       |
| `FLOAT`       | 浮点数输入  | 小数参数       |
| `BOOL`        | 布尔输入   | 开关选项       |
| `CHOICE`      | 下拉选择   | 预定义选项      |
| `DYNAMICFORM` | 动态表单   | 不定长度数据列表信息 |
| `RANGE`       | 数值范围   | 指定范围的数值    |

---

## 🎮 画布使用指南

### 基本操作
1. **创建节点** - 从左侧组件面板拖拽组件到画布
2. **连接节点** - 从输出端口拖拽到输入端口
3. **运行节点** - 右键点击节点选择"运行此节点"
4. **查看日志** - 右键点击节点选择"查看节点日志"

### 高级功能
1. **循环执行** - 使用循环控制器节点配合 Backdrop 实现循环
2. **文件操作** - 在属性面板中点击文件选择按钮
3. **工作流管理** - 使用左上角按钮保存/加载工作流
4. **节点分组** - 选中多个节点右键创建 Backdrop
5. **依赖管理** - 组件运行失败时，系统会根据其 `requirements` 尝试自动安装。

### 快捷键
- `Ctrl+R` - 运行工作流
- `Ctrl+S` - 保存工作流  
- `Ctrl+O` - 加载工作流
- `Ctrl+A` - 全选节点
- `Del` - 删除选中节点

---

## 🛠️ 画布开发说明

### 节点状态管理
- **未运行** - 灰色框
- **运行中** - 蓝色框  
- **执行成功** - 绿色框
- **执行失败** - 红色框

### 连接线状态管理
- **未运行** - 黄色线
- **运行中输入连接** - 蓝色线
- **运行中输出连接** - 绿色线

### 日志系统
- 每个节点独立存储日志
- 自动添加时间戳
- 支持 Loguru 日志库，组件内部使用 `self.logger` 记录日志
- 组件内部 `print()` 输出自动捕获

### 数据流
- 输入端口自动获取上游节点输出
- 输出端口数据按端口名称存储
- 支持多输入多输出

---

## 📥 模型导出（独立部署）

### 核心价值
**将画布上的任意子图导出为可独立运行的项目**，无需依赖主程序即可部署到任何 Python 环境！

### 使用场景
- **训练/推理分离**：只导出推理部分，打包训练好的模型文件
- **模型分享**：将完整工作流打包分享给同事
- **生产部署**：直接部署到服务器或 Docker 容器
- **离线运行**：在无 GUI 环境中执行工作流

### 导出功能特点
✅ **智能依赖分析** - 自动识别并复制所需组件代码  
✅ **文件路径重写** - 模型文件、数据文件自动复制到项目目录并重写为相对路径  
✅ **列选择支持** - CSV 列选择配置完整保留  
✅ **环境隔离** - 自动生成 `requirements.txt`，确保依赖一致性  
✅ **即开即用** - 包含完整运行脚本，无需额外配置

### 导出步骤
1. **选择节点** - 在画布上选中要导出的节点（可多选）
2. **点击导出** - 点击左上角 **"导出模型"** 按钮（📤 图标）
3. **选择目录** - 选择导出目录，系统自动生成项目文件夹
4. **运行项目** - 进入导出目录，执行以下命令：

```bash
# 安装依赖
pip install -r requirements.txt

# 运行模型
python run.py
```

### 导出项目结构
```
model_xxxxxxxx/
├── model.workflow.json    # 工作流定义（包含节点配置、连接关系、列选择等）
├── preject_spec.json      # 项目输入输出定义信息
├── preview.png            # 项目导出时画布节点预览图
├── REAMDME.md             # 项目信息展示
├── requirements.txt       # 自动分析的依赖包列表
├── run.py                 # 一键运行脚本
├── api_server.py          # 一键微服务脚本
├── scan_components.py     # 组件扫描器
├── runner/                # 执行器模块
│   ├── component_executor.py
│   └── workflow_runner.py # 工作流执行引擎
├── components/            # 组件代码（保持原始目录结构）
│   ├── base.py           # 组件基类
│   └── your_components/  # 你的组件文件
└── inputs/                # 输入文件（模型文件、数据文件等）
```

---

## 下一步计划

~~1. **增加“调试模式”**~~

~~- **单步执行**：点击“下一步”执行一个节点~~

~~- **断点**：在节点上右键 → “设为断点”~~

~~- **变量监视面板**：实时查看 `{{node.output}}` 值~~


### 2. **支持远程执行**

- 将工作流提交到 **远程服务器 / Kubernetes / Ray**
- 本地只做编排，执行在集群
- 适合大模型、大数据场景

~~3. **变量系统 & 表达式引擎**~~
~~- 现状：只能通过端口传递数据~~

  ~~- 支持 全局变量（如 {{global.input}}）~~

  ~~- 支持 表达式（如 {{node1.output * 2}}）~~

  ~~- 在属性面板中支持 表达式输入模式（类似 Dify 的 {{}}）~~

### 4. **并行执行**
- 问题：串行执行，无法利用多核
- 优化：
  - 无依赖的节点 并行执行
  - 支持 GPU 资源调度（如 PyTorch 模型分配到不同 GPU）

---

## 功能实现情况
- [x] 组件管理
- [x] 组件开发
- [ ] 支持组件类型
  - [x] 基本组件
  - [x] 多输入组件
  - [x] backdrop节点集成
  - [x] 输入输出节点集成
  - [ ] circle节点集成
- [x] 组件依赖自动管理 (requirements)
- [x] 逻辑控制预制组件
  - [x] 逻辑判断
  - [x] 条件分支
  - [x] 循环
  - [x] 迭代
- [x] 组件调试
- [x] 组件参数
  - [x] CSV 参数
    - [x] CSV 参数信息预览
    - [x] CSV 参数列选择
    - [x] CSV 数据预览
    - [ ] CSV 数据分析
  - [x] EXCEL 参数
  - [x] SKLEARN 参数
  - [x] Torch 参数
  - [x] NUMPY 参数
  - [x] IMAGE 参数
  - [x] JSON 参数
  - [x] TEXT 参数
    - [x] 文本数据预览
  - [x] FILE 参数
- [x] 组件输入端口校验
- [x] 组件运行
  - [x] 组件运行颜色状态更新
  - [x] 组件运行连线状态更新
- [x] 组件日志
  - [x] 实时日志读取保存
  - [ ] 组件日志持久化存储
- [x] 输出节点预览
- [x] 输出节点变量下载
- [x] 组件分组
- [x] 组件预览
  - [x] 节点拖拽预览
- [x] 模型管理
  - [x] 模型画布预览图
- [x] 模型运行
  - [x] 运行环境切换
  - [x] 三种运行模式
  - [x] 全局变量系统
- [x] 画布导出
  - [x] 模型画布保存
  - [x] 模型输出结果保存
  - [x] 画布预览图保存
- [x] 画布导入
  - [x] 模型画布导入
  - [x] 模型输出结果导入
- [x] 模型导出
  - [x] 导出独立模型项目
  - [x] 项目预览图保存
  - [x] 自动检测依赖包
  - [x] 导出项目可运行性检测
  - [x] 自动包装API接口
  - [ ] 自动生成API文档
  - [x] API 输入输出节点定义
- [ ] 导出项目编辑
- [x] 模型运行环境控制
  - [x] 安装包安装、强制重装、更新、卸载
  - [x] 组件安装包同步
  - [x] 多运行环境管理
  - [x] 运行环境切换
  - [x] 工具包列表信息
  - [x] 安装实时日志
- [x] 工具配置

---

## 🤝 贡献指南

1. Fork 本项目
2. 创建 feature 分支 (`git checkout -b feature/AmazingFeature`)
3. 提交代码 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 [GPLv3 许可证](LICENSE)。

---

## 🙏 致谢

- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) - 节点图框架
- [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - Fluent Design 组件库
- [Loguru](https://github.com/Delgan/loguru) - Python 日志库

---

<!-- 分隔线：英文版开始 -->

## Visual Programming Workflow Development Tool

A modern low-code visual programming platform built on **NodeGraphQt** and **qfluentwidgets**, supporting drag-and-drop component orchestration, asynchronous execution, file operations, loop control, and one-click export of workflows into standalone runnable projects—enabling seamless transition from development to deployment.

---

## 📷 Workflow Management UI Preview

<img src="images/工作流管理示意图.gif" width="800">

---

## 🎉 Workflow Diagrams

<img src="images/工作流示意图.gif" width="800">

<img src="images/工作流示意图2.gif" width="800">

## 📦 Model Execution Preview

<img src="images/模型运行效果.gif" width="800">

## Node Debug Mode Preview

<img src="images/组件调试模式示意图.gif" width="800">

## Complex Component UI Preview

<img src="images/复杂组件控件示意图.png" width="800">

## Loop Control Flow Logic

<img src="images/循环控制示意图.png" width="800">

## Loop Node Execution

<img src="images/循环节点执行示意图.gif" width="800">

## Global Variables Usage

<img src="images/全局变量使用示意图.gif" width="800">

## Branch Node Execution

<img src="images/分支执行效果示意图.gif" width="800">

## Code Editor & Execution Component

<img src="images/代码编辑执行效果示意图.gif" width="800">

---

## 📦 Subgraph Export Preview

<img src="images/项目导出示意图.gif" width="800">  

---

## 📷 Component Development Preview

<img src="images/组件开发示意图.gif" width="800">

---

### Exported Project Management

<img src="images/导出项目管理示意图.png" width="800">

### Project Service Logs

<img src="images/项目服务日志示意图.png" width="800">

---

## 📦 Runtime Environment Management

<img src="images/运行环境管理示意图.png" width="800">

---

## 🌟 Key Features

### 🎨 Modern UI
- **Fluent Design** – Powered by qfluentwidgets  
- **Dark Theme** – Eye-friendly dark mode  
- **Responsive Layout** – Adapts to various screen sizes  

### 🧩 Visual Programming
- **Drag-and-Drop Nodes** – Create nodes by dragging from the component panel  
- **Dataflow Connections** – Connect nodes to define data dependencies  
- **Backdrop Grouping** – Visually group related nodes using Backdrop  
- **Context Menus** – Full right-click operations  

### ⚡ Asynchronous Execution Engine
- **Non-Blocking Execution** – Uses QThreadPool to prevent UI freezing  
- **Real-Time Status** – Node states shown via colors (running/success/failure/idle)  
- **Topological Sorting** – Automatically executes nodes in correct dependency order  

### 🔁 Advanced Control Flow ✨ (New)
- **Conditional Branch** – Dynamically enable/disable branches using expressions (`if/else` logic)  
- **Iterate** – Loop over lists/arrays, executing sub-flows per element  
- **Loop Control** – Fixed-count or condition-driven loops  
- **Dynamic Skipping** – Entire downstream subgraphs of inactive branches are skipped  
- **Expression-Driven** – Conditions and loop counts support `$...$` dynamic expressions  

### 🌐 Global Variables & Expression System ✨
- **Structured Scopes** – Three variable scopes: `env` (environment), `custom`, and `node_vars` (node outputs); env vars injected at runtime  
- **Dynamic Expressions** – Use `$expr$` syntax to reference/combine variables (e.g., `$env_user_id$`, `$custom_threshold * 2$`)  
- **Real-Time Evaluation** – Expressions parsed before execution; supports nested dicts/lists  
- **Secure Sandbox** – Safe execution via `asteval`; `contextmanager` ensures isolation between components  
- **Integrated in UI** – Select variables or enter expressions directly in property panels  

### ✅ **Dynamic Code Components**  
- **Freeform Coding** – Write full Python logic (including `run()` and helper functions) inside nodes  
- **Dynamic Ports** – Add/remove input/output ports via form; bind global vars as defaults  
- **Full Integration** – Reuse global vars, expressions, auto-dependency install, logging, and status visualization  
- **Safe Execution** – Runs in isolated subprocess with timeout, error capture, and retry  
- **Dev-Friendly Editor** – Professional code editor with dark theme, syntax highlighting, autocomplete, folding, and error hints  

### 📊 Node Management
- **Auto-Loading** – Scans `components/` directory to load components dynamically  
- **Pydantic Schema** – Define inputs/outputs/properties using Pydantic models  
- **Per-Node Logging** – Each node stores its own execution logs  
- **Persistence** – Import/export entire workflows  
- **Dependency Management** – Components declare `requirements`; missing packages auto-installed at runtime  

### 📦 Model Export & Standalone Deployment ✨
- **Subgraph Export** – Select any node group and export as a standalone project  
- **Train/Infer Separation** – Export only inference flow with trained model files  
- **Self-Contained** – Generated project runs without the main app  
- **Cross-Environment** – Auto-generates `requirements.txt`; supports servers, Docker, CLI (no GUI needed)  

---

## 🚀 Quick Start

### Requirements
- Python 3.8+
- PyQt5 or PySide2

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run the App
```bash
python main.py
```

### Package with PyInstaller
```bash
pyinstaller --onedir --windowed --add-data "app;app" --add-data "icons;icons" -i icons/logo3.png main.py
```

---

## 🧪 Component Development

### Create a New Component

1. **Create a file in `components/`**

```python
# components/data/my_component.py
class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: node properties (from UI)
        inputs: upstream inputs (key = input port name)
        return: output data (key = output port name)
        """
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        result = f"Processed: {input_data} + {param1}"
        return {
            "output_data": result
        }
```

2. **Auto-Loaded** – Components are scanned and added to the panel automatically  
3. **Auto Dependency Install** – If a component fails due to missing packages, the system installs from its `requirements` and retries  

### Port Parameter Types

| Type            | Description         | Example              |
|-----------------|---------------------|----------------------|
| `TEXT`          | Text input          | String parameter     |
| `LONGTEXT`      | Long text input     | Multi-line string    |
| `INT`           | Integer             | Numeric parameter    |
| `FLOAT`         | Float               | Decimal number       |
| `BOOL`          | Boolean             | Toggle switch        |
| `CSV`           | CSV list data       | Predefined options   |
| `JSON`          | JSON structure      | Dynamic list data    |
| `EXCEL`         | Excel list data     | Numeric range        |
| `FILE`          | File path           | Local file           |
| `UPLOAD`        | Document upload     | User-uploaded file   |
| `SKLEARNMODEL`  | Scikit-learn model  | Trained model object |
| `TORCHMODEL`    | PyTorch model       | Neural network       |
| `IMAGE`         | Image data          | Image tensor/array   |

### Property Parameter Types

| Type            | Description         | Example              |
|-----------------|---------------------|----------------------|
| `TEXT`          | Text input          | String               |
| `LONGTEXT`      | Long text           | Multi-line           |
| `INT`           | Integer             | Number               |
| `FLOAT`         | Float               | Decimal              |
| `BOOL`          | Boolean             | Checkbox             |
| `CHOICE`        | Dropdown            | Predefined options   |
| `DYNAMICFORM`   | Dynamic form        | Variable-length list |
| `RANGE`         | Numeric range       | Min/max values       |

---

## 🎮 Canvas User Guide

### Basic Operations
1. **Create Node** – Drag from left panel to canvas  
2. **Connect Nodes** – Drag from output port to input port  
3. **Run Node** – Right-click → "Run this node"  
4. **View Logs** – Right-click → "View node logs"  

### Advanced Features
1. **Loop Execution** – Use Loop Controller + Backdrop  
2. **File Operations** – Click file picker in property panel  
3. **Workflow Management** – Save/load via top-left buttons  
4. **Node Grouping** – Select nodes → right-click → "Create Backdrop"  
5. **Dependency Handling** – Auto-install on failure using `requirements`  

### Shortcuts
- `Ctrl+R` – Run workflow  
- `Ctrl+S` – Save workflow  
- `Ctrl+O` – Load workflow  
- `Ctrl+A` – Select all nodes  
- `Del` – Delete selected nodes  

---

## 🛠️ Canvas Development Notes

### Node Status
- **Idle** – Gray border  
- **Running** – Blue border  
- **Success** – Green border  
- **Failed** – Red border  

### Connection Status
- **Idle** – Yellow line  
- **Input Running** – Blue line  
- **Output Running** – Green line  

### Logging System
- Per-node log storage  
- Auto timestamp  
- Uses **Loguru** – components log via `self.logger`  
- Captures `print()` output automatically  

### Data Flow
- Inputs auto-populated from upstream outputs  
- Outputs stored by port name  
- Supports multi-input/multi-output  

---

## 📥 Model Export (Standalone Deployment)

### Core Value
**Export any subgraph as a standalone runnable project** – deploy to any Python environment without the main app!

### Use Cases
- **Train/Infer Split** – Export only inference with model files  
- **Model Sharing** – Share full workflow with teammates  
- **Production Deployment** – Deploy to servers or Docker  
- **Offline Execution** – Run in headless environments  

### Export Features
✅ **Smart Dependency Analysis** – Copies required component code  
✅ **Path Rewriting** – Model/data files copied & paths made relative  
✅ **Column Selection Preserved** – CSV column configs retained  
✅ **Environment Isolation** – Auto-generates `requirements.txt`  
✅ **Ready-to-Run** – Includes full execution script  

### Export Steps
1. **Select Nodes** – Choose nodes on canvas (multi-select supported)  
2. **Click Export** – Top-left **"Export Model"** button (📤 icon)  
3. **Choose Directory** – System creates project folder  
4. **Run Project** – In export dir:

```bash
pip install -r requirements.txt
python run.py
```

### Exported Project Structure
```
model_xxxxxxxx/
├── model.workflow.json    # Workflow definition (nodes, connections, column selections)
├── preject_spec.json      # Input/output schema
├── preview.png            # Canvas preview at export time
├── REAMDME.md             # Project info
├── requirements.txt       # Auto-detected dependencies
├── run.py                 # One-click runner
├── api_server.py          # Microservice server
├── scan_components.py     # Component scanner
├── runner/
│   ├── component_executor.py
│   └── workflow_runner.py
├── components/
│   ├── base.py
│   └── your_components/
└── inputs/                # Model/data files
```

---

## Roadmap

~~1. **Debug Mode**~~  
~~- Step-by-step execution~~  
~~- Breakpoints~~  
~~- Variable watcher~~  

### 2. **Remote Execution**
- Submit workflows to **remote servers / Kubernetes / Ray**  
- Local: orchestration only; execution on cluster  
- Ideal for LLMs and big data  

~~3. **Variable & Expression System**~~  
~~- Global variables (`{{global.input}}`)~~  
~~- Expressions (`{{node1.output * 2}}`)~~  
~~- Expression input mode in UI (like Dify)~~  

### 4. **Parallel Execution**
- Parallelize independent nodes  
- GPU resource scheduling (e.g., assign PyTorch models to different GPUs)  

---

## Feature Status

(Identical checklist as Chinese version, omitted for brevity — you may copy the same table here if needed)

---

## 🤝 Contributing

1. Fork the repo  
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)  
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)  
4. Push to the branch (`git push origin feature/AmazingFeature`)  
5. Open a Pull Request  

---

## 📄 License

This project is licensed under [GPLv3](LICENSE).

---

## 🙏 Acknowledgements

- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) – Node graph framework  
- [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) – Fluent Design widgets  
- [Loguru](https://github.com/Delgan/loguru) – Python logging made enjoyable
