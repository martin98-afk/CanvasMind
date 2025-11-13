# 自动组件生成
> 从 **自动组件生成** 导出的子项目 · 2025-11-12 20:59:38
---
## 📌 项目概览
- **来源画布**: `自动组件生成`
- **导出时间**: `2025-11-12 20:59:38`
- **节点数量**: 12
- **内部连接**: 11
- **组件数量**: 6
## 🧩 输入接口
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件输入`
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件输出`
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件参数`
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `组件意图`
## 📤 输出接口
- `parsed_json` (`JSON`): 输出 `parsed_json` from `大模型输出解析`
## 🧱 包含组件
- `移除思考过程`
- `长文本输入`
- `JSON文本包装`
- `大模型输出解析`
- `提示词模板`
- `大模型对话`
## ▶️ 使用方法
1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{"input_0": "hello"}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
