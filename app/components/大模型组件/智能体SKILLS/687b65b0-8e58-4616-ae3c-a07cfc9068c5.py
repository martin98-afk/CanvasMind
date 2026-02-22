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
    description = "基于选中技能文档执行 Agent 技能，LLM 自主决策 + 沙箱执行"
    requirements = "openai,orjson,PyYAML"

    inputs = [
        PortDefinition(name="input_data", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
        PortDefinition(name="selected_skills_detail", label="选中技能详情", type=ArgumentType.JSON),
        PortDefinition(name="workspace_path", label="工作空间路径", type=ArgumentType.TEXT),
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
2. **严格遵循文档**：按 SKILL.md 中的步骤执行，不要自行发明命令
3. **只执行文档中的命令**：不要执行 SKILL.md 未提及的命令
4. **结果验证**：执行后检查输出，必要时按 QA 指南重试

## 📤 响应格式
### 情况 A：需要执行技能
当需要使用技能时，严格按以下格式回复（仅输出代码块）：
```skill
{
  "skill_id": "技能 ID（与 selected_skills_detail 的 key 一致）",
  "command": "要执行的命令（必须来自 SKILL.md 的 Commands 部分）",
  "reason": "简要说明为什么调用这个技能"
}
```

### 情况 B：不需要技能
直接回复自然语言，不要包含 ```skill 代码块。

## ⚠️ 重要
- 如果 SKILL.md 中提到需要多个步骤，请一次只执行一个命令，等待结果后再决定下一步
- 如果命令执行失败，分析错误原因，参考 SKILL.md 的 Troubleshooting 部分重试或告知用户
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
            default="""python,pip,npx,markitdown,pdftoppm,soffice,curl,wget""",
            label="允许执行的命令白名单",
            description="每行一个命令前缀，仅允许执行匹配的命令",
        ),
        "blocked_patterns": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""rm -rf,chmod 777,eval,exec,__import__,os.system,subprocess""",
            label="禁止的命令模式",
            description="每行一个正则模式，匹配的命令将被拒绝执行",
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
    }

    def run(self, params, inputs):
        import time
        import json
        import orjson
        import re
        import subprocess
        import os
        from pathlib import Path
        from datetime import datetime
        from openai import OpenAI

        self.params = params
        self.inputs = inputs
        start_time = time.time()

        user_input = (inputs.input_data or "").strip() or "你好"
        history = self._parse_history(inputs.history)
        skill_docs = getattr(inputs, 'selected_skills_detail', {}) or {}
        workspace = getattr(inputs, 'workspace_path', None)

        if not skill_docs:
            return self._error_output("未提供选中技能文档，请连接 SkillRouterComponent")

        skill_context = self._build_skill_context(skill_docs)
        system_prompt = params.system_prompt + "\n\n" + skill_context if skill_context else params.system_prompt

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        model_cfg = params.model[1] if isinstance(params.model, (list, tuple)) and len(params.model) > 1 else {}
        api_key = model_cfg.get("API_KEY", "").strip()
        api_url = model_cfg.get("API_URL", "https://api.openai.com/v1").strip().rstrip("/")
        model_name = model_cfg.get("模型名称", "gpt-4o").strip()

        client = OpenAI(api_key=api_key, base_url=api_url)

        exec_log = []
        skill_used = None
        final_reply = ""
        response_obj = None

        for round_idx in range(int(params.max_command_rounds)):
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=float(params.temperature),
                    max_tokens=int(params.max_tokens),
                )
                response_obj = response
                message = response.choices[0].message
                llm_text = message.content or ""
            except Exception as e:
                self.logger.exception(f"❌ 模型调用失败：{str(e)}")
                final_reply = f"❌ 模型调用失败：{str(e)}"
                break

            skill_request = self._parse_skill_request(llm_text)

            if not skill_request:
                final_reply = llm_text.strip()
                messages.append({"role": "assistant", "content": final_reply})
                break

            if skill_request["skill_id"] not in skill_docs:
                feedback = f"❌ 技能 '{skill_request['skill_id']}' 未加载，可用技能：{list(skill_docs.keys())}"
                messages.append({"role": "assistant", "content": llm_text})
                messages.append({"role": "user", "content": feedback})
                continue

            allowed_cmds = self._get_allowed_commands()

            if params.intervent:
                confirm_result = self._ask_user_confirm(skill_request, allowed_cmds)
                if confirm_result is False:
                    messages.append({"role": "user", "content": f"🚫 用户取消了技能执行：{skill_request['reason']}"})
                    continue
                elif isinstance(confirm_result, str):
                    skill_request["command"] = confirm_result

            cmd_result = self._execute_command(
                skill_request["command"],
                workspace,
                int(params.command_timeout),
                allowed_cmds
            )
            exec_entry = {**skill_request, **cmd_result, "round": round_idx + 1}
            exec_log.append(exec_entry)
            skill_used = skill_request["skill_id"]

            if cmd_result["success"]:
                output_preview = cmd_result.get("stdout", "") or cmd_result.get("stderr", "")
                feedback = f"✅ 命令执行成功\n\n输出:\n```\n{output_preview[:4000]}\n```"
            else:
                error_msg = cmd_result.get("error", cmd_result.get("stderr", "Unknown error"))
                feedback = f"❌ 命令执行失败\n\n错误:\n{error_msg}"
                if params.auto_retry and round_idx < int(params.max_command_rounds) - 1:
                    feedback += "\n\n请分析错误原因，参考 SKILL.md 的 Troubleshooting 部分，修正后重试。"

            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user", "content": feedback})

        if not final_reply:
            summary_prompt = "已达到最大执行轮数。请根据已有的执行结果，给用户一个清晰、简洁的总结性回复。"
            messages.append({"role": "user", "content": summary_prompt})
            try:
                summary_resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=int(params.max_tokens),
                )
                final_reply = summary_resp.choices[0].message.content or ""
            except Exception as e:
                final_reply = f"⚠️ 无法生成总结：{str(e)}"

        output_history = self._clean_history(history, [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": final_reply}
        ]) if params.output_clean else messages

        total_duration = time.time() - start_time
        status = "success" if final_reply and not any(err in final_reply[:50] for err in ["❌", "⚠️", "失败"]) else ("partial" if exec_log else "failed")

        self.logger.info(f"✅ AgentSkills 执行完成 | 状态:{status} | 耗时:{total_duration:.2f}s | 技能:{skill_used or '无'}")

        return {
            "response": final_reply,
            "raw_output": response_obj.model_dump() if response_obj else {},
            "history": output_history,
            "executed_commands": exec_log,
            "skill_used": skill_used or "",
            "execution_status": status,
        }

    def _build_skill_context(self, skill_docs):
        import re
        import yaml
        if not skill_docs:
            return ""
        sections = ["\n\n## 🔧 可用技能文档（请仔细阅读）\n"]
        for skill_id, content in skill_docs.items():
            desc = "无描述"
            if content.startswith("---"):
                match = re.search(r'---\n(.*?)\n---', content, re.DOTALL)
                if match:
                    try:
                        meta = yaml.safe_load(match.group(1))
                        desc = meta.get("description", "无描述") if meta else "无描述"
                    except:
                        pass
            sections.append(f"### 🔹 技能：{skill_id}")
            sections.append(f"> 📋 {desc}\n")
            sections.append("```markdown")
            sections.append(content[:15000])
            if len(content) > 15000:
                sections.append("\n...（文档截断，LLM 请重点关注 Trigger/Commands/QA 部分）")
            sections.append("```")
            sections.append("")
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
                        self.logger.warning(f"技能请求缺少必要字段：{request}")
                        return None
                    return {
                        "skill_id": str(request["skill_id"]).strip(),
                        "command": str(request["command"]).strip(),
                        "reason": str(request.get("reason", "")).strip(),
                    }
                except Exception as e:
                    self.logger.warning(f"技能请求 JSON 解析失败：{e}")
        return None

    def _get_allowed_commands(self):
        return [cmd.strip() for cmd in self.params.allowed_commands.split("\n") if cmd.strip()]

    def _execute_command(self, command, workspace, timeout, allowed_cmds):
        import re
        import subprocess
        import os
        import time
        from datetime import datetime

        start_time = time.time()
        result = {
            "command": command,
            "workspace": workspace,
            "start_time": datetime.now().isoformat(),
        }

        if allowed_cmds:
            cmd_prefix = command.split()[0] if command.split() else ""
            if not any(cmd_prefix == prefix or command.startswith(prefix + " ") or command == prefix for prefix in allowed_cmds):
                return {
                    **result,
                    "success": False,
                    "error": f"❌ 命令不在白名单中：`{cmd_prefix}`",
                    "blocked_by": "allowlist",
                    "duration": time.time() - start_time,
                }

        blocked = [p.strip() for p in self.params.blocked_patterns.split("\n") if p.strip()]
        for pattern in blocked:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    **result,
                    "success": False,
                    "error": f"❌ 命令包含禁止模式：`{pattern}`",
                    "blocked_by": "blocklist",
                    "duration": time.time() - start_time,
                }

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workspace or ".",
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ},
            )
            result.update({
                "success": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "duration": time.time() - start_time,
            })
            for key in ["stdout", "stderr"]:
                if len(result.get(key, "")) > 10000:
                    result[key] = result[key][:5000] + "\n...（输出截断）...\n" + result[key][-5000:]
            return result
        except subprocess.TimeoutExpired:
            return {
                **result,
                "success": False,
                "error": f"⏱️ 命令执行超时 ({timeout}s)",
                "duration": timeout,
            }
        except FileNotFoundError:
            return {
                **result,
                "success": False,
                "error": f"🔍 命令未找到：{command.split()[0] if command.split() else command}",
                "duration": time.time() - start_time,
            }
        except Exception as e:
            return {
                **result,
                "success": False,
                "error": f"💥 执行异常：{type(e).__name__}: {str(e)}",
                "duration": time.time() - start_time,
            }

    def _ask_user_confirm(self, skill_request, allowed_cmds):
        try:
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
            if action == "execute":
                return True
            elif action == "edit" and confirm_resp.get("edited_command"):
                return confirm_resp["edited_command"].strip()
            else:
                return False
        except Exception as e:
            self.logger.warning(f"人工确认弹窗失败，默认取消：{e}")
            return False

    def _parse_history(self, history_input):
        import json
        if not history_input:
            return []
        if isinstance(history_input, str):
            try:
                return json.loads(history_input)
            except json.JSONDecodeError:
                return []
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
        return clean

    def _error_output(self, message):
        return {
            "response": f"❌ {message}",
            "raw_output": {},
            "history": [],
            "executed_commands": [],
            "skill_used": "",
            "execution_status": "failed",
        }