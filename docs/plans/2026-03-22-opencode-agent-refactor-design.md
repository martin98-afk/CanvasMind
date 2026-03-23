# LLM Chatter Agent 重构设计文档

**日期**: 2026-03-22
**主题**: 向 OpenCode Agent 机制全面重构

---

## 1. 背景与目标

当前 `llm_chatter` 插件的 agent 系统使用 YAML 格式定义，工具控制采用简单的工具名称白名单机制。为了与 OpenCode 生态对齐并提升扩展性，本次重构将：

1. 采用 Markdown 格式定义 Agent（与 OpenCode 一致）
2. 引入 Permission 系统替代简单的工具列表
3. 区分 Primary / Subagent / Hidden 三种 Agent 模式
4. 支持 OpenCode 兼容的 Skill 格式

---

## 2. OpenCode Agent 机制对照

### 2.1 Agent 类型

| 类型 | 说明 | 调用方式 |
|------|------|----------|
| **Primary** | 主要交互智能体 | Tab 键切换 |
| **Subagent** | 专业任务智能体 | @mention 或 task 工具调用 |
| **Hidden** | 系统级智能体 | 仅程序化调用，UI 不可见 |

### 2.2 内置 Agents

| Agent | Mode | Description |
|-------|------|-------------|
| `build` | primary | 全工具权限，标准开发智能体 |
| `plan` | primary | 只读限制，禁止 edit/bash |
| `general` | subagent | 通用任务执行，可并行 |
| `explore` | subagent | 只读代码探索 |
| `compaction` | primary, hidden | 长上下文压缩 |
| `title` | primary, hidden | 会话标题生成 |
| `summary` | primary, hidden | 会话摘要生成 |

### 2.3 Permission 系统

替代原有的 tools 列表，采用 ask/allow/deny 三级控制：

```yaml
permission:
  edit: deny                    # 完全禁止编辑
  bash:
    "*": ask                    # 默认询问
    "git *": allow              # git 命令直接执行
    "rm *": deny                # rm 命令禁止
  webfetch: deny                # 禁止网页访问
```

### 2.4 Markdown Agent 格式

```markdown
---
description: Agent 描述（必填）
mode: subagent
permission:
  edit: deny
  bash: allow
temperature: 0.1
steps: 50
model: anthropic/claude-sonnet-4-20250514
hidden: false
---

You are in code review mode. Focus on:
- Code quality and best practices
- Potential bugs and edge cases
```

文件名即为 agent name，如 `review.md` 创建 `review` agent。

---

## 3. 目录结构

```
llm_chatter/
├── agents/                          # 内置 Markdown agents
│   ├── build.md                    # mode: primary
│   ├── plan.md                     # mode: primary
│   ├── general.md                  # mode: subagent
│   ├── explore.md                  # mode: subagent
│   ├── compaction.md               # mode: primary, hidden: true
│   ├── title.md                    # mode: primary, hidden: true
│   └── summary.md                  # mode: primary, hidden: true
├── skills/                         # 兼容现有 skills 格式
│   ├── canvas-agent/
│   │   └── SKILL.md
│   ├── skill-creator/
│   │   └── SKILL.md
│   └── find-skills/
│       └── SKILL.md
├── .opencode/                      # OpenCode 兼容格式
│   ├── agents/                     # 项目级 agents（可选）
│   │   └── *.md
│   └── skills/                    # 项目级 skills（可选）
│       └── */SKILL.md
├── core/
│   └── agent_manager.py           # 重构支持 Markdown 解析
└── main_widget.py                 # 适配新的 agent 机制
```

---

## 4. Agent 数据结构

```python
@dataclass
class Agent:
    name: str                          # 文件名
    description: str                   # 必填，agent 用途描述
    mode: str = "all"                  # primary / subagent / all
    permission: Dict[str, Any] = {}    # ask/allow/deny 规则
    temperature: Optional[float] = None
    steps: Optional[int] = None         # max_steps
    model: Optional[str] = None         # 模型覆盖
    hidden: bool = False                # UI 隐藏
    task_permissions: Dict[str, str] = {}  # 可调用的 subagent
    color: Optional[str] = None         # UI 颜色
    top_p: Optional[float] = None
    prompt: str = ""                   # Markdown body 作为 system prompt
```

---

## 5. Permission 解析规则

1. **全局默认**: `"*": "allow"`
2. **逐级覆盖**: agent permission 覆盖全局
3. **Glob 模式**: `*` 匹配任意字符，`?` 匹配单个字符
4. **最后匹配优先**: 规则按顺序匹配，最后一条生效

### 可配置权限的工具

| 权限名 | 说明 |
|--------|------|
| `read` | 读取文件 |
| `edit` | 文件修改（write, edit, patch, multiedit） |
| `glob` | 文件 glob 模式 |
| `grep` | 内容搜索 |
| `list` | 目录列表 |
| `bash` | Shell 命令 |
| `task` | 启动子智能体 |
| `skill` | 加载技能 |
| `webfetch` | 获取网页 |
| `websearch` | 网页搜索 |
| `todoread` | 读取 TODO |
| `todowrite` | 写入 TODO |

---

## 6. Skill 兼容性

### 6.1 现有格式（保持兼容）

```
skills/
└── canvas-agent/
    └── SKILL.md        # YAML frontmatter + markdown
```

### 6.2 OpenCode 格式（新增支持）

```
.opencode/skills/
└── git-release/
    └── SKILL.md        # name, description, license, instructions
```

### 6.3 Skill 发现路径

1. 项目级: `.opencode/skills/<name>/SKILL.md`
2. 全局级: `~/.config/opencode/skills/<name>/SKILL.md`
3. 兼容级: `skills/<name>/SKILL.md`（现有路径）

---

## 7. UI 变更

### 7.1 Agent 切换

- **Primary agents**: Tab 键或下拉框切换
- **Subagents**: @mention 在输入框触发
- **Hidden agents**: 不显示在 UI

### 7.2 Permission 提示

当 tool 执行需要 `ask` 时，弹出确认对话框：
- `once`: 仅本次允许
- `always`: 本会话内永久允许
- `reject`: 拒绝执行

---

## 8. 迁移计划

### Phase 1: 核心重构
1. 重构 `Agent` 数据结构
2. 实现 Markdown agent 解析
3. 实现 Permission 系统
4. 迁移内置 agents 到 Markdown

### Phase 2: 功能完善
1. 实现 Primary/Subagent/Hidden 区分
2. 实现 task_permissions 控制
3. 实现 hidden agents（compaction, title, summary）

### Phase 3: 生态兼容
1. 实现 OpenCode 格式 Skill 支持
2. 实现 `.opencode/` 路径兼容
3. 更新 UI 以匹配新机制

---

## 9. 风险与应对

| 风险 | 应对 |
|------|------|
| Permission 改动影响现有功能 | 保留 tools 字段做向后兼容 |
| Markdown 解析性能 | 缓存解析结果 |
| Skill 格式冲突 | 明确优先级：项目级 > 全局级 > 兼容级 |

---

## 10. 验收标准

1. ✅ 所有现有 agents 可迁移到 Markdown 格式
2. ✅ Permission 系统正确控制工具访问
3. ✅ Primary agents 可通过 Tab 切换
4. ✅ Subagents 可通过 @mention 调用
5. ✅ Hidden agents 不显示在 UI
6. ✅ 现有 skills 继续正常工作
7. ✅ OpenCode 格式 skills 可被识别加载
