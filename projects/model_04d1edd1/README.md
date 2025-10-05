# 导出的模型项目

    ## 目录结构
    - `model.workflow.json`: 工作流定义文件（使用原始节点ID）
    - `project_spec.json`: **项目输入/输出接口规范**
    - `components/`: 组件代码
    - `inputs/`: 输入文件
    - `requirements.txt`: 依赖包列表
    - `run.py`: 运行脚本

    ## 使用方法
    1. 安装依赖: `pip install -r requirements.txt`
    2. 准备输入: 创建 `inputs.json`，如 `{"input_0": "hello"}`
    3. 运行: `python run.py --input inputs.json`
    