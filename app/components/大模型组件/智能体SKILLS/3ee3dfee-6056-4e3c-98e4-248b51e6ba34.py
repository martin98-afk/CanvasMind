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


class CanvasDesignAgentComponent(BaseComponent):
    name = "画布设计智能体"
    category = "大模型组件/智能体SKILLS"
    description = "基于 skill.md 自动构建节点图工作流，支持组件发现、节点创建、端口连接、属性配置"
    requirements = "openai,orjson,PyYAML"

    inputs = [
        PortDefinition(name="input_data", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON),
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
            label="模型配置",
            description="选择已配置的大模型或输入 API 参数",
        ),
        "system_prompt": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""你是一个专业的画布设计助手，专门帮助用户构建节点图工作流。

## 📚 技能文档
当前目录下的 skill.md 已加载，请严格遵循其中的调用格式。

## 🔑 核心原则
1. **先查后建**: 不确定组件路径时，必须先调用 `get_all_components`
2. **精确匹配**: 组件路径必须与返回列表**逐字一致**（中文/英文/大小写敏感）
3. **UUID 必存**: `create_next_node` 返回的 UUID 必须立即保存，用于后续操作
4. **格式严格**: `interactive` 是**顶层字段**，不要在 params 内
5. **等待反馈**: 每次插件调用后，系统会返回执行结果，请根据结果决定下一步

## 📤 响应格式（严格执行）

### 调用插件时 (仅输出代码块):
```plugin_call
{
  "method": "get_all_components",
  "params": {},
  "interactive": true,
  "reason": "查询可用组件列表"
}
```

### 字段说明
- `method`: 插件方法名（如 `get_all_components`, `create_next_node`）
- `params`: **业务参数对象**，不要包含 `interactive`
- `interactive`: **布尔值，顶层字段**，true=需要 UI 交互，false=纯逻辑操作
- `reason`: (可选) 调用原因，便于调试

### 需要用户补充信息时:
```ask_user
{
  "title": "确认文件路径",
  "message": "请提供 CSV 文件的完整路径",
  "schema": {
    "file_path": {"type": "file", "label": "CSV 路径", "ext": ".csv"}
  }
}
```

### 完成时:
直接输出自然语言回复

