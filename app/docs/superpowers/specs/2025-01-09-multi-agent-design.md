# 多智能体协作系统设计文档

## 1. 概述

### 1.1 目标

在大模型对话系统中实现多智能体协作功能，支持多个具有不同角色的智能体（统筹者、开发者、测试者等）在不同会话窗口中并行工作，通过消息传递机制相互协作完成任务。

### 1.2 核心特性

- **会话角色绑定**：每个会话窗口绑定一个角色身份
- **智能路由**：任务自动分配给空闲的同类型智能体
- **去中心化协作**：用户和智能体都可以发起协作
- **工作产物固化**：智能体工作成果保存到本地文件
- **回调机制**：任务完成后通过消息传递结果

## 2. 系统架构

### 2.1 核心组件

```
┌─────────────────────────────────────────────────────────────────┐
│  AgentRegistry (全局身份注册表，单例模式)                           │
│  ├── register(session_id, role_id, role_name, prompt, color)   │
│  ├── unregister(session_id)                                     │
│  ├── get_agent(role_id) → AgentInfo                            │
│  ├── get_agent_by_session(session_id) → AgentInfo              │
│  ├── list_agents() → List[AgentInfo + status]                 │
│  └── update_status(session_id, status, progress, task)        │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ 会话窗口A │        │ 会话窗口B │        │ 会话窗口C │
    │ role=     │        │ role=     │        │ role=     │
    │ coordinator│        │ developer │        │ tester   │
    └──────────┘        └──────────┘        └──────────┘
```

### 2.2 数据流

```
用户/智能体调用 send_to_agent
         │
         ▼
┌──────────────────┐
│ AgentRegistry    │
│ 查找目标 agent   │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ 写入目标会话     │
│ 消息队列         │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ 目标智能体处理   │
│ (自动/手动触发)  │
└──────────────────┘
         │
         ▼ (need_callback=true)
┌──────────────────┐
│ 回调发送结果     │
│ send_to_agent    │
└──────────────────┘
```

## 3. 核心数据结构

### 3.1 AgentInfo

```python
@dataclass
class AgentInfo:
    id: str              # 唯一标识，如 "developer_1"
    name: str            # 显示名称，如 "开发者1"
    session_id: str      # 绑定的会话ID
    prompt: str          # 角色提示词
    color: str           # 颜色，如 "#4EC9B0"
    status: str          # idle / busy / done
    progress: int        # 进度 0-100
    task: str            # 当前任务描述
    workdir: str         # 工作产物目录
    created_at: str      # 创建时间
```

### 3.2 InterAgentMessage

```python
@dataclass
class InterAgentMessage:
    id: str              # 消息ID
    from_agent: str      # 发送者ID
    from_session: str    # 发送者会话ID
    to_agent: str        # 接收者ID
    content: str          # 消息内容
    need_callback: bool  # 是否需要回调
    created_at: str       # 创建时间
    status: str           # pending / delivered / processed
```

### 3.3 WorkOutcome

```python
@dataclass
class WorkOutcome:
    id: str              # 产物ID
    agent_id: str         # 所属智能体ID
    name: str             # 产物名称
    path: str             # 文件路径
    type: str             # file / directory
    created_at: str       # 创建时间
    description: str      # 产物描述
```

## 4. 预制角色

### 4.1 角色列表

| 角色 | ID | 核心职责 |
|------|-----|---------|
| 🏛️ 统筹者 | `coordinator` | 任务分解、协调各方、进度跟踪、决策 |
| 👨‍💻 开发者 | `developer` | 代码实现、功能开发、技术方案 |
| 🎨 设计者 | `designer` | 界面设计、交互设计、视觉方案 |
| 🔍 测试者 | `tester` | 测试用例编写、Bug 发现、质量把关 |

### 4.2 预制角色配置

预制角色文件位于 `llm_chatter/agents/` 目录：

- `coordinator.md` - 统筹者提示词
- `developer.md` - 开发者提示词
- `designer.md` - 设计者提示词
- `tester.md` - 测试者提示词

用户也可以自定义角色，配置随会话存储。

## 5. 协作工具

### 5.1 send_to_agent

发送给指定身份的消息。

