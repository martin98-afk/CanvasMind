# -*- coding: utf-8 -*-
DETAILED_README = """# {project_name_placeholder}

> 从 **{original_canvas}** 导出的子项目 · {export_time}

---

## 📌 项目概览

- **来源画布**: `{original_canvas}`
- **导出时间**: `{export_time}`

## 🧩 输入接口

{input_desc}

## 📤 输出接口

{output_desc}

## 🧱 包含组件

{component_names}

## ▶️ 使用方法
1. 安装依赖: `pip install -r requirements.txt`
2. 准备输入: 创建 `inputs.json`，如 `{{"input_0": "hello"}}`
3. 直接运行: `python run.py --input inputs.json`
4. 创建微服务: `python api_server.py --port 8888`
"""