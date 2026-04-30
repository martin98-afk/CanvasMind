# -*- coding: utf-8 -*-
"""
子智能体执行器 - 独立运行子智能体任务，避免共享超长上下文
"""

import json
import re
import time
from typing import Dict, List, Optional, Any, Callable
from loguru import logger

from PyQt5.QtCore import QThread, pyqtSignal, QCoreApplication
from openai import OpenAI

from app.llm_chatter.core.provider_profile import (
    get_provider_profile,
)


class SubAgentExecutor(QThread):
    """子智能体执行器 - 独立线程运行子智能体任务"""

    finished_with_result = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)
    tool_call_started = pyqtSignal(str, dict)
    tool_result_received = pyqtSignal(str, str, bool)

    def __init__(
        self,
        agent_name: str,
        task_description: str,
        llm_config: Dict,
        agent_manager: Any,
        tool_executor: Any = None,
        parent_context: str = "",
    ):
        super().__init__()
        self.agent_name = agent_name
        self.task_description = task_description
        self.llm_config = llm_config
        self.agent_manager = agent_manager
        self.tool_executor = tool_executor
        self.parent_context = parent_context
        self._is_cancelled = False
        self._pending_answer = None
        self._last_result = None
        self._execution_error = None

    def cancel(self):
        self._is_cancelled = True

    def provide_answer(self, answer: str):
        self._pending_answer = answer

    def run(self):
        try:
            agent = self.agent_manager.get_agent(self.agent_name)
            if not agent:
                self.error_occurred.emit(f"Agent not found: {self.agent_name}")
                return

            system_prompt = self.agent_manager.get_agent_system_prompt(self.agent_name)
            tools = self.agent_manager.get_agent_tools_schema(self.agent_name)

            messages = [{"role": "system", "content": system_prompt}]

            if self.parent_context:
                messages.append(
                    {
                        "role": "user",
                        "content": f"## 父任务上下文\n{self.parent_context}\n\n## 子任务\n{self.task_description}",
                    }
                )
            else:
                messages.append({"role": "user", "content": self.task_description})

            self.progress_updated.emit(f"开始执行子任务: {self.agent_name}")

            try:
                result = self._execute_agent_loop(messages, tools)
            except Exception as e:
                logger.error(f"[SubAgentExecutor] _execute_agent_loop error: {e}")
                result = f"执行出错: {str(e)}"

            if self._is_cancelled:
                return

            try:
                summary = self._summarize_result(result)
                self._last_result = summary
            except Exception as e:
                logger.error(f"[SubAgentExecutor] _summarize_result error: {e}")
                summary = result if result else "执行出错"
                self._last_result = summary

            self.finished_with_result.emit(summary)

        except Exception as e:
            logger.error(f"[SubAgentExecutor] run() error: {e}")
            self._execution_error = str(e)
            self.error_occurred.emit(f"SubAgent execution error: {str(e)}")

    def _execute_agent_loop(self, messages: List[Dict], tools: List[Dict]) -> str:
        """执行子智能体对话循环"""
        current_messages = messages.copy()
        response_content = ""
        current_reasoning = ""  # DeepSeek V4 thinking mode

        while not self._is_cancelled:
            if self._is_cancelled:
                return ""

            response_content, tool_calls, reasoning_content = self._make_api_call(
                current_messages, tools
            )
            current_reasoning = reasoning_content

            if self._is_cancelled:
                return ""

            if not tool_calls:
                return self._filter_thinking_content(response_content)

            # DeepSeek V4 thinking mode: 需要传递 reasoning_content
            assistant_msg = {
                "role": "assistant",
                "content": response_content,
                "tool_calls": tool_calls,
            }
            if current_reasoning:
                assistant_msg["reasoning_content"] = current_reasoning
            current_messages.append(assistant_msg)

            tool_results = self._execute_tools(tool_calls)

            if tool_results is None:
                while self._pending_answer is None and not self._is_cancelled:
                    time.sleep(0.1)

                if self._is_cancelled:
                    return ""

                current_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": self._question_pending["tool_call_id"],
                        "content": self._pending_answer,
                    }
                )
                self._pending_answer = None
                continue

            current_messages.extend(tool_results)
            QCoreApplication.processEvents()
            time.sleep(0.2)

        return self._filter_thinking_content(response_content)

    def _filter_thinking_content(self, content: str) -> str:
        """过滤掉思考内容，只保留纯回复"""
        if not content:
            return content
        pattern = r"<think>[\s\S]*?</think>"
        return re.sub(pattern, "", content)

    def _parse_tool_arguments_json(self, raw_arguments: Any):
        if isinstance(raw_arguments, dict):
            return raw_arguments, ""

        text = str(raw_arguments or "")
        if not text.strip():
            return {}, ""

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, str(exc)

        if not isinstance(parsed, dict):
            return None, f"expected JSON object, got {type(parsed).__name__}"

        return parsed, ""

    def _make_api_call(self, messages: List[Dict], tools: List[Dict] = None) -> tuple:
        """调用 LLM API"""
        api_key = self.llm_config.get("API_KEY", "").strip()
        base_url = self.llm_config.get("API_URL") or None
        model = str(self.llm_config.get("模型名称", "gpt-4o"))

        req_kwargs = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        extra_body = {}
        mapping = {
            "温度": "temperature",
            "最大Token": "max_tokens",
            "核采样": "top_p",
        }

        for cn_key, value in self.llm_config.items():
            if cn_key in ["API_KEY", "API_URL", "模型名称", "系统提示", "启用技能"]:
                continue

            en_key = mapping.get(cn_key)
            if not en_key and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cn_key):
                en_key = cn_key
            if not en_key:
                continue
            elif en_key in ["temperature", "max_tokens", "top_p"]:
                req_kwargs[en_key] = value
            else:
                extra_body[en_key] = value

        if "max_tokens" in req_kwargs:
            req_kwargs["max_tokens"] = self._cap_max_output_tokens(
                model, req_kwargs["max_tokens"]
            )

        if extra_body:
            req_kwargs["extra_body"] = extra_body

        client = OpenAI(
            api_key=api_key if api_key else "dummy",
            base_url=base_url,
            timeout=120.0,
        )

        from ..utils.retry_helper import create_api_call_with_retry

        def create_completion():
            return client.chat.completions.create(**req_kwargs, tools=tools)

        response = create_api_call_with_retry(client, create_completion)

        full_response = ""
        reasoning_content = ""  # DeepSeek V4 thinking mode
        tool_calls_found = []
        tool_calls_buffer = {}

        for chunk in response:
            if self._is_cancelled:
                return "", []

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                content = self._filter_thinking_content(content)
                full_response += content

            # DeepSeek V4 thinking mode: 收集 reasoning_content
            reasoning_delta = getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                reasoning_content += reasoning_delta

            tool_calls = getattr(delta, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    tc_id = tc.id
                    if tc_id is None:
                        if tool_calls_buffer:
                            tc_id = list(tool_calls_buffer.keys())[-1]
                        else:
                            continue

                    if tc_id not in tool_calls_buffer:
                        tool_calls_buffer[tc_id] = {
                            "id": tc_id,
                            "type": getattr(tc, "type", "function"),
                            "function": {"name": "", "arguments": ""},
                        }

                    buffer = tool_calls_buffer[tc_id]
                    if tc.function and tc.function.name:
                        buffer["function"]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        buffer["function"]["arguments"] += tc.function.arguments

                    if buffer["function"]["name"] and buffer["function"]["arguments"]:
                        parsed_args, _ = self._parse_tool_arguments_json(
                            buffer["function"]["arguments"]
                        )
                        if parsed_args is not None:
                            tool_calls_found.append(
                                {
                                    "id": buffer["id"],
                                    "type": buffer["type"],
                                    "function": {
                                        "name": buffer["function"]["name"],
                                        "arguments": json.dumps(
                                            parsed_args, ensure_ascii=False
                                        ),
                                    },
                                }
                            )
                            del tool_calls_buffer[tc_id]

        for tc_id, buffer in list(tool_calls_buffer.items()):
            if not (buffer["function"]["name"] and buffer["function"]["arguments"]):
                continue
            parsed_args, error = self._parse_tool_arguments_json(
                buffer["function"]["arguments"]
            )
            if parsed_args is None:
                logger.warning(
                    f"[SubAgentExecutor] Dropping invalid tool arguments for "
                    f"tool_call {tc_id} ({buffer['function']['name']}): {error}"
                )
                continue
            tool_calls_found.append(
                {
                    "id": buffer["id"],
                    "type": buffer["type"],
                    "function": {
                        "name": buffer["function"]["name"],
                        "arguments": json.dumps(parsed_args, ensure_ascii=False),
                    },
                }
            )

        return full_response, tool_calls_found, reasoning_content

    def _cap_max_output_tokens(self, model: str, requested: int) -> int:
        try:
            requested_int = int(requested)
        except Exception:
            return requested
        profile = get_provider_profile(self.llm_config)
        cap = int(profile.get("max_output_tokens", requested_int))
        if profile.get("family") == "openai":
            model_name = (model or "").lower()
            if "o1" in model_name or "o3" in model_name:
                cap = max(cap, min(requested_int, 32768))
        return min(requested_int, cap)

    def _execute_tools(self, tool_calls: List[Dict]) -> Optional[List[Dict]]:
        """执行工具调用"""
        if not tool_calls or not self.tool_executor:
            return []

        results = []
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            arguments = tc["function"]["arguments"]

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except:
                    arguments = {}

            tool_call_id = tc["id"]

            if tool_name == "question":
                question_text = arguments.get("question", "")
                options = arguments.get("options", [])
                multiple = arguments.get("multiple", False)
                self._question_pending = {
                    "tool_call_id": tool_call_id,
                    "question": question_text,
                    "options": options,
                    "multiple": multiple,
                }
                return None

            self.tool_call_started.emit(tool_name, arguments)
            QCoreApplication.processEvents()

            result = self.tool_executor.execute(tool_name, arguments)
            result_content = str(result) if result else ""
            success = getattr(result, "success", True) if result else False

            self.tool_result_received.emit(tool_name, result_content, success)
            QCoreApplication.processEvents()

            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                }
            )

        return results

    def _summarize_result(self, result: str) -> str:
        """总结子智能体执行结果"""
        if not result:
            return "无执行结果"

        if len(result) < 2000:
            return result

        try:
            api_key = self.llm_config.get("API_KEY", "").strip()
            base_url = self.llm_config.get("API_URL") or None
            model = str(self.llm_config.get("模型名称", "gpt-4o"))

            prompt = f"""你是一个结果整理助手。请将以下子智能体的执行结果整理成结构化但详细的内容，返回给主智能体继续任务。

## 要求
1. 完整保留关键信息、结论、发现的内容
2. 保留重要的文件路径、代码片段、数据详情
3. 保持信息的完整性和实用性，不要过度压缩
4. 使用清晰的格式组织内容，便于主智能体理解和使用

## 执行结果
{result[:15000]}

请直接输出整理后的内容，格式示例：

## 任务完成情况
[总结任务完成情况]

## 关键发现
- 发现1: 具体内容
- 发现2: 具体内容
- ...

## 重要细节
- 文件: xxx
- 关键代码: xxx
- 数据: xxx

## 建议
[如果有必要，可以给出后续建议]

直接输出内容，不要输出JSON格式："""

            client = OpenAI(
                api_key=api_key if api_key else "dummy",
                base_url=base_url,
                timeout=60.0,
            )

            from ..utils.retry_helper import create_api_call_with_retry

            def create_summary():
                return client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=4000,
                )

            resp = create_api_call_with_retry(client, create_summary)

            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"Summary failed: {e}")
            return result[:3000]