```json
{
  "name": "send_to_agent",
  "description": "发送消息给团队中的其他成员。发送完成后即可结束任务，无需等待对方回复（除非 need_callback=true）。",
  "parameters": {
    "type": "object",
    "properties": {
      "agent": {
        "type": "string",
        "description": "目标身份ID，从 list_agents() 获取，例如 'developer' 或 'developer_1'"
      },
      "message": {
        "type": "string",
        "description": "要发送的消息内容，应该清晰描述任务要求和期望结果"
      },
      "need_callback": {
        "type": "boolean",
        "description": "是否需要回调。true=任务完成后对方会回复你；false=对方自行决定后续行动，默认 false"
      }
    },
    "required": ["agent", "message"]
  }
}
```

**返回示例：**
```
成功发送消息给 'developer'。
消息ID: xxx
目标智能体将在空闲时处理。
```

### 5.2 broadcast_to_agents

广播消息给多个团队成员。

```json
{
  "name": "broadcast_to_agents",
  "description": "同时向多个团队成员广播消息。例如：评审时向所有人征询意见，或通知所有人任务变更。",
  "parameters": {
    "type": "object",
    "properties": {
      "agents": {
        "type": "array",
        "items": {"type": "string"},
        "description": "目标身份ID列表。null 或空数组表示发给所有成员"
      },
      "message": {
        "type": "string",
        "description": "要广播的消息内容"
      }
    },
    "required": ["message"]
  }
}
```

### 5.3 list_agents

查询团队成员及其状态。

```json
{
  "name": "list_agents",
  "description": "查询当前团队的所有成员及其工作状态。用于了解谁空闲、谁忙碌，以便智能分配任务。",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

**返回示例：**
```json
{
  "agents": [
    {
      "id": "coordinator",
      "name": "统筹者",
      "status": "idle",
      "session_id": "xxx"
    },
    {
      "id": "developer_1",
      "name": "开发者1",
      "status": "busy",
      "progress": 60,
      "task": "登录模块开发",
      "session_id": "yyy"
    },
    {
      "id": "developer_2",
      "name": "开发者2",
      "status": "idle",
      "session_id": "zzz"
    }
  ]
}
```

### 5.4 get_work_outcomes

获取指定智能体的工作产物。

```json
{
  "name": "get_work_outcomes",
  "description": "获取团队成员已完成的工作产物列表，包括文件路径和描述。用于查看其他智能体的工作成果。",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_id": {
        "type": "string",
        "description": "智能体ID，如果为空则返回所有产物"
      }
    }
  }
}
```

**返回示例：**
```json
{
  "outcomes": [
    {
      "id": "outcome_001",
      "agent_id": "coordinator",
      "agent_name": "统筹者",
      "name": "需求分析文档",
      "path": "canvas_files/agents/xxx/outcomes/01_需求分析.md",
      "type": "file",
      "description": "项目需求完整分析"
    },
    {
      "id": "outcome_002",
      "agent_id": "developer_1",
      "agent_name": "开发者1",
      "name": "登录模块",
      "path": "canvas_files/agents/yyy/outcomes/02_登录模块.py",
      "type": "file",
      "description": "用户登录功能实现"
    }
  ]
}
```

## 6. 身份列表注入格式

每次对话前，系统自动将以下内容注入到 system prompt：

```markdown
## 团队成员
以下是你当前团队的所有成员及其状态：

1. 🏛️ 统筹者
   - ID: coordinator
   - 状态: 空闲
   - 会话: xxx

2. 👨‍💻 开发者1
   - ID: developer_1
   - 状态: 忙碌 - 登录模块开发 (60%)
   - 会话: yyy

3. 👨‍💻 开发者2
   - ID: developer_2
   - 状态: 空闲
   - 会话: zzz

4. 🔍 测试者
   - ID: tester
   - 状态: 空闲
   - 会话: www

## 协作工具
你可以使用以下工具与其他成员协作：

- send_to_agent(agent, message, need_callback?)
  → 发送消息给指定成员
  → need_callback=true 时对方完成后会回复你
  → need_callback=false 时对方自行决定后续行动

- broadcast_to_agents(agents?, message)
  → 广播消息给所有或指定的成员

- list_agents()
  → 查询当前团队成员状态，优先分配任务给空闲的成员

- get_work_outcomes(agent_id?)
  → 查看其他成员的工作成果，文件路径可直接使用 read 工具查看

