# react智能体
> 从 **react智能体** 导出的子项目 · 2025-11-13 21:50:18
---
## 📌 项目概览
- **来源画布**: `react智能体`
- **导出时间**: `2025-11-13 21:50:18`
- **节点数量**: 17
- **内部连接**: 17
- **组件数量**: 13
## 🧩 输入接口
- `input_text` (`LONGTEXT`): 超参数 `input_text` of `长文本输入`
## 📤 输出接口
- `output1` (`JSON`): 输出 `output1` from `JSON文本包装 3`
## 🧱 包含组件
- `提示词模板`
- `输入端口`
- `获取全局变量`
- `json筛选`
- `大模型输出解析`
- `大模型对话`
- `工具调用`
- `JSON文本包装`
- `条件分支`
- `循环控制流区域`
- `长文本输入`
- `移除思考过程`
- `输出端口`
## ▶️ 使用方法
1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{"input_0": "hello"}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
