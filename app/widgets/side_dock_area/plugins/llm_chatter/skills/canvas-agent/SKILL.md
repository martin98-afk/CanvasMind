---
name: canvas-agent
description: 工作流画布编排智能体，能够根据用户需求自动选择合适的组件、创建画布、添加节点、连接节点、配置参数和执行工作流。当用户需要创建自动化工作流、编排画布组件、设计数据处理流程时使用此技能。
---

# Canvas Agent - 画布编排智能体

## 概述
Canvas Agent 是工作流画布的编排专家，能够理解用户需求并自动完成画布的设计和搭建。

## 画布位置
画布存储在 `canvas_files/workflows/` 目录下。

## 执行方式
使用 `bash` 执行Python脚本。脚本位于 skills/canvas-agent/scripts/

## 脚本调用示例

### 1. 列出组件
```bash
python skills/canvas-agent/scripts/list_components.py --search API --limit 10
```
返回: `{"total": N, "items": [{"path": "类别/名称", "cat": "类别", "desc": "描述", "in": ["输入端口"], "out": ["输出端口"]}]}`

### 2. 获取组件详情
```bash
python skills/canvas-agent/scripts/get_component.py --full-path "网络请求/API分页查询器"
```
返回: `{"path": "", "cat": "", "name": "", "desc": "", "in": [], "out": [], "props": []}`

### 3. 创建画布
```bash
python skills/canvas-agent/scripts/create_canvas.py --name "我的工作流"
```
返回: `{"name": "", "path": "", "workflow": ""}`

### 4. 添加节点 (必须保存返回的id!)
```bash
python skills/canvas-agent/scripts/add_node.py --canvas-path "canvas_files/workflows/我的工作流_xxx" --component "触发器/触发器" --node-name "开始" --x 100 --y 100
```
返回: `{"id": "0x123...", "name": "开始", "path": "", "pos": [100, 100], "ports": {"in": ["input"], "out": ["output"]}}`

### 5. 连接节点
```bash
python skills/canvas-agent/scripts/connect_nodes.py --canvas-path "xxx" --from-node "0x123..." --from-port "output" --to-node "0x456..." --to-port "input"
```

### 6. 设置属性
```bash
python skills/canvas-agent/scripts/set_property.py --canvas-path "xxx" --node-id "0x123..." --property "mode" --value "auto"
```

### 7. 设置输入
```bash
python skills/canvas-agent/scripts/set_input.py --canvas-path "xxx" --node-id "0x123..." --input-name "url" --value "https://api.example.com"
```

### 8. 获取画布
```bash
python skills/canvas-agent/scripts/get_canvas.py --canvas-path "xxx"
```

### 9. 列出画布
```bash
python skills/canvas-agent/scripts/list_canvases.py
```

## 常用内置节点
- `触发器/触发器` - 手动/Webhook/定时触发
- `控制流/条件分支` - 条件分支
- `控制流/循环迭代` - 循环处理
- `控制流/并行执行` - 并行分支
- `数据/变量节点` - 定义变量
- `代码执行/代码编辑` - Python代码

## 关键约束
1. **add_node返回的id必须保存** - 用于后续连接和配置
2. **连接前确认端口名** - 用get_component查看in/out
3. **属性/输入值支持JSON** - 如 `--value '{"key": "val"}'`
4. **canvas-path格式** - `canvas_files/workflows/画布名_时间戳`