## 协作规则
1. 通过 send_to_agent 向其他成员派发任务
2. 任务描述中应包含工作产物文件路径，格式如：输出到 `canvas_files/agents/{session_id}/outcomes/xxx.md`
3. 完成后如果 need_callback=true，使用 send_to_agent 回复发送方
4. 通过 list_agents 查看成员状态，优先分配任务给空闲的成员
5. 协作消息在对方会话中以特殊卡片样式显示，标注来源身份
```

## 7. 消息卡片样式

### 7.1 跨身份消息卡片

跨身份消息使用特殊样式，与普通用户消息区分：

```
┌─────────────────────────────────────────────────┐
│ 🏛️ 来源: 统筹者                    [特殊边框色] │
├─────────────────────────────────────────────────┤
│                                                 │
│ 请开发登录功能，包括：                            │
│ 1. 用户名密码登录                               │
│ 2. 验证码登录                                   │
│                                                 │
│ 输出到: canvas_files/agents/yyy/outcomes/       │
│        01_登录模块.py                           │
│                                                 │
│ 完成后通知测试者进行测试                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 7.2 用户消息卡片

保持现有样式，通过**名称和颜色**区分：

```
┌─────────────────────────────────────────────────┐
│ 👨‍💻 开发者1                                     │  ← 角色名称 + 对应颜色
├─────────────────────────────────────────────────┤
│                                                 │
│ 登录模块已开发完成，                             │
│ 文件位置：canvas_files/agents/yyy/outcomes/     │
│          01_登录模块.py                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

## 8. 工作产物管理

### 8.1 目录结构

```
canvas_files/
└── agents/
    └── {session_id}/
        ├── outcomes/
        │   ├── metadata.json       # 产物清单
        │   ├── 01_需求分析.md
        │   ├── 02_架构设计.md
        │   └── 03_登录模块.py
        └── cache/                 # 临时文件
```

### 8.2 metadata.json 格式

```json
{
  "agent_id": "developer_1",
  "session_id": "yyy",
  "created_at": "2025-01-09 10:00:00",
  "outcomes": [
    {
      "id": "outcome_001",
      "name": "登录模块",
      "filename": "01_登录模块.py",
      "path": "canvas_files/agents/yyy/outcomes/01_登录模块.py",
      "type": "file",
      "created_at": "2025-01-09 11:30:00",
      "description": "用户登录功能实现，包含用户名密码和验证码登录"
    }
  ]
}
```

### 8.3 产物生成流程

1. 智能体通过工具创建文件
2. 系统自动将文件记录到 `metadata.json`
3. 发送任务时，系统自动在消息末尾附加产物路径清单

## 9. 工作状态管理

### 9.1 状态定义

| 状态 | 值 | 说明 |
|------|-----|------|
| 空闲 | `idle` | 等待新任务 |
| 忙碌 | `busy` | 正在处理任务 |
| 完成 | `done` | 任务完成 |

### 9.2 状态更新机制

**自动切换：**
- 收到新消息且开始处理 → 自动切换为 `busy`
- 当前消息处理完成 → 自动切换为 `idle`

**主动上报：**
- 智能体可在消息中包含进度信息，如 `progress: 60%`
- 系统解析并更新 `progress` 和 `task` 字段

```markdown
# 智能体可发送的进度格式示例
[进度更新] 60% - 正在实现登录验证逻辑
```

## 10. 窗口复制行为

### 10.1 复制操作

当用户复制会话窗口时：
1. 系统自动生成新 ID（如 `developer` → `developer_2`）
2. 新窗口继承原角色模板（提示词、颜色等）
3. 新窗口创建独立的工作目录

### 10.2 ID 生成规则

```
原始ID: developer
复制后: developer_2
再次复制 developer_2: developer_3
...
```

### 10.3 用户修改

用户可通过标题栏下拉框：
- 选择预设角色
- 编辑角色名称、提示词、颜色
- 解绑/重新绑定身份

## 11. 协作示例

### 11.1 单向任务传递

```
┌─────────────────────────────────────────────────────────────────┐
│ 场景：统筹者分解任务给开发者和测试者                               │
└─────────────────────────────────────────────────────────────────┘

