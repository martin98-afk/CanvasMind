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


class SubAgentExecutor(QThread):
    """子智能体执行器 - 独立线程运行子智能体任务"""

    finished_with_result = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

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

            result = self._execute_agent_loop(messages, tools)

            if self._is_cancelled:
                return

            summary = self._summarize_result(result)
            self.finished_with_result.emit(summary)

        except Exception as e:
            self.error_occurred.emit(f"SubAgent execution error: {str(e)}")

    def _execute_agent_loop(self, messages: List[Dict], tools: List[Dict]) -> str:
        """执行子智能体对话循环"""
        iteration = 0
        max_iterations = 10
        current_messages = messages.copy()
        response_content = ""

        while iteration < max_iterations:
            if self._is_cancelled:
                return ""

            iteration += 1

            response_content, tool_calls = self._make_api_call(current_messages)

            if self._is_cancelled:
                return ""

            if not tool_calls:
                return response_content

            current_messages.append(
                {
                    "role": "assistant",
                    "content": response_content,
                    "tool_calls": tool_calls,
                }
            )

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

        return response_content

    def _make_api_call(self, messages: List[Dict]) -> tuple:
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
            if cn_key in ["API_KEY", "API_URL", "模型名称", "系统提示"]:
                continue

            if cn_key == "是否思考":
                status = (
                    "enabled"
                    if (value is True or str(value).lower() == "true")
                    else "disabled"
                )
                extra_body["enable_thinking"] = status == "enabled"
                extra_body["include_reasoning"] = status == "enabled"

            en_key = mapping.get(cn_key)
            if not en_key and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cn_key):
                en_key = cn_key
            if not en_key:
                continue
            elif en_key in ["temperature", "max_tokens", "top_p"]:
                req_kwargs[en_key] = value
            else:
                extra_body[en_key] = value

        if extra_body:
            req_kwargs["extra_body"] = extra_body

        tools_to_use = req_kwargs.pop("tools", None)

        client = OpenAI(
            api_key=api_key if api_key else "dummy",
            base_url=base_url,
            timeout=120.0,
        )

        response = client.chat.completions.create(**req_kwargs, tools=tools_to_use)

        full_response = ""
        tool_calls_found = []
        tool_calls_buffer = {}

        for chunk in response:
            if self._is_cancelled:
                return "", []

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)

            if content:
                full_response += content

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
                        try:
                            parsed_args = json.loads(buffer["function"]["arguments"])
                            tool_calls_found.append(
                                {
                                    "id": buffer["id"],
                                    "type": buffer["type"],
                                    "function": {
                                        "name": buffer["function"]["name"],
                                        "arguments": buffer["function"]["arguments"],
                                    },
                                }
                            )
                            del tool_calls_buffer[tc_id]
                        except json.JSONDecodeError:
                            pass

        return full_response, tool_calls_found

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

            result = self.tool_executor.execute(tool_name, arguments)
            result_content = str(result) if result else ""

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
        if not result or len(result) < 500:
            return result

        try:
            api_key = self.llm_config.get("API_KEY", "").strip()
            base_url = self.llm_config.get("API_URL") or None
            model = str(self.llm_config.get("模型名称", "gpt-4o"))

            prompt = f"""你是一个结果总结助手。请将以下子智能体的执行结果压缩成简洁的摘要，返回给主智能体继续任务。

## 要求
1. 保留关键信息、结论、修改的文件路径
2. 忽略调试过程和无效输出
3. 返回JSON格式: {{"summary": "摘要内容", "key_files": ["文件1", "文件2"], "status": "completed/failed"}}

## 执行结果
{result[:8000]}

请直接输出JSON，不要有其他内容："""

            client = OpenAI(
                api_key=api_key if api_key else "dummy",
                base_url=base_url,
                timeout=30.0,
            )

            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )

            raw = resp.choices[0].message.content.strip()
            json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if json_match:
                summary_data = json.loads(json_match.group())
                return json.dumps(summary_data, ensure_ascii=False)

            return result[:1000]

        except Exception as e:
            logger.warning(f"Summary failed: {e}")
            return result[:1000]


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