class SubAgentManager:
    """子智能体管理器 - 管理子智能体任务分发"""

    def __init__(self, agent_manager, tool_executor, get_llm_config: Callable):
        self._agent_manager = agent_manager
        self._tool_executor = tool_executor
        self._get_llm_config = get_llm_config
        self._running_tasks: Dict[str, SubAgentExecutor] = {}

    def execute_task(
        self,
        task_id: str,
        agent_name: str,
        task_description: str,
        parent_context: str = "",
        on_finished: Callable[[str], None] = None,
        on_error: Callable[[str], None] = None,
        on_progress: Callable[[str], None] = None,
        executor_ref: Dict = None,
    ) -> bool:
        """执行子智能体任务"""
        try:
            llm_config = self._get_llm_config()
            if not llm_config:
                if on_error:
                    on_error("No LLM config available")
                return False

            executor = SubAgentExecutor(
                agent_name=agent_name,
                task_description=task_description,
                llm_config=llm_config,
                agent_manager=self._agent_manager,
                tool_executor=self._tool_executor,
                parent_context=parent_context,
            )

            if executor_ref is not None:
                executor_ref["executor"] = executor

            if on_finished:
                executor.finished_with_result.connect(on_finished)
            if on_error:
                executor.error_occurred.connect(on_error)
            if on_progress:
                executor.progress_updated.connect(on_progress)

            self._running_tasks[task_id] = executor
            executor.start()

            logger.info(
                f"[SubAgentManager] Started task {task_id} with agent {agent_name}"
            )
            return True

        except Exception as e:
            logger.error(f"[SubAgentManager] Failed to execute task: {e}")
            if on_error:
                on_error(str(e))
            return False

    def cancel_task(self, task_id: str) -> bool:
        """取消子智能体任务"""
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]
            return True
        return False

    def get_running_tasks(self) -> List[str]:
        """获取正在运行的任务ID列表"""
        return list(self._running_tasks.keys())