## ⚠️ 重要提醒
- `interactive` 必须是**顶层字段**，格式：`"interactive": true`
- `params` 只包含业务参数（如 `key`, `node_path`, `source` 等）
- 使用英文双引号 `"`，禁止中文引号
- 组件路径必须来自 `get_all_components` 返回列表，**禁止猜测**
""",
            label="系统提示词",
        ),
        "max_rounds": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="最大执行轮数",
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
        "enable_ask_user": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用主动问询",
            description="允许 LLM 在信息不足时弹出输入框询问用户",
        ),
        "auto_retry": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="失败自动重试",
        ),
        "confirm_before_exec": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="执行前人工确认",
        ),
        "output_clean": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="输出历史清洗",
        ),
    }

    def run(self, params, inputs):
        import time
        import os
        from pathlib import Path
        from datetime import datetime
        from openai import OpenAI
        import orjson

        self.params = params
        self.inputs = inputs
        exec_start = time.time()

        # === 日志：执行开始 ===
        self.logger.info(f"🚀 [START] CanvasDesignAgent | {datetime.now().strftime('%H:%M:%S')}")
        self.logger.info(f"📥 输入: '{(inputs.input_data or '')[:50]}...' | history_len={len(inputs.history or [])}")

        user_input = (inputs.input_data or "").strip() or "你好"
        history = self._parse_history(inputs.history)

        # === 加载技能文档 (当前目录 skill.md) ===
        skill_doc = self._load_skill_md()
        if not skill_doc:
            self.logger.error("❌ 未找到 skill.md 文件")
            return self._error_output("技能文档 skill.md 未找到，请确保文件存在于组件运行目录")

        # === 构建 Prompt ===
        system_prompt = params.system_prompt + "\n\n## 📄 已加载技能文档\n```markdown\n" + skill_doc + "\n```"
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # === 模型客户端 ===
        model_cfg = params.model[1] if isinstance(params.model, (list, tuple)) and len(params.model) > 1 else {}
        api_key = model_cfg.get("API_KEY", "").strip()
        api_url = model_cfg.get("API_URL", "https://api.openai.com/v1").strip().rstrip("/")
        model_name = model_cfg.get("模型名称", "gpt-4o").strip()
        self.logger.info(f"🤖 [MODEL] {model_name} | {api_url[:30]}... | temp={params.temperature}")

        client = OpenAI(api_key=api_key if api_key else "", base_url=api_url)

        exec_log = []
        skill_used = "canvas_design"
        final_reply = ""
        response_obj = None
        round_idx = 0
        ask_user_count = 0
        plugin_context = {}  # 存储 UUID 等上下文

        # === 主执行循环 ===
        while round_idx < int(params.max_rounds):
            round_start = time.time()
            round_idx += 1
            self.logger.info(f"🔄 [ROUND {round_idx}/{params.max_rounds}] | msgs:{len(messages)}")

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
                llm_text = response.choices[0].message.content or ""
                self.logger.info(f"✅ [LLM] +{llm_duration:.2f}s | len:{len(llm_text)}")
            except Exception as e:
                self.logger.exception(f"❌ [LLM] Error: {e}")
                final_reply = f"❌ 模型调用失败：{str(e)}"
                break

            # === 优先级 1: 解析问询请求 ===
            if params.enable_ask_user and ask_user_count < 3:
                ask_req = self._parse_ask_user(llm_text)
                if ask_req:
                    ask_user_count += 1
                    self.logger.info(f"💬 [ASK] {ask_req['title']}")
                    user_resp = self._handle_ask_user(ask_req)
                    if user_resp is None:
                        messages.append({"role": "assistant", "content": llm_text})
                        messages.append({"role": "user", "content": "用户取消了信息补充。"})
                        continue
                    user_msg = "【用户补充】\n" + "\n".join(f"{k}: {v}" for k, v in user_resp.items())
                    messages.append({"role": "assistant", "content": llm_text})
                    messages.append({"role": "user", "content": user_msg})
                    self.logger.info(f"⏱️ [ROUND {round_idx}] Ask done | +{time.time()-round_start:.2f}s")
                    continue

            # === 优先级 2: 解析插件调用请求 ===
            plugin_req = self._parse_plugin_call(llm_text)
            if not plugin_req:
                final_reply = llm_text.strip()
                messages.append({"role": "assistant", "content": final_reply})
                self.logger.info(f"💬 [DONE] Final reply generated")
                break

            self.logger.info(f"🔧 [PLUGIN] {plugin_req['method']} | {plugin_req['reason'][:40]}...")

            # --- 人工确认 (如果启用) ---
            if params.confirm_before_exec:
                confirm = self._ask_confirm(plugin_req)
                if confirm is False:
                    messages.append({"role": "user", "content": "🚫 用户取消了本次执行。"})
                    continue
                elif isinstance(confirm, dict):
                    plugin_req["params"] = confirm

            # --- 执行插件调用 (统一 emit_message) ---
            plugin_start = time.time()
            try:
                # interactive 作为独立参数传递，不在 params 字典内
                result = self.emit_message(
                    method=plugin_req["method"],
                    params=plugin_req["params"],
                    interactive=plugin_req.get("interactive", False)
                )
                plugin_dur = time.time() - plugin_start
                self.logger.info(f"✅ [PLUGIN] +{plugin_dur:.2f}s | result:{type(result)}")
                
                # 保存上下文：create_next_node 返回 UUID
                if plugin_req["method"] == "create_next_node" and isinstance(result, str):
                    plugin_context["last_uuid"] = result
                    self.logger.info(f"💾 [CTX] Saved UUID: {result[:8]}...")
                    
            except Exception as e:
                plugin_dur = time.time() - plugin_start
                self.logger.error(f"❌ [PLUGIN] Error: {e}")
                result = {"error": str(e), "success": False}
                plugin_dur = 0

            # --- 构建反馈 ---
            exec_entry = {
                "method": plugin_req["method"],
                "params": plugin_req["params"],
                "reason": plugin_req["reason"],
                "result": result,
                "round": round_idx,
                "duration": plugin_dur,
                "success": result is not None and (not isinstance(result, dict) or not result.get("error"))
            }
            exec_log.append(exec_entry)

            if exec_entry["success"]:
                preview = str(result) or "非交互插件，无返回信息，继续下一步。"
                feedback = f"✅ 执行成功\n```\n{preview}\n```"
            else:
                err = result.get("error") if isinstance(result, dict) else str(result)
                feedback = f"❌ 执行失败\n\n错误: {err}"
                if params.auto_retry and round_idx < int(params.max_rounds):
                    feedback += "\n\n请分析错误后重试。"

            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user", "content": feedback})
            self.logger.info(f"⏱️ [ROUND {round_idx}] Done | +{time.time()-round_start:.2f}s")

        # === 强制总结 ===
        if not final_reply and exec_log:
            summary_prompt = "请根据以上执行结果，给用户一个简洁的总结。"
            messages.append({"role": "user", "content": summary_prompt})
            try:
                summary = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=int(params.max_tokens),
                )
                final_reply = summary.choices[0].message.content or ""
            except Exception as e:
                final_reply = f"⚠️ 无法生成总结: {e}"

        # === 输出处理 ===
        output_history = self._clean_history(history, [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": final_reply}
        ]) if params.output_clean else messages

        total_dur = time.time() - exec_start
        status = "success" if final_reply and "❌" not in final_reply[:20] else ("partial" if exec_log else "failed")

        self.logger.info(f"✅ [END] {status} | +{total_dur:.2f}s | calls:{len(exec_log)} | asks:{ask_user_count}")

        return {
            "response": final_reply,
            "raw_output": response_obj.model_dump() if response_obj else {},
            "history": output_history,
            "executed_commands": exec_log,
            "skill_used": skill_used,
            "execution_status": status,
        }

    def _load_skill_md(self):
        """读取当前目录下的 skill.md 文件"""
        from pathlib import Path
        try:
            # 尝试多个可能路径
            paths = [
                Path(__file__).parent / "skill.md",
                Path.cwd() / "skill.md",
                Path("skill.md"),
            ]
            for p in paths:
                if p.exists():
                    content = p.read_text(encoding="utf-8")
                    self.logger.info(f"📄 [SKILL] Loaded: {p} | {len(content)} chars")
                    return content
            self.logger.warning(f"⚠️ [SKILL] Not found in: {[str(p) for p in paths]}")
            return None
        except Exception as e:
            self.logger.error(f"❌ [SKILL] Load error: {e}")
            return None

    def _parse_plugin_call(self, llm_text):
        """解析 ```plugin_call {...}``` 格式的插件调用请求"""
        import re
        import orjson
        
        # 调试：记录原始 LLM 输出片段
        self.logger.debug(f"🔍 [PARSE_INPUT] LLM text preview: {llm_text[:500]}...")
        
        # 正则模式列表，按优先级尝试（更宽松的匹配）
        patterns = [
            # plugin_call 代码块 - \n? 表示换行可选，[\s\S]*? 匹配任意字符包括换行
            (r'```plugin_call\s*\n?([\s\S]*?)\s*```', "plugin_call block"),
            # json 代码块
            (r'```json\s*\n?([\s\S]*?)\s*```', "json block"),
            # 裸 JSON - 必须包含 method 和 params 字段
            (r'\{[^{}]*"method"[^{}]*"params"[^{}]*\}', "bare JSON"),
        ]
        
        for pattern, desc in patterns:
            match = re.search(pattern, llm_text)
            if match:
                self.logger.debug(f"✅ [PARSE] Matched {desc}")
                try:
                    # 提取 JSON 字符串
                    json_str = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else match.group(0).strip()
                    self.logger.debug(f"🔍 [PARSE] JSON preview: {json_str[:200]}...")
                    
                    # 解析 JSON (orjson 支持中文)
                    req = orjson.loads(json_str)
                    
                    # 必须有 method 字段
                    if not req.get("method"):
                        self.logger.warning(f"⚠️ [PARSE] Missing 'method' field: {req}")
                        return None
                    
                    # 确保 params 存在
                    if "params" not in req:
                        req["params"] = {}
                    
                    # 提取 interactive 作为顶层字段（默认 false）
                    # 兼容：如果 interactive 误写在 params 里，也自动提取出来
                    interactive = req.get("interactive", False)
                    if "interactive" in req.get("params", {}):
                        interactive = req["params"].pop("interactive")
                    
                    result = {
                        "method": str(req["method"]).strip(),
                        "params": req["params"],
                        "interactive": interactive,
                        "reason": str(req.get("reason", "")).strip(),
                    }
                    self.logger.info(f"✅ [PARSE] Success: method={result['method']}, interactive={result['interactive']}")
                    return result
                    
                except orjson.JSONDecodeError as e:
                    self.logger.warning(f"⚠️ [PARSE] JSON decode error: {e}")
                    self.logger.debug(f"🔍 [PARSE] Problematic JSON: {json_str[:300]}")
                except Exception as e:
                    self.logger.warning(f"⚠️ [PARSE] Error: {type(e).__name__}: {e}")
        
        self.logger.warning(f"⚠️ [PARSE] Failed to match any pattern")
        return None

    def _parse_ask_user(self, llm_text):
        """解析 ```ask_user {...}``` 格式的问询请求"""
        import re
        import orjson
        patterns = [
            r'```ask_user\s*\n(\{.*?\})\n\s*```',
            r'```json\s*\n(\{.*?"title".*?"schema".*?\})\n\s*```',
        ]
        for pat in patterns:
            match = re.search(pat, llm_text, re.DOTALL)
            if match:
                try:
                    req = orjson.loads(match.group(1))
                    if not req.get("title") or not req.get("message"):
                        return None
                    return {
                        "title": str(req["title"]).strip(),
                        "message": str(req["message"]).strip(),
                        "schema": req.get("schema", {}),
                    }
                except Exception as e:
                    self.logger.warning(f"⚠️ [ASK_PARSE] Error: {e}")
        return None

    def _handle_ask_user(self, ask_req):
        """弹出交互框获取用户输入"""
        import orjson
        try:
            schema = ask_req.get("schema") or {"reply": {"type": "text", "label": "回复", "default": ""}}
            resp = self.emit_interactive_message(
                method="ask_user",
                params={
                    "title": f"🔍 {ask_req['title']}",
                    "message": ask_req["message"],
                    "schema": schema
                }
            )
            return resp if resp else None
        except Exception as e:
            self.logger.warning(f"⚠️ [ASK_UI] Error: {e}")
            return None

    def _ask_confirm(self, plugin_req):
        """执行前人工确认弹窗"""
        import orjson
        try:
            resp = self.emit_interactive_message(
                method="ask_user",
                params={
                    "title": "🔧 确认执行",
                    "message": f"""
