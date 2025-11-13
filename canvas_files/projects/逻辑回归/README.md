# workflow
> 从 **workflow** 导出的子项目 · 2025-11-12 19:46:30
---
## 📌 项目概览
- **来源画布**: `workflow`
- **导出时间**: `2025-11-12 19:46:30`
- **节点数量**: 3
- **内部连接**: 2
- **组件数量**: 3
## 🧩 输入接口
- `param1` (`TEXT`): 超参数 `param1` of `输入array`
## 📤 输出接口
- `output` (`ARRAY`): 输出 `output` from `归一化推理(npy)`
- `value` (`ARRAY`): 输出 `value` from `逻辑回归推理(npy) 1`
## 🧱 包含组件
- `输入array`
- `归一化推理(npy)`
- `逻辑回归推理(npy)`
## ▶️ 使用方法
1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{"input_0": "hello"}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
