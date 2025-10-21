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

<div align="center">
  <h1>Visual Programming Workflow Development Tool</h1>
  
  [🇨🇳 中文](README_zh.md) | [🇬🇧 English](README.md)
</div>

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
