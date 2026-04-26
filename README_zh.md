<!-- README_zh.md -->
<p align="center">
  <img width="50%" align="center" src="icons/logo.png" alt="logo">
</p>
 
<div align="center">
  <h1>可视化编程流程算法开发工具</h1>
  
  [🇨🇳 中文](README_zh.md) | [🇬🇧 English](README.md) | [📘 使用手册](https://canvasmind-sphinx-build.readthedocs.io/zh-cn/latest/) | [🎥 演示视频](https://www.bilibili.com/video/BV153zCBGEU2)

</div>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/github/license/martin98-afk/CanvasMind)
![Stars](https://img.shields.io/github/stars/martin98-afk/CanvasMind)
![Downloads](https://img.shields.io/github/downloads/martin98-afk/CanvasMind/total)
![Last Commit](https://img.shields.io/github/last-commit/martin98-afk/CanvasMind)
![Issues](https://img.shields.io/github/issues/martin98-afk/CanvasMind)

</div>

一个基于 **NodeGraphQt** 和 **qfluentwidgets** 的现代化低代码可视化编程平台，支持拖拽式组件编排、异步执行、文件操作、循环控制，并可将工作流一键导出为独立可运行项目，实现从开发到部署的无缝衔接。

<img src="images/宣传图.png" width="100%" height="100%"><br>

<img src="images/宣传图2.png" width="100%" height="100%"><br>

<img src="images/宣传图3.png" width="100%" height="100%"><br>

<img src="images/大模型对话框.png" width="100%" height="100%"><br>

<img src="images/文档差异对比.png" width="100%" height="100%"><br>

---

## 🌟 为什么选择 CanvasMind？

| 传统低代码工具           | CanvasMind                                         |
|-------------------|----------------------------------------------------|
| 静态组件拼接            | **动态表达式 + 全局变量** 驱动参数                              |
| 仅支持串行执行           | **条件分支 + 迭代 + 循环** 控制流                             |
| 无法自定义逻辑           | **内嵌代码编辑器**，自由编写 Python 组件                         |
| 执行即终点             | **一键导出独立项目**，支持 API、命令行、MCP 部署                     |
| 节点显示单一            | **支持多种控件类型**，可以展示 echarts 图表、图片及代码编辑器                |
| AI 与画布割裂          | **大模型深度集成**：黄色跳转 / 紫色创建，实现画布级智能补全                    |
| 运行环境固定            | **支持远程 ssh 执行**，集成 ssh 服务器 python 环境管理工具，并支持将节点发送到服务器端运行 |
| 没有触发器节点 或 触发方式硬编码 | **全插件化触发架构**：支持 Cron、Webhook、文件监听等插件动态扩展，实现零代码接入任意外部事件 |

---

## 🌟 主要特性

#### 核心特性 ✨

- **动态属性网格**  - 根据参数数据类型自动渲染适配的UI控件（文本输入、数值调节、文件选择器、开关按钮、滑块等），支持实时类型校验与范围约束，确保配置准确性。
- **层级化属性树**  - 采用可展开/折叠的树形结构组织嵌套配置项，支持拖拽重排序与父子关系可视化，轻松管理复杂工作流的多层参数体系。
- **交互式树导航**  - 通过右键菜单快速添加/删除节点，视觉标识清晰区分父级容器与叶节点，支持键盘快捷操作提升配置效率。

<img src="images/复杂节点控件1.png" width="100%" height="100%"><br>

### 🪟 多视角画布拆分 🛰️
*   **递归式视角拆分** —— 支持画布水平或垂直方向的无限拆分，便于在大规模工作流中同时监控物理距离较远的多个逻辑区域。
*   **场景状态实时同步** —— 所有视口共享同一个实时场景。在任一视角中对节点进行的编辑都会即时反映在所有视图中，实现极高的跨节点协作与参考效率。
*   **跨区域节点追踪** —— 完美适配复杂长流程开发。允许用户在一个视口中锁定查看"源头节点"的参数配置，同时在另一个视口中实时观察"末端输出"节点的运行表现，彻底告别频繁的缩放与拖拽。

<img src="images/视角拆分.png" width="100%" height="100%"><br>

### ⚡ 分布式混合执行引擎
-  **并行 DAG 执行** – 通过高性能任务调度器并发执行独立的分支任务，最大化提升整个工作流在多核 CPU/GPU 上的利用率。
-  **混合运行时编排 (Hybrid Runtime)** – 支持多种执行环境的无缝混合调度：
    *   **交互式 IPython 内核**: 利用本地持久化会话实现快速代码调试与内存状态保留。
    *   **远程 SSH 工作节点**: 将高算力消耗任务（如模型训练、大规模推理）透明地分发至远程服务器，并支持自动化的环境同步。
-  **选择性内存持久化 (缓存机制)** – 用户可对特定节点开启"常驻内存"功能；执行结果将直接缓存在活动进程的 RAM 中，彻底消除在反复迭代调优过程中的冗余计算与 I/O 开销。
-  **智能拓扑分发** – 系统根据节点配置自动解析依赖关系，并将任务精准路由至最佳目标执行环境（本地、远程服务器或 IPython 内核）。
-  **统一状态监控** – 在单个画布上实时可视化所有分布式节点的运行状态（排队中 / 运行中 / 成功 / 失败），全局掌控复杂任务进度。
-  **极速数据序列化** – 采用 `pyarrow` 和 `pickle` 深度优化数据传输协议，确保本地与远程环境之间的大规模数据交换保持极低延迟。

### 🧠 智能节点补全推荐 ✨
- **类型兼容推荐** - 基于输出端口 ArgumentType 自动匹配兼容的下游组件
- **多端口分组** - 按输出端口分组显示推荐项，清晰展示推荐来源
- **视觉区分** - 不同端口的推荐项使用不同颜色高亮，一目了然
- **全局统计学习** - 跨画布记录组件连接频率，越用越聪明

### 🤖 LLM-Chatter：智能编程助手
功能强大的内置编程助手，采用 OpenCode 风格的智能体架构和全面的工具系统。

#### 🧠 智能体系统
- **多智能体支持**：主智能体（Primary）处理主任务，子智能体（Subagent）并行处理子任务，隐藏智能体（Hidden）执行后台操作
- **权限系统**：基于 allow/deny/ask 的细粒度工具权限控制
- **灵活配置**：支持 Markdown（YAML frontmatter）或 YAML 文件定义智能体
- **智能体配置**：支持自定义 temperature、top_p、max_steps、model 等参数

#### 🛠️ 全面的工具集（30+ 工具）
| 类别 | 工具 |
|----------|-------|
| **文件操作** | `read`, `write`, `edit`, `multiedit`, `patch`, `grep`, `glob`, `list`, `diff_files` |
| **终端** | `bash`, `run_verify` |
| **网络** | `webfetch`, `websearch` |
| **代码分析** | `get_diagnostics` (Python/JS/TS/Shell) |
| **任务管理** | `todowrite`, `todoread`, `ask_question` |
| **技能** | `skill`, `list_skills`, `scan_repo`, `stage_files` |
| **记忆** | `memory_list`, `memory_search`, `memory_save`, `memory_consolidate` |
| **画布集成** | `list_webhooks`, `trigger_webhook` |
| **子智能体** | `task`（分发任务给 build/plan/skillful/explore 智能体） |

#### 💾 长期记忆系统
- **持久化上下文**：跨会话保存关键信息，支持置信度评分
- **冲突管理**：按组管理记忆，自动压制过时信息
- **分类组织**：任务偏好、项目约束、用户习惯等分类
- **自动提炼**：从对话中自动提取重要信息

#### 🎨 画布感知集成
- **画布工具**：运行节点、获取日志、创建节点、连接端口、设置属性、编辑属性字符串
- **上下文注入**：自动将画布图像 + 节点结构 + 全局变量作为上下文
- **黄色跳转按钮**：点击跳转到引用的画布节点
- **紫色创建按钮**：一键实例化推荐的组件
- **执行状态**：实时查询运行任务、失败节点、日志

#### ✨ 高级特性
- **对话预览**：带代码高亮的富文本消息卡片
- **上下文用量环**：可视化 Token 预算监控
- **历史管理**：搜索历史对话，自动摘要主题
- **文件撤销预览**：通过 diff 查看器预览变更
- **工具浮窗**：实时工具调用状态显示
- **子智能体管理**：协调并行任务执行

### 🔁 高级控制流支持 ✨
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

### ✅ 动态代码组件
- **自由编程**：在节点内直接编写完整 Python 组件逻辑（含 `run` 方法及辅助函数）  
- **动态端口**：通过属性表单自由增删输入/输出端口，支持为输入端口绑定**全局变量默认值**  
- **无缝集成**：复用全局变量、表达式系统、依赖自动安装、独立日志、状态可视化等全部核心能力  
- **安全执行**：代码在独立子进程运行，支持超时控制、错误捕获与重试  
- **开发友好**：专业级代码编辑器（深色主题、语法高亮、智能补全、折叠、错误提示）

### ⚡ 插件化触发系统

* **动态插件加载** – 采用解耦架构，自动识别并注册插件目录下的新触发类型（如 Cron、Webhook、文件监听），无需重启程序即可热更新。
* **自适应 UI 面板** – 节点属性栏根据所选插件动态重构输入控件，确保界面简洁且仅显示当前触发模式相关的配置项。
* **事件驱动执行** – 从手动运行转向自动化工作流，支持通过外部 HTTP 请求、定时计划或文件系统变更实时驱动画布逻辑。
* **自动化生命周期管理** – 内置安全清理逻辑，在画布关闭或节点删除时自动注销后端监听器，确保零内存泄漏与端口占用。

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

### 🛠️ 导出项目画布工具调用
- **工具调用** - 画布可直接根据项目名称调用项目执行脚本，获取运行结果
- **工具调用参数** - 画布节点属性中支持工具调用参数，工具调用时自动传入
- **工具调用日志** - 完整记录并返回详细的工具调用过程与结果日志，便于调试与追踪。
- **大模型集成** - 提供标准化的工具名称、输入/输出参数格式及调用示例，无缝支持大模型的工具调用（Function Calling）能力。

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- PyQt5 或 PySide6

### 安装

```bash
# 克隆仓库
git clone https://github.com/martin98-afk/CanvasMind.git
cd CanvasMind

# 创建虚拟环境（推荐）
python -m venv .venv

# 激活虚拟环境
# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

### 打包（可选）

```bash
python build.py
```

---

## 🧪 组件开发

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

| 类型            | 说明    | 示例                     |
|---------------|-------|------------------------|
| `TEXT`        | 文本输入  | 字符串参数                  |
| `LONGTEXT`    | 长文本输入 | 字符串参数                  |
| `INT`         | 整数输入  | 数值参数                   |
| `FLOAT`       | 浮点数输入 | 小数参数                   |
| `BOOL`        | 布尔输入  | 开关选项                   |
| `CHOICE`      | 下拉选择  | 预定义选项                  |
| `DYNAMICFORM` | 动态表单  | 不定长度数据列表信息             |
| `RANGE`       | 数值范围  | 指定范围的数值                |
| `VARIABLE`      | 变量选择  | 全局变量                   |
| `FILE SELECT`   | 文件选择  | canvas_files/model.pth |
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
- `alt+左键拖拽` - 画布平移

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

## 🗺️ 路线图

| 状态 | 功能 |
|------|------|
| 🚧 进行中 | 代码→画布自动创建（从编辑器 → 新节点） |
| 📋 计划中 | 大规模工作流可视化增强 |
| 📋 计划中 | 云端执行支持 |

---

## 🤝 贡献指南

欢迎贡献代码！请随时提交 Pull Request。

### 开发环境搭建

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/martin98-afk/CanvasMind.git
cd CanvasMind

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 开发模式运行
python main.py

# 5. 运行测试（如果有）
pytest
```

### Pull Request 流程

1. Fork 本项目
2. 创建 feature 分支 (`git checkout -b feature/AmazingFeature`)
3. 提交代码 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📖 文档

完整文档请访问：[CanvasMind 文档](https://canvasmind-sphinx-build.readthedocs.io/zh-cn/latest/)

---

## 💬 获取帮助

- 📋 [提交 Issue](https://github.com/martin98-afk/CanvasMind/issues) - 报告问题或请求新功能
- 💬 [ Discussions](https://github.com/martin98-afk/CanvasMind/discussions) - 提问和分享想法

---

## 📄 许可证

本项目采用 [GPLv3 许可证](LICENSE)。

---

## 🙏 致谢

- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) - 节点图框架
- [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - Fluent Design 组件库
- [Loguru](https://github.com/Delgan/loguru) - Python 日志库

---

## Star History

<a href="https://www.star-history.com/#martin98-afk/CanvasMind&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=martin98-afk/CanvasMind&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=martin98-afk/CanvasMind&type=date&theme=dark&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=martin98-afk/CanvasMind&type=date&legend=top-left" />
 </picture>
</a>
