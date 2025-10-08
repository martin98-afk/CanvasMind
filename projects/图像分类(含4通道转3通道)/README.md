# my_subproject

> 从 **workflow** 导出的子项目 · 2025-10-08 12:15:01

---

## 📌 项目概览

- **来源画布**: `workflow`
- **导出时间**: `2025-10-08 12:15:01`
- **节点数量**: 3
- **内部连接**: 2
- **组件数量**: 3

## 🧩 输入接口

- `file`: 输入端口 `file` of `文件转图片`

## 📤 输出接口

- `predict_class`: 输出 `predict_class` from `图像分类测试`
- `confidence`: 输出 `confidence` from `图像分类测试`
- `model`: 输出 `model` from `图像分类测试`

## 🧱 包含组件

- `文件转图片`
- `图像分类测试`
- `图像4通道转3通道`

## 📂 目录结构

- `model.workflow.json`: 工作流定义文件（使用原始节点ID）
- `project_spec.json`: **项目输入/输出接口规范**
- `components/`: 组件代码
- `inputs/`: 输入文件
- `requirements.txt`: 依赖包列表
- `run.py`: 运行脚本
- `api_server.py`: 微服务脚本

## ▶️ 使用方法

1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{"input_0": "hello"}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