**技能**: {plugin_req['skill_id']}
**方法**: {plugin_req['method']}
**原因**: {plugin_req['reason']}
**参数**:
```json
{plugin_req['params']}
```
                    """.strip(),
                    "schema": {
                        "action": {
                            "type": "choice",
                            "label": "操作",
                            "choices": ["✅ 执行", "❌ 取消", "✏️ 修改参数"],
                            "default": "✅ 执行"
                        },
                        "edited_params": {
                            "type": "long_text",
                            "label": "修改后的参数 (JSON)",
                            "optional": True
                        }
                    }
                }
            )
            if resp.get("action") == "✅ 执行":
                return True
            elif resp.get("action") == "✏️ 修改参数" and resp.get("edited_params"):
                return orjson.loads(resp["edited_params"])
            return False
        except Exception as e:
            self.logger.warning(f"⚠️ [CONFIRM] Error: {e}")
            return False

    def _parse_history(self, hist_input):
        """解析历史消息"""
        import json
        if not hist_input:
            return []
        if isinstance(hist_input, str):
            try:
                return json.loads(hist_input)
            except:
                return []
        return hist_input if isinstance(hist_input, list) else []

    def _clean_history(self, original, current):
        """清洗历史记录"""
        clean = [m for m in original if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        clean.extend(current)
        return clean

    def _error_output(self, msg):
        """错误输出"""
        self.logger.error(f"❌ [ERROR] {msg}")
        return {
            "response": f"❌ {msg}",
            "raw_output": {},
            "history": [],
            "executed_commands": [],
            "skill_used": "",
            "execution_status": "failed",
        }