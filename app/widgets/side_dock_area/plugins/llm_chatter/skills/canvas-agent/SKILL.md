---
name: canvas-agent
description: 工作流画布编排智能体，能够根据用户需求自动选择合适的组件、创建画布、添加节点、连接节点、配置参数和执行工作流。当用户需要创建自动化工作流、编排画布组件、设计数据处理流程时使用此技能。
---

# Canvas Agent - 画布编排智能体

## 概述

Canvas Agent 是工作流画布的编排专家，能够理解用户需求并自动完成画布的设计和搭建。

## 画布位置

画布存储在 `canvas_files/workflows/` 目录下，每个画布是一个文件夹，包含 `.workflow.json` 文件。

## 脚本工具

每个命令对应一个独立的脚本文件：

| 脚本 | 功能 | 参数 |
|------|------|------|
| `list_components.py` | 列出组件 | `--category`, `--search`, `--limit` |
| `get_component.py` | 获取组件详情 | `--full-path` |
| `create_canvas.py` | 创建画布 | `--name`, `--description` |
| `add_node.py` | 添加节点 | `--canvas-path`, `--component`, `--node-name`, `--x`, `--y` |
| `connect_nodes.py` | 连接节点 | `--canvas-path`, `--from-node`, `--from-port`, `--to-node`, `--to-port` |
| `set_property.py` | 设置属性 | `--canvas-path`, `--node-id`, `--property`, `--value` |
| `set_input.py` | 设置输入 | `--canvas-path`, `--node-id`, `--input-name`, `--value` |
| `get_canvas.py` | 获取画布信息 | `--canvas-path` |
| `list_canvases.py` | 列出所有画布 | (无) |

## 使用示例

```bash
# 1. 查看组件
python scripts/list_components.py --search API --limit 10

# 2. 获取组件详情
python scripts/get_component.py --full-path "网络请求/API分页查询器"

# 3. 创建画布
python scripts/create_canvas.py --name "数据采集工作流" --description "自动采集"

# 4. 添加节点
python scripts/add_node.py \
  --canvas-path "canvas_files/workflows/数据采集工作流_xxx" \
  --component "网络请求/API分页查询器" \
  --node-name "获取数据" \
  --x 100 --y 100

# 5. 连接节点
python scripts/connect_nodes.py \
  --canvas-path "xxx" \
  --from-node "node1_id" \
  --from-port "all_results" \
  --to-node "node2_id" \
  --to-port "content"

# 6. 设置属性
python scripts/set_property.py --canvas-path "xxx" --node-id "node1" --property "pagination_mode" --value "page"

# 7. 设置输入
python scripts/set_input.py --canvas-path "xxx" --node-id "node1" --input-name "base_url" --value "https://api.example.com"

# 8. 获取画布状态
python scripts/get_canvas.py --canvas-path "xxx"

# 9. 列出所有画布
python scripts/list_canvases.py
```

## 工作流程

1. **理解需求** - 分析用户想要实现的功能
2. **查询组件** - 使用 `list_components.py` 或 `get_component.py`
3. **创建画布** - 使用 `create_canvas.py`
4. **添加节点** - 使用 `add_node.py`
5. **连接节点** - 使用 `connect_nodes.py`
6. **配置参数** - 使用 `set_property.py` 和 `set_input.py`

## 注意事项

1. 组件路径格式: `类别/名称`，如 `网络请求/API分页查询器`
2. 添加节点后返回 `node_id`，用于后续连接和配置
3. 连接节点前确认端口名称
4. 属性值和输入值支持 JSON 格式