统筹者:
  → send_to_agent("developer", "
    请实现登录模块：
    1. 用户名密码登录
    2. 验证码登录
    3. 输出到 canvas_files/agents/{dev_session}/outcomes/
  ", need_callback=true)

开发者:
  → 实现登录模块
  → 保存到 outcomes/01_登录模块.py
  → send_to_agent("coordinator", "登录模块已完成，文件位置：...", need_callback=false)
  → send_to_agent("tester", "
    登录模块已就绪，请进行测试：
    文件：canvas_files/agents/{dev_session}/outcomes/01_登录模块.py
  ", need_callback=true)

测试者:
  → 查看文件并进行测试
  → send_to_agent("developer", "发现 Bug：验证码超时未处理", ...)
  → send_to_agent("coordinator", "测试完成，发现 1 个 Bug 已反馈", ...)
```

### 11.2 并行评审

```
┌─────────────────────────────────────────────────────────────────┐
│ 场景：评审设计方案，网状通信                                     │
└─────────────────────────────────────────────────────────────────┘

统筹者:
  → broadcast_to_agents("[\"architect\", \"developer\", \"tester\"]", "
    请评审架构设计：
    文件：canvas_files/agents/{coord_session}/outcomes/架构设计.md
    请在 10 分钟内给出评审意见
  ")

架构师:
  → send_to_agent("coordinator", "架构评审通过，建议增加缓存层", ...)

开发者:
  → send_to_agent("coordinator", "技术可行，建议微服务拆分", ...)

测试者:
  → send_to_agent("coordinator", "可测试性良好，建议增加接口文档", ...)

统筹者:
  → 汇总评审意见，做出决策
```

## 12. 文件结构

```
llm_chatter/
├── core/
│   ├── agent_registry.py          # 身份注册表（单例）
│   ├── agent_role.py              # 角色配置结构
│   └── inter_agent_message.py     # 身份间消息结构
├── tools/
│   └── inter_agent_tools.py       # send_to_agent, broadcast, list_agents, get_work_outcomes
├── agents/
│   ├── coordinator.md             # 预制角色：统筹者
│   ├── developer.md              # 预制角色：开发者
│   ├── designer.md               # 预制角色：设计者
│   └── tester.md                 # 预制角色：测试者
├── widgets/
│   ├── role_selector.py           # 标题栏角色选择器
│   └── role_editor_dialog.py     # 角色编辑弹窗
├── utils/
│   └── work_outcome_manager.py    # 工作产物管理器
├── main_widget.py                 # 修改：集成角色属性
└── api/
    └── api_session_handler.py    # 修改：支持协作消息
```

## 13. 实现计划

### 阶段 1：核心基础设施
1. 实现 `AgentRegistry` 身份注册表（单例）
2. 实现 `AgentInfo` 和 `InterAgentMessage` 数据结构
3. 实现 `WorkOutcomeManager` 工作产物管理器

### 阶段 2：预制角色
4. 创建预制角色文件（coordinator.md, developer.md, designer.md, tester.md）
5. 实现角色加载和解析

### 阶段 3：协作工具
6. 实现 `send_to_agent` 工具
7. 实现 `broadcast_to_agents` 工具
8. 实现 `list_agents` 工具
9. 实现 `get_work_outcomes` 工具

### 阶段 4：UI 集成
10. 实现标题栏角色选择器
11. 实现角色编辑弹窗
12. 实现跨身份消息卡片样式
13. 修改窗口复制逻辑

### 阶段 5：消息路由
14. 实现消息队列管理
15. 实现自动/手动触发机制
16. 实现身份列表自动注入

### 阶段 6：测试与优化
17. 端到端协作流程测试
18. 并发场景测试
19. 错误处理和恢复机制

## 14. 风险与约束

### 14.1 已识别风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| 消息循环依赖 | 智能体间可能形成死循环 | 添加消息去重 + 深度限制 |
| 上下文膨胀 | 多智能体对话导致上下文爆炸 | 每个身份独立的压缩策略 |
| 状态不一致 | 并发更新导致状态不一致 | 使用线程锁保护共享状态 |

### 14.2 约束条件

1. 所有协作消息必须固化到本地，不依赖内存
2. 每个会话窗口只绑定一个身份
3. 身份 ID 在全局唯一
