# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class AgentSkillsComponent(BaseComponent):
    name = "Agent 技能执行智能体"
    category = "大模型组件/智能体SKILLS"
    description = "基于选中技能文档执行 Agent 技能，支持 LLM 主动问询 + 沙箱执行"
    requirements = "openai,orjson,PyYAML"

    inputs = [
        PortDefinition(name="input_data", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
        PortDefinition(name="selected_skills_detail", label="选中技能详情", type=ArgumentType.JSON),
        PortDefinition(name="skill_registry", label="技能注册表", type=ArgumentType.JSON, optional=True),
        PortDefinition(name="workspace_path", label="工作空间路径", type=ArgumentType.TEXT, optional=True),
    ]

    outputs = [
        PortDefinition(name="response", label="最终回复", type=ArgumentType.TEXT),
        PortDefinition(name="raw_output", label="原始响应", type=ArgumentType.JSON),
        PortDefinition(name="history", label="更新后历史", type=ArgumentType.JSON),
        PortDefinition(name="executed_commands", label="执行记录", type=ArgumentType.JSON),
        PortDefinition(name="skill_used", label="使用的技能", type=ArgumentType.TEXT),
        PortDefinition(name="execution_status", label="执行状态", type=ArgumentType.TEXT),
    ]

    properties = {
        "model": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="模型参数",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""你是一个具备技能执行能力的智能助手。

## 📚 可用技能
下方提供了技能文档（SKILL.md），请仔细阅读每个技能的：
- **description**（frontmatter 中）：何时使用这个技能
- **Trigger/When to use**：具体的触发条件
- **Commands/Usage**：如何执行（命令、参数、示例）
- **Guidelines/QA**：执行时的注意事项和质量检查

## 🔑 执行原则
1. **先判断后行动**：分析用户请求，匹配技能的触发条件
2. **信息不足时主动问询**：如果缺少关键参数，使用 <ask_user> 格式询问用户
3. **严格遵循文档**：按 SKILL.md 中的步骤执行，不要自行发明命令
4. **命令灵活性**：优先使用 SKILL.md 中提到的命令，但可根据实际情况调整（白名单非强制）
5. **安全底线**：不要执行包含 `rm -rf`、`eval`、`exec` 等危险模式的命令
6. **结果验证**：执行后检查输出，必要时按 QA 指南重试

## 📤 响应格式
在没有结束前严格按照以下结构化信息返回内容。

### 情况 A：需要执行技能
当需要使用技能时，严格按以下格式回复（仅输出代码块）：
```skill
{
  "skill_id": "技能 ID（与 selected_skills_detail 的 key  一致）",
  "command": "要执行的命令（必须来自 SKILL.md 的 Commands 部分）",
  "reason": "简要说明为什么调用这个技能"
}
```

### 情况 B：需要用户补充信息
当缺少关键信息时，使用以下格式询问用户（仅输出代码块）：
```ask_user
{
  "title": "简短标题，如'需要 API Key'",
  "message": "详细说明需要什么信息，为什么需要，如何获取",
  "fields": [
    {
      "name": "字段名（英文小写+下划线，如 api_key）",
      "label": "显示标签（如'API Key'）",
      "type": "字段类型（见下方支持列表）",
      "default": "默认值（可选）",
      "choices": ["选项1", "选项2"]  // 仅当 type=choice 时需要
    }
  ]
}
```
📋 补充信息支持的字段类型（必须严格使用以下值）

| type 值 | 说明 | 示例 |
|---------|------|------|
| `text` | 单行文本输入 | `{"name": "city", "type": "text", "default": "北京"}` |
| `bool` | 复选框（true/false） | `{"name": "use_https", "type": "bool", "default": true}` |
| `float` | 浮点数输入 | `{"name": "threshold", "type": "float", "default": 0.5}` |
| `int` | 整数输入 | `{"name": "count", "type": "int", "default": 3}` |
| `choice` | 下拉选择（必须带 choices） | `{"name": "mode", "type": "choice", "choices": ["fast", "slow"], "default": "fast"}` |

⚠️ 补充信息重要规则
1. **字段名**：只用小写字母+下划线，如 `api_key`，不要用中文或特殊字符
2. **choice 类型**：必须包含 `choices` 数组，且 `default` 必须是数组中的值
3. **bool 类型**：`default` 必须是 `true` 或 `false`（布尔值，不是字符串）
4. **number 类型**：`default` 必须是数字，不是字符串（`3` 不是 `"3"`）
5. **一次性问完**：尽量在一个问询中收集所有需要的信息，避免多次打断用户

## ⚠️ 重要
- 如果 SKILL.md 中提到需要多个步骤，请一次只执行一个命令，等待结果后再决定下一步
- 如果命令执行失败，分析错误原因，参考 SKILL.md 的 Troubleshooting 部分重试或告知用户
- 问询时尽量一次性问清楚所有需要的信息，避免多次打断用户
""",
            label="系统提示词",
        ),
        "max_command_rounds": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="最大命令执行轮数",
        ),
        "command_timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=60,
            label="单命令超时 (秒)",
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.7",
            label="温度",
            min=0.0,
            max=1.0,
            step=0.1,
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=2000,
            label="最大生成长度",
        ),
        "allowed_commands": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="",  # ✅ 空值表示不限制任何命令
            label="允许执行的命令白名单（可选）",
            description="每行一个命令前缀，留空表示不限制（仅黑名单生效）",
        ),
        "blocked_patterns": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""rm -rf
chmod 777
eval
exec
__import__
os.system
subprocess""",
            label="禁止的命令模式",
            description="每行一个正则模式",
        ),
        "intervent": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="执行前人工确认",
        ),
        "auto_retry": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="失败自动重试",
        ),
        "output_clean": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="输出清洗",
        ),
        "enable_ask_user": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用 LLM 主动问询",
            description="允许 LLM 在信息不足时弹出输入框询问用户",
        ),
    }

    def run(self, params, inputs):
        import time
        from pathlib import Path
        from datetime import datetime
        from openai import OpenAI

        self.params = params
        self.inputs = inputs
        exec_start = time.time()
        
        # === 日志：执行开始 ===
        self.logger.info(f"🚀 [START] AgentSkills 执行开始 | 时间:{datetime.now().strftime('%H:%M:%S')}")
        self.logger.info(f"📥 输入: user_input='{(inputs.input_data or '')[:50]}...', history_len={len(inputs.history or [])}")
        self.logger.info(f"📦 技能文档数:{len(inputs.selected_skills_detail or {})} | 技能列表:{list((inputs.selected_skills_detail or {}).keys())}")

        user_input = (inputs.input_data or "").strip() or "你好"
        history = self._parse_history(inputs.history)
        skill_docs = getattr(inputs, 'selected_skills_detail', {}) or {}
        skill_registry = getattr(inputs, 'skill_registry', {}) or {}
        workspace = getattr(inputs, 'workspace_path', None)

        if not skill_docs:
            self.logger.error("❌ 未提供选中技能文档，请连接 SkillRouterComponent")
            return self._error_output("未提供选中技能文档，请连接 SkillRouterComponent")

        # === 构建 Prompt ===
        prompt_start = time.time()
        skill_context = self._build_skill_context(skill_docs)
        system_prompt = params.system_prompt + "\n\n" + skill_context if skill_context else params.system_prompt
        self.logger.info(f"⏱️  [PROMPT] 构建完成 | 耗时:{time.time()-prompt_start:.3f}s | 长度:{len(system_prompt)} chars")

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # === 模型客户端 ===
        model_cfg = params.model[1] if isinstance(params.model, (list, tuple)) and len(params.model) > 1 else {}
        api_key = model_cfg.get("API_KEY", "").strip()
        api_url = model_cfg.get("API_URL", "https://api.openai.com/v1").strip().rstrip("/")
        model_name = model_cfg.get("模型名称", "gpt-4o").strip()
        self.logger.info(f"🤖 [MODEL] 配置: name={model_name} | url={api_url[:30]}... | temp={params.temperature}")

        client = OpenAI(api_key=api_key if api_key else "", base_url=api_url)

        exec_log = []
        skill_used = None
        final_reply = ""
        response_obj = None
        round_idx = 0
        ask_user_count = 0  # 记录问询次数，防止无限循环

        # === 主执行循环 ===
        while round_idx < int(params.max_command_rounds):
            round_start = time.time()
            round_idx += 1
            self.logger.info(f"🔄 [ROUND {round_idx}/{params.max_command_rounds}] 开始 | 消息数:{len(messages)}")

            # --- 调用 LLM ---
            llm_start = time.time()
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=float(params.temperature),
                    max_tokens=int(params.max_tokens),
                )
                llm_duration = time.time() - llm_start
                response_obj = response
                message = response.choices[0].message
                llm_text = message.content or ""
                print(llm_text)
                self.logger.info(f"✅ [LLM] 响应接收 | 耗时:{llm_duration:.3f}s | 内容长度:{len(llm_text)}")
            except Exception as e:
                self.logger.exception(f"❌ [LLM] 调用失败: {str(e)}")
                final_reply = f"❌ 模型调用失败：{str(e)}"
                break

            # === 优先级 1: 解析问询请求（如果启用）===
            if params.enable_ask_user and ask_user_count < 3:  # 最多问询 3 次
                ask_request = self._parse_ask_user_request(llm_text)
                if ask_request:
                    self.logger.info(f"💬 [ASK_USER] 解析到问询请求 | title={ask_request['title']}")
                    ask_user_count += 1
                    
                    # 弹出交互框获取用户输入
                    user_response = self._handle_ask_user(ask_request)
                    if user_response is None:
                        # 用户取消
                        self.logger.info(f"🚫 [ASK_USER] 用户取消问询")
                        messages.append({"role": "assistant", "content": llm_text})
                        messages.append({"role": "user", "content": "用户取消了信息补充，请尝试其他方式或告知无法完成。"})
                        continue
                    
                    # 将用户回复作为新的 user 消息
                    user_msg = f"【用户补充信息】\n" + "\n".join([f"{k}: {v}" for k, v in user_response.items()])
                    self.logger.info(f"✅ [ASK_USER] 用户回复: {user_msg[:200]}...")
                    
                    messages.append({"role": "assistant", "content": llm_text})
                    messages.append({"role": "user", "content": user_msg})
                    
                    round_duration = time.time() - round_start
                    self.logger.info(f"⏱️ [ROUND {round_idx}] 问询完成 | 耗时:{round_duration:.2f}s\n")
                    continue  # 不消耗命令轮数，继续下一轮 LLM 调用

            # === 优先级 2: 解析技能执行请求 ===
            skill_request = self._parse_skill_request(llm_text)
            if not skill_request:
                self.logger.info(f"💬 [DECISION] 无技能调用/问询，生成最终回复")
                final_reply = llm_text.strip()
                messages.append({"role": "assistant", "content": final_reply})
                break

            self.logger.info(f"🔧 [SKILL_REQ] 解析成功 | skill_id={skill_request['skill_id']} | reason={skill_request['reason'][:50]}...")

            # --- 校验技能 ---
            if skill_request["skill_id"] not in skill_docs:
                self.logger.warning(f"⚠️ [SKILL] 技能 '{skill_request['skill_id']}' 未加载，可用:{list(skill_docs.keys())}")
                feedback = f"❌ 技能 '{skill_request['skill_id']}' 未加载，可用技能：{list(skill_docs.keys())}"
                messages.append({"role": "assistant", "content": llm_text})
                messages.append({"role": "user", "content": feedback})
                continue

            # --- 白名单检查 ---
            allowed_cmds = self._get_allowed_commands()
            self.logger.debug(f"🔐 [WHITELIST] 允许的命令前缀:{allowed_cmds[:5]}{'...' if len(allowed_cmds)>5 else ''}")

            # --- 人工确认 ---
            if params.intervent:
                confirm_start = time.time()
                confirm_result = self._ask_user_confirm(skill_request, allowed_cmds)
                if confirm_result is False:
                    self.logger.info(f"🚫 [INTERVENT] 用户取消执行 | 耗时:{time.time()-confirm_start:.2f}s")
                    messages.append({"role": "user", "content": f"🚫 用户取消了技能执行：{skill_request['reason']}"})
                    continue
                elif isinstance(confirm_result, str):
                    skill_request["command"] = confirm_result
                    self.logger.info(f"✏️ [INTERVENT] 命令已修改 | 新命令:{confirm_result[:50]}...")

            # --- 获取工作目录 ---
            workdir_start = time.time()
            skill_workdir = self._get_skill_workdir(skill_request["skill_id"], skill_registry, workspace)
            self.logger.info(f"📂 [WORKDIR] 技能目录推导 | 耗时:{time.time()-workdir_start:.3f}s | path={skill_workdir}")
            if not Path(skill_workdir).exists():
                self.logger.error(f"❌ [WORKDIR] 目录不存在: {skill_workdir}")

            # --- 执行命令 ---
            cmd_start = time.time()
            self.logger.info(f"⚙️ [EXEC] 执行命令 | cmd={skill_request['command'][:80]}... | cwd={skill_workdir}")
            cmd_result = self._execute_command(
                skill_request["command"],
                skill_workdir,
                int(params.command_timeout),
                allowed_cmds
            )
            cmd_duration = time.time() - cmd_start
            exec_entry = {**skill_request, **cmd_result, "round": round_idx, "duration": cmd_duration}
            exec_log.append(exec_entry)
            skill_used = skill_request["skill_id"]

            if cmd_result["success"]:
                output_preview = (cmd_result.get("stdout") or cmd_result.get("stderr") or "")[:200]
                self.logger.info(f"✅ [EXEC] 命令成功 | 耗时:{cmd_duration:.2f}s | 输出预览:{output_preview}...")
                feedback = f"✅ 命令执行成功\n\n输出:\n```\n{(cmd_result.get('stdout') or cmd_result.get('stderr') or '')[:4000]}\n```"
            else:
                error_msg = cmd_result.get("error") or cmd_result.get("stderr") or "Unknown error"
                self.logger.error(f"❌ [EXEC] 命令失败 | 耗时:{cmd_duration:.2f}s | 错误:{error_msg}...")
                feedback = f"❌ 命令执行失败\n\n错误:\n{error_msg}"
                if params.auto_retry and round_idx < int(params.max_command_rounds):
                    feedback += "\n\n请分析错误原因，参考 SKILL.md 的 Troubleshooting 部分，修正后重试。"
                    self.logger.info(f"🔄 [RETRY] 已启用自动重试，剩余轮数:{int(params.max_command_rounds)-round_idx}")

            # --- 更新消息历史 ---
            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user", "content": feedback})
            round_duration = time.time() - round_start
            self.logger.info(f"⏱️ [ROUND {round_idx}] 完成 | 总耗时:{round_duration:.2f}s\n")

        # === 强制总结 ===
        if not final_reply:
            self.logger.warning(f"⚠️ [SUMMARY] 达到最大轮数，发起强制总结")
            summary_prompt = "已达到最大执行轮数。请根据已有的执行结果，给用户一个清晰、简洁的总结性回复。"
            messages.append({"role": "user", "content": summary_prompt})
            try:
                summary_start = time.time()
                summary_resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=int(params.max_tokens),
                )
                final_reply = summary_resp.choices[0].message.content or ""
                self.logger.info(f"✅ [SUMMARY] 生成完成 | 耗时:{time.time()-summary_start:.2f}s | 长度:{len(final_reply)}")
            except Exception as e:
                final_reply = f"⚠️ 无法生成总结：{str(e)}"
                self.logger.error(f"❌ [SUMMARY] 生成失败: {str(e)}")

        # === 输出处理 ===
        output_start = time.time()
        output_history = self._clean_history(history, [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": final_reply}
        ]) if params.output_clean else messages
        self.logger.debug(f"🧹 [HISTORY] 清洗完成 | 原始:{len(history)} → 输出:{len(output_history)} 条 | 耗时:{time.time()-output_start:.3f}s")

        total_duration = time.time() - exec_start
        status = "success" if final_reply and not any(err in final_reply[:50] for err in ["❌", "⚠️", "失败"]) else ("partial" if exec_log else "failed")

        self.logger.info(f"✅ [END] AgentSkills 执行完成 | 状态:{status} | 总耗时:{total_duration:.2f}s | 技能:{skill_used or '无'} | 调用次数:{len(exec_log)} | 问询次数:{ask_user_count}")

        return {
            "response": final_reply,
            "raw_output": response_obj.model_dump() if response_obj else {},
            "history": output_history,
            "executed_commands": exec_log,
            "skill_used": skill_used or "",
            "execution_status": status,
        }

    def _parse_ask_user_request(self, llm_response):
        """解析 LLM 返回的 ```ask_user {...}``` 问询请求"""
        import re
        import orjson
        
        patterns = [
            r'```ask_user\s*\n(\{.*?\})\n\s*```',
            r'```json\s*\n(\{.*?"title".*?"fields".*?\})\n\s*```',  # 兼容普通 json
        ]
        
        for pattern in patterns:
            match = re.search(pattern, llm_response, re.DOTALL)
            if match:
                try:
                    request = orjson.loads(match.group(1))
                    # 基础校验
                    if not request.get("title") or not request.get("message"):
                        self.logger.warning(f"⚠️ [ASK_PARSE] 问询请求缺少 title 或 message: {request}")
                        return None
                    # 确保 fields 是列表
                    if "fields" in request and not isinstance(request["fields"], list):
                        request["fields"] = []
                    self.logger.debug(f"✅ [ASK_PARSE] 解析成功: title={request['title']} | fields={len(request.get('fields', []))}")
                    return {
                        "title": str(request["title"]).strip(),
                        "message": str(request["message"]).strip(),
                        "fields": request.get("fields", []),
                    }
                except Exception as e:
                    self.logger.warning(f"⚠️ [ASK_PARSE] JSON 解析失败: {e} | 原始内容:{match.group(1)[:100]}...")
        return None

    def _handle_ask_user(self, ask_request):
        """弹出交互框获取用户输入（完全匹配您现有的 schema 格式）"""
        try:
            # 构建 schema - 完全使用您现有的格式
            schema = {}
            for field in ask_request.get("fields", []):
                field_name = field.get("name", f"field_{len(schema)}")
                field_type = field.get("type", "text").lower()
                
                # 基础配置
                field_config = {
                    "label": field.get("label", field_name),
                }
                
                # 默认值处理
                if "default" in field:
                    field_config["default"] = field["default"]
                elif "placeholder" in field:
                    field_config["default"] = field["placeholder"]
                
                # 类型映射（匹配您插件支持的类型）
                if field_type in ["text", "textarea", "string"]:
                    field_config["type"] = "text"
                elif field_type in ["bool", "boolean"]:
                    field_config["type"] = "bool"
                    # bool 默认值转换
                    if "default" in field_config and isinstance(field_config["default"], str):
                        field_config["default"] = field_config["default"].lower() in ["true", "1", "yes"]
                elif field_type in ["float", "number"]:
                    field_config["type"] = "float"
                    if "default" in field_config:
                        try:
                            field_config["default"] = float(field_config["default"])
                        except:
                            field_config["default"] = 0.0
                elif field_type in ["int", "integer"]:
                    field_config["type"] = "int"
                    if "default" in field_config:
                        try:
                            field_config["default"] = int(float(field_config["default"]))
                        except:
                            field_config["default"] = 0
                elif field_type in ["choice", "select", "enum"]:
                    # 使用您的 select + options 格式
                    field_config["type"] = "select"
                    choices = field.get("choices", field.get("options", []))
                    if choices:
                        # 转换为 [{"label": "...", "value": "..."}] 格式
                        field_config["options"] = [
                            {"label": str(c), "value": str(c)} if isinstance(c, str) else c
                            for c in choices
                        ]
                        # 确保 default 在 options 中
                        if "default" in field_config:
                            values = [opt["value"] for opt in field_config["options"]]
                            if field_config["default"] not in values:
                                field_config["default"] = field_config["options"][0]["value"]
                else:
                    field_config["type"] = "text"  # 兜底
                
                # optional 字段
                if field.get("optional", False) or field.get("required") == False:
                    field_config["optional"] = True
                
                schema[field_name] = field_config
            
            # 如果没有 fields，使用默认文本输入
            if not schema:
                schema = {
                    "reply": {
                        "label": "回复",
                        "type": "text",
                        "default": "请输入您想补充的信息..."
                    }
                }
            
            self.logger.info(f"🔐 [ASK_UI] 弹出问询框 | title={ask_request['title']} | fields:{list(schema.keys())}")
            self.logger.debug(f"🔐 [ASK_UI] schema: {schema}")
            
            confirm_resp = self.emit_interactive_message(
                method="ask_user",
                params={
                    "title": f"🔍 {ask_request['title']}",
                    "message": ask_request['message'],
                    "schema": schema  # 直接传入，格式完全匹配您的插件
                }
            )
            
            if not confirm_resp:
                self.logger.info(f"🚫 [ASK_UI] 用户取消")
                return None
            
            self.logger.info(f"✅ [ASK_UI] 用户提交: {list(confirm_resp.keys())}")
            return confirm_resp
            
        except Exception as e:
            self.logger.warning(f"⚠️ [ASK_UI] 弹窗失败: {e}")
            return None

    def _get_skill_workdir(self, skill_id, skill_registry, workspace):
        """获取技能对应的工作目录（带详细日志）"""
        from pathlib import Path
        
        self.logger.debug(f"🔍 [WORKDIR] 推导技能 '{skill_id}' 目录 | workspace={workspace}")
        
        # 方案 1：从 file_path 推导（最可靠）
        skill_info = skill_registry.get("skills", {}).get(skill_id, {})
        file_path = skill_info.get("file_path")
        if file_path:
            skill_md_path = Path(file_path)
            if skill_md_path.exists():
                skill_dir = skill_md_path.parent
                self.logger.debug(f"✅ [WORKDIR] 方案 1: 从 file_path 推导 -> {skill_dir}")
                return str(skill_dir)
            else:
                self.logger.warning(f"⚠️ [WORKDIR] file_path 不存在: {file_path}")

        # 方案 2：从 path 字段推导
        skill_path_str = skill_info.get("path", f"skills/{skill_id}")
        if workspace:
            skill_dir = Path(workspace) / skill_path_str
            if skill_dir.exists():
                self.logger.debug(f"✅ [WORKDIR] 方案 2: 从 path 推导 -> {skill_dir}")
                return str(skill_dir)
            else:
                self.logger.debug(f"⚠️ [WORKDIR] path 不存在: {skill_dir}")

        # 方案 3：默认路径 workspace/skills/skill_id
        if workspace:
            workspace_path = Path(workspace)
            if workspace_path.name == "skills":
                skill_dir = workspace_path / skill_id
            else:
                skill_dir = workspace_path / "skills" / skill_id
            if skill_dir.exists():
                self.logger.debug(f"✅ [WORKDIR] 方案 3: 标准结构 -> {skill_dir}")
                return str(skill_dir)
            else:
                self.logger.debug(f"⚠️ [WORKDIR] 标准结构不存在: {skill_dir}")

        # 方案 4：兜底 workspace/skill_id
        if workspace:
            skill_dir = Path(workspace) / skill_id
            if skill_dir.exists():
                self.logger.debug(f"✅ [WORKDIR] 方案 4: 兜底路径 -> {skill_dir}")
                return str(skill_dir)

        # 失败
        result = workspace or "."
        self.logger.error(f"❌ [WORKDIR] 所有方案失败，使用兜底: {result}")
        return result

    def _build_skill_context(self, skill_docs):
        import re
        import yaml
        import time
        
        if not skill_docs:
            return ""
        
        start = time.time()
        sections = ["\n\n## 🔧 可用技能文档（请仔细阅读）\n"]
        for skill_id, content in skill_docs.items():
            desc = "无描述"
            if content.startswith("---"):
                match = re.search(r'---\n(.*?)\n---', content, re.DOTALL)
                if match:
                    try:
                        meta = yaml.safe_load(match.group(1))
                        desc = meta.get("description", "无描述") if meta else "无描述"
                    except Exception as e:
                        self.logger.debug(f"⚠️ frontmatter 解析跳过 {skill_id}: {e}")
            sections.append(f"### 🔹 技能：{skill_id}")
            sections.append(f"> 📋 {desc}\n")
            sections.append("```markdown")
            sections.append(content[:15000])
            if len(content) > 15000:
                sections.append("\n...（文档截断，LLM 请重点关注 Trigger/Commands/QA 部分）")
            sections.append("```")
            sections.append("")
        
        duration = time.time() - start
        self.logger.debug(f"⏱️ [CONTEXT] 构建技能上下文 | 技能数:{len(skill_docs)} | 耗时:{duration:.3f}s | 总长度:{len(''.join(sections))} chars")
        return "\n".join(sections)

    def _parse_skill_request(self, llm_response):
        import re
        import orjson
        
        patterns = [
            r'```skill\s*\n(\{.*?\})\n\s*```',
            r'```json\s*\n(\{.*?\})\n\s*```',
            r'```(?:\s*\n)?(\{.*?"skill_id".*?\})\n?\s*```',
        ]
        for pattern in patterns:
            match = re.search(pattern, llm_response, re.DOTALL)
            if match:
                try:
                    request = orjson.loads(match.group(1))
                    if not request.get("skill_id") or not request.get("command"):
                        self.logger.warning(f"⚠️ [PARSE] 技能请求缺少必要字段：{request}")
                        return None
                    self.logger.debug(f"✅ [PARSE] 解析成功: skill_id={request['skill_id']} | cmd={request['command'][:50]}...")
                    return {
                        "skill_id": str(request["skill_id"]).strip(),
                        "command": str(request["command"]).strip(),
                        "reason": str(request.get("reason", "")).strip(),
                    }
                except Exception as e:
                    self.logger.warning(f"⚠️ [PARSE] JSON 解析失败: {e} | 原始内容:{match.group(1)[:100]}...")
        self.logger.debug(f"⚠️ [PARSE] 未匹配到技能请求格式")
        return None

    def _get_allowed_commands(self):
        import re
        raw = self.params.allowed_commands.strip()
        # ✅ 空值或 "*" 表示不限制
        if not raw or raw == "*":
            return []
        items = re.split(r'[,\n]', raw)
        result = [cmd.strip() for cmd in items if cmd.strip()]
        self.logger.debug(f"🔐 [WHITELIST] 解析白名单 | 结果:{result if result else '无限制'}")
        return result

    def _execute_command(self, command, workspace, timeout, allowed_cmds):
        import re
        import subprocess
        import os
        import sys
        import time
        from pathlib import Path
        from datetime import datetime

        start_time = time.time()
        result = {
            "command": command,
            "workspace": workspace,
            "start_time": datetime.now().isoformat(),
        }

        # === 1. 白名单检查（仅当 allowed_cmds 非空时生效）===
        if allowed_cmds:  # ✅ 空列表表示不限制，直接跳过
            cmd_prefix = command.split()[0] if command.split() else ""
            if not any(cmd_prefix == prefix or command.startswith(prefix + " ") or command == prefix for prefix in allowed_cmds):
                self.logger.warning(f"⚠️ [EXEC] 命令不在白名单中（但仍执行，因配置宽松）: `{cmd_prefix}`")
                # ✅ 改为警告而非拒绝，保持灵活性
                # 如果仍需严格拒绝，取消下面这行的注释：
                # return {**result, "success": False, "error": f"❌ 命令不在白名单中：`{cmd_prefix}`", "blocked_by": "allowlist", "duration": time.time() - start_time}

        # === 2. 黑名单检查（始终生效，安全底线）===
        blocked = [p.strip() for p in self.params.blocked_patterns.split("\n") if p.strip()]
        for pattern in blocked:
            if pattern and re.search(pattern, command, re.IGNORECASE):
                self.logger.error(f"❌ [EXEC] 黑名单拒绝：`{pattern}` matched in `{command[:50]}...`")
                return {
                    **result,
                    "success": False,
                    "error": f"❌ 命令包含禁止模式：`{pattern}`",
                    "blocked_by": "blocklist",
                    "duration": time.time() - start_time,
                }

        # === 3. Windows 兼容预处理 ===
        is_windows = sys.platform.startswith("win")
        exec_command = command
        temp_files = []
        
        try:
            if is_windows:
                exec_command = re.sub(r'\bpython3\b', 'python', exec_command)
                
                c_match = re.search(r'python\s+-c\s+([\'"])(.*?)(?<!\\)\1', exec_command, re.DOTALL)
                if c_match:
                    code = c_match.group(2)
                    import tempfile
                    fd, temp_path = tempfile.mkstemp(suffix='.py', dir=workspace or ".", text=True)
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(code)
                    temp_files.append(temp_path)
                    exec_command = f'python "{temp_path}"'
                    self.logger.info(f"🪟 [EXEC] -c 多行代码转换为临时文件：{temp_path}")
                
                if "<<" in exec_command and "EOF" in exec_command:
                    heredoc_match = re.search(r"<<\s*['\"]?EOF['\"]?\s*\n(.*?)\nEOF", exec_command, re.DOTALL)
                    if heredoc_match:
                        script_content = heredoc_match.group(1)
                        import tempfile
                        fd, temp_path = tempfile.mkstemp(suffix='.py', dir=workspace or ".", text=True)
                        with os.fdopen(fd, 'w', encoding='utf-8') as f:
                            f.write(script_content)
                        temp_files.append(temp_path)
                        prefix_match = re.search(r'(python\s*)', exec_command)
                        exec_command = f'python "{temp_path}"' if prefix_match else f'"{temp_path}"'
                        self.logger.info(f"🪟 [EXEC] heredoc 转换为临时文件：{temp_path}")

            # === 4. 执行命令 ===
            self.logger.info(f"⚙️ [EXEC] 执行：{exec_command[:200]}{'...' if len(exec_command)>200 else ''} | cwd={workspace}")
            
            env = os.environ.copy()
            if workspace:
                env["PYTHONPATH"] = str(Path(workspace)) + (os.pathsep + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else str(Path(workspace))
            
            proc = subprocess.run(
                exec_command,
                shell=True,
                cwd=workspace or ".",
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0,
            )
            duration = time.time() - start_time
            
            # === 5. 安全处理输出 ===
            stdout = proc.stdout if proc.stdout else ""
            stderr = proc.stderr if proc.stderr else ""
            
            if stderr and proc.returncode == 0:
                self.logger.warning(f"⚠️ [EXEC] 命令成功但有警告：{stderr[:200]}...")
            
            if len(stdout) > 10000:
                stdout = stdout[:5000] + "\n...（输出截断）...\n" + stdout[-5000:]
            if len(stderr) > 10000:
                stderr = stderr[:5000] + "\n...（输出截断）...\n" + stderr[-5000:]
            
            result.update({
                "success": proc.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": proc.returncode,
                "duration": duration,
            })
            
            # === 6. 详细错误日志 ===
            if proc.returncode != 0:
                error_detail = stderr.strip() if stderr.strip() else f"returncode={proc.returncode}"
                self.logger.error(f"❌ [EXEC] 命令失败 | code={proc.returncode} | stderr={error_detail[:300]}...")
                if "python" in stderr.lower() and ("not found" in stderr.lower() or "不是内部命令" in stderr):
                    result["error"] = "❌ 未找到 python 命令，请确保 Python 已安装并添加到 PATH"
                elif "can't open file" in stderr.lower() or "no such file" in stderr.lower():
                    result["error"] = f"❌ 文件未找到：{error_detail}"
                else:
                    result["error"] = f"❌ 执行错误：{error_detail}"
            else:
                self.logger.debug(f"✅ [EXEC] 成功 | stdout_len={len(stdout)} | stderr_len={len(stderr)}")
            
            return result
            
        except subprocess.TimeoutExpired as e:
            output = e.output.decode('utf-8', errors='replace') if e.output and isinstance(e.output, bytes) else (e.output if isinstance(e.output, str) else "")
            return {
                **result,
                "success": False,
                "error": f"⏱️ 命令执行超时 ({timeout}s)",
                "partial_output": output[:2000],
                "duration": timeout,
            }
        except UnicodeDecodeError as e:
            return {
                **result,
                "success": False,
                "error": f"🔤 输出编码错误：{str(e)}",
                "duration": time.time() - start_time,
            }
        except FileNotFoundError as e:
            cmd = exec_command.split()[0] if exec_command.split() else exec_command
            return {
                **result,
                "success": False,
                "error": f"🔍 命令未找到：`{cmd}` - 请检查是否已安装",
                "duration": time.time() - start_time,
            }
        except Exception as e:
            self.logger.exception(f"❌ [EXEC] 执行异常：{type(e).__name__}: {str(e)}")
            return {
                **result,
                "success": False,
                "error": f"💥 执行异常：{type(e).__name__}: {str(e)}",
                "duration": time.time() - start_time,
            }
        finally:
            # === 7. 清理临时文件 ===
            for temp_file in temp_files:
                if Path(temp_file).exists():
                    try:
                        Path(temp_file).unlink()
                        self.logger.debug(f"🧹 [EXEC] 清理临时文件：{temp_file}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ [EXEC] 清理临时文件失败：{e}")

    def _ask_user_confirm(self, skill_request, allowed_cmds):
        try:
            self.logger.info(f"🔐 [INTERVENT] 弹出确认框 | skill={skill_request['skill_id']} | cmd={skill_request['command'][:50]}...")
            confirm_resp = self.emit_interactive_message(
                method="ask_user",
                params={
                    "title": "🔧 确认执行技能命令",
                    "message": f"""
**技能**: {skill_request['skill_id']}
**原因**: {skill_request['reason']}
**命令**:
```bash
{skill_request['command']}
```
**允许的命令前缀**: `{', '.join(allowed_cmds[:5])}`{'...' if len(allowed_cmds) > 5 else ''}
                    """.strip(),
                    "schema": {
                        "action": {
                            "label": "操作",
                            "type": "select",
                            "options": [
                                {"label": "✅ 执行命令", "value": "execute"},
                                {"label": "❌ 取消执行", "value": "cancel"},
                                {"label": "✏️ 修改命令", "value": "edit"},
                            ],
                            "default": "execute"
                        },
                        "edited_command": {
                            "label": "修改后的命令",
                            "type": "code",
                            "language": "bash",
                            "optional": True
                        }
                    }
                }
            )
            action = confirm_resp.get("action", "cancel")
            self.logger.info(f"✅ [INTERVENT] 用户选择: {action}")
            if action == "execute":
                return True
            elif action == "edit" and confirm_resp.get("edited_command"):
                return confirm_resp["edited_command"].strip()
            else:
                return False
        except Exception as e:
            self.logger.warning(f"⚠️ [INTERVENT] 弹窗失败，默认取消: {e}")
            return False

    def _parse_history(self, history_input):
        import json
        if not history_input:
            return []
        if isinstance(history_input, str):
            try:
                result = json.loads(history_input)
                self.logger.debug(f"📜 [HISTORY] 解析字符串历史 | 条数:{len(result)}")
                return result
            except json.JSONDecodeError as e:
                self.logger.warning(f"⚠️ [HISTORY] JSON 解析失败: {e}")
                return []
        self.logger.debug(f"📜 [HISTORY] 直接使用列表历史 | 条数:{len(history_input)}")
        return history_input if isinstance(history_input, list) else []

    def _clean_history(self, original, current_turn):
        clean = []
        for msg in original:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            if role == "user":
                clean.append(msg)
            elif role == "assistant" and "tool_calls" not in msg and msg.get("content"):
                clean.append({"role": "assistant", "content": msg["content"]})
        clean.extend(current_turn)
        self.logger.debug(f"🧹 [HISTORY] 清洗: {len(original)} → {len(clean)} 条")
        return clean

    def _error_output(self, message):
        self.logger.error(f"❌ [ERROR] {message}")
        return {
            "response": f"❌ {message}",
            "raw_output": {},
            "history": [],
            "executed_commands": [],
            "skill_used": "",
            "execution_status": "failed",
        }