<p align="center">
  <img width="50%" align="center" src="images/logo2.png" alt="logo">
</p>
 
<h1 align="center">
  低代码可视化编程平台
</h1>

<div align="center">

![Low-Code Platform](https://img.shields.io/badge/Python-3.8%2B-blue    )
![NodeGraphQt](https://img.shields.io/badge/NodeGraphQt-v0.3%2B-orange    )
![qfluentwidgets](https://img.shields.io/badge/qfluentwidgets-v1.0%2B-green    )

</div>


一个基于 **NodeGraphQt** 和 **qfluentwidgets** 的现代化低代码可视化编程平台，支持拖拽式组件编排、异步执行、文件操作、循环控制，并可将工作流一键导出为独立可运行项目，实现从开发到部署的无缝衔接。

---

## 📷 组件开发示意图

<img src="images/组件开发示意图.gif" width="800">

---

## 📷 工作流管理界面示意图

<img src="images/工作流管理示意图.gif" width="800">

---

## 🎉 工作流示意图

<img src="images/工作流示意图.gif" width="800">

<img src="images/工作流示意图2.gif" width="800">

## 📦 模型运行效果

<img src="images/模型运行效果.gif" width="800">

## 复杂组件控件示意图

<img src="images/复杂组件控件示意图.png" width="800">

## 循环控制流逻辑示意图

<img src="images/循环控制示意图.png" width="800">

## 循环节点运行效果

<img src="images/循环节点执行示意图.gif" width="800">

---

## 📦 子图导出示意图

<img src="images/项目导出示意图.gif" width="800">  

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
- **循环支持** - 通过循环控制器节点实现循环逻辑

### 📊 节点管理
- **动态组件加载** - 自动扫描 components 目录，动态加载组件
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

### 1. **增加“调试模式”**

- **单步执行**：点击“下一步”执行一个节点
- **断点**：在节点上右键 → “设为断点”
- **变量监视面板**：实时查看 `{{node.output}}` 值

这能极大提升复杂工作流的调试效率。


### 2. **支持远程执行**

- 将工作流提交到 **远程服务器 / Kubernetes / Ray**
- 本地只做编排，执行在集群
- 适合大模型、大数据场景

### 3. **变量系统 & 表达式引擎**
- 现状：只能通过端口传递数据
- 目标：
  - 支持 全局变量（如 {{global.input}}）
  - 支持 表达式（如 {{node1.output * 2}}）
  - 在属性面板中支持 表达式输入模式（类似 Dify 的 {{}}）

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
- [ ] 逻辑控制预制组件
  - [x] 逻辑判断
  - [ ] 当如果就
  - [ ] 循环
  - [ ] 迭代
- [ ] 组件调试
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
- [ ] 输出节点变量下载
- [x] 组件分组
- [x] 组件预览
  - [x] 节点拖拽预览
- [x] 模型管理
  - [x] 模型画布预览图
- [x] 模型运行
  - [x] 运行环境切换
  - [x] 三种运行模式
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

- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt    ) - 节点图框架
- [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets    ) - Fluent Design 组件库
- [Loguru](https://github.com/Delgan/loguru    ) - Python 日志库
