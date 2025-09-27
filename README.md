# 低代码可视化编程平台

![Low-Code Platform](https://img.shields.io/badge/Python-3.8%2B-blue) ![NodeGraphQt](https://img.shields.io/badge/NodeGraphQt-v0.3%2B-orange) ![qfluentwidgets](https://img.shields.io/badge/qfluentwidgets-v1.0%2B-green)

一个基于 **NodeGraphQt** 和 **qfluentwidgets** 的现代化低代码可视化编程平台，支持拖拽式组件编排、异步执行、文件操作和循环控制。

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

### 📁 文件操作支持
- **文件上传** - 支持 CSV、JSON、文件夹等多种文件类型
- **文件输出** - 输出端口可显示生成的文件路径
- **文件预览** - 拖拽组件时显示组件预览

### 📊 节点管理
- **动态组件加载** - 自动扫描 components 目录，动态加载组件
- **Pydantic 配置** - 使用 Pydantic 模型定义组件输入/输出/属性
- **独立日志系统** - 每个节点独立存储执行日志
- **状态持久化** - 支持工作流的导入/导出

## 🚀 快速开始

### 环境要求
- Python 3.8+
- PyQt5 或 PySide2

### 安装依赖
```bash
pip install -r requirements.txt
```

### requirements.txt
```txt
NodeGraphQt>=0.3.0
qfluentwidgets>=1.0.0
PyQt5>=5.15.0
loguru>=0.6.0
pandas>=1.3.0
scikit-learn>=1.0.0
```

### 运行应用
```bash
python lowcode_demo.py
```

## 📂 项目结构

```
lowcode-platform/
├── lowcode_demo.py          # 主应用程序
├── components/              # 组件定义目录
│   ├── __init__.py
│   ├── base.py             # 组件基类
│   ├── data/               # 数据处理组件
│   │   └── csv_reader.py
│   ├── algorithms/         # 算法组件
│   │   └── logistic_regression.py
│   └── control/            # 控制流组件
│       └── loop_controller.py
├── dev_codes/
│   ├── nodes/              # 节点类定义
│   ├── utils/              # 工具函数
│   └── widgets/            # 自定义控件
├── requirements.txt
└── README.md
```

## 🧪 组件开发

### 创建新组件

1. **在 `components/` 目录下创建组件文件**

```python
# components/data/my_component.py
from components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType

class MyComponent(BaseComponent):
    name = "我的组件"
    category = "数据处理"
    description = "这是一个示例组件"
    
    inputs = [
        PortDefinition(name="input_data", label="输入数据", type=ArgumentType.TEXT)
    ]
    
    outputs = [
        PortDefinition(name="output_data", label="输出数据", type=ArgumentType.CSV),
        PortDefinition(name="result", label="结果", type=ArgumentType.TEXT)
    ]
    
    properties = {
        "parameter1": PropertyDefinition(
            type=PropertyType.TEXT,
            default="default_value",
            label="参数1"
        ),
        "max_count": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="最大数量"
        )
    }

    def run(self, params, inputs=None):
        # 组件逻辑
        input_data = inputs.get("input_data") if inputs else "default"
        param1 = params.get("parameter1", "default")
        max_count = int(params.get("max_count", 10))
        
        # 处理逻辑...
        result_data = f"{input_data}_{param1}_{max_count}"
        
        return {
            "output_data": "/path/to/output.csv",  # 文件路径
            "result": result_data                  # 文本结果
        }
```

2. **自动加载** - 组件会自动被扫描并添加到组件面板

### 组件类型支持

| 类型 | 说明 | 示例 |
|------|------|------|
| `TEXT` | 文本输入 | 字符串参数 |
| `INT` | 整数输入 | 数值参数 |
| `FLOAT` | 浮点数输入 | 小数参数 |
| `BOOL` | 布尔输入 | 开关选项 |
| `CHOICE` | 下拉选择 | 预定义选项 |
| `FILE` | 文件路径 | 任意文件 |
| `FOLDER` | 文件夹路径 | 目录选择 |
| `CSV` | CSV文件 | CSV文件选择 |
| `JSON` | JSON文件 | JSON文件选择 |

## 🎮 使用指南

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

### 快捷键
- `Ctrl+R` - 运行工作流
- `Ctrl+S` - 保存工作流  
- `Ctrl+O` - 加载工作流
- `Ctrl+A` - 全选节点
- `Del` - 删除选中节点

## 🛠️ 开发说明

### 节点状态管理
- **未运行** - 灰色边框
- **运行中** - 蓝色边框  
- **执行成功** - 绿色边框
- **执行失败** - 红色边框

### 日志系统
- 每个节点独立存储日志
- 自动添加时间戳
- 支持 Loguru 日志库
- 组件内部 `print()` 输出自动捕获

### 数据流
- 输入端口自动获取上游节点输出
- 输出端口数据按端口名称存储
- 支持多输入多输出

## 📈 性能优化

- **异步执行** - 避免界面卡死
- **内存管理** - 节点删除时自动清理资源
- **高效序列化** - 工作流保存/加载优化
- **懒加载** - 组件按需加载

## 🤝 贡献指南

1. Fork 本项目
2. 创建 feature 分支 (`git checkout -b feature/AmazingFeature`)
3. 提交代码 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🙏 致谢

- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) - 节点图框架
- [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - Fluent Design 组件库
- [Loguru](https://github.com/Delgan/loguru) - Python 日志库

---

**低代码可视化编程平台** - 让编程更简单，让创造更高效！
