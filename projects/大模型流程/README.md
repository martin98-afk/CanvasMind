# 大模型流程
    
> 从 **大模型流程** 导出的子项目 · 2025-10-10 14:39:32

---

## 📌 项目概览

- **来源画布**: `大模型流程`
- **导出时间**: `2025-10-10 14:39:32`
- **节点数量**: 7
- **内部连接**: 6
- **组件数量**: 3

## 🧩 输入接口

- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件输入`
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件输出`
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件意图`

## 📤 输出接口

- `prompt` (`TEXT`): 输出 `prompt` from `提示词模板 3`

## 🧱 包含组件

- `提示词模板`
- `长文本输入`
- `JSON文本包装`

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
