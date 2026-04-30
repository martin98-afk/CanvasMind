# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, List, Optional


VALID_MESSAGE_ROLES = {"system", "user", "assistant", "tool"}


def normalize_tool_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return dict(arguments)
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}
    return {}


def make_text_block(text: Any) -> Dict[str, Any]:
    return {
        "type": "text",
        "text": str(text or ""),
    }


def make_tool_result_block(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    result: Any = None,
    success: bool = True,
    tool_call_id: Optional[str] = None,
) -> Dict[str, Any]:
    block = {
        "type": "tool_result",
        "name": str(tool_name or "tool"),
        "arguments": normalize_tool_arguments(arguments),
        "result": "" if result is None else str(result),
        "success": bool(success),
    }
    if tool_call_id:
        block["tool_call_id"] = str(tool_call_id)
    return block


def ensure_content_blocks(content: Any) -> List[Dict[str, Any]]:
    if content is None:
        return []

    if isinstance(content, list):
        blocks: List[Dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text":
                    text = str(item.get("text", ""))
                    if text:
                        blocks.append({"type": "text", "text": text})
                elif item_type == "tool_result":
                    blocks.append(
                        make_tool_result_block(
                            tool_name=item.get("name", "tool"),
                            arguments=item.get("arguments", {}),
                            result=item.get("result", ""),
                            success=item.get("success", True),
                            tool_call_id=item.get("tool_call_id"),
                        )
                    )
                else:
                    text = str(item.get("text", ""))
                    if text:
                        blocks.append({"type": "text", "text": text})
            elif item is not None:
                text = str(item)
                if text:
                    blocks.append({"type": "text", "text": text})
        return blocks

    text = str(content or "")
    return [make_text_block(text)] if text else []


def build_assistant_content(
    text: Any = "",
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    text_value = str(text or "")
    if text_value:
        blocks.append(make_text_block(text_value))

    for item in tool_results or []:
        if not isinstance(item, dict):
            continue
        blocks.append(
            make_tool_result_block(
                tool_name=item.get("name", "tool"),
                arguments=item.get("arguments", {}),
                result=item.get("result", item.get("content", "")),
                success=item.get("success", True),
                tool_call_id=item.get("tool_call_id"),
            )
        )

    return blocks


def append_text_block(content: Any, text: Any) -> List[Dict[str, Any]]:
    blocks = ensure_content_blocks(content)
    text_value = str(text or "")
    if not text_value:
        return blocks

    if blocks and blocks[-1].get("type") == "text":
        blocks[-1]["text"] = str(blocks[-1].get("text", "")) + text_value
    else:
        blocks.append(make_text_block(text_value))
    return blocks


def append_tool_result_block(
    content: Any,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    result: Any = None,
    success: bool = True,
    tool_call_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    blocks = ensure_content_blocks(content)
    blocks.append(
        make_tool_result_block(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            tool_call_id=tool_call_id,
        )
    )
    return blocks


def content_to_text(content: Any, include_tool_results: bool = False) -> str:
    if isinstance(content, str):
        return content

    texts: List[str] = []
    for block in ensure_content_blocks(content):
        block_type = block.get("type")
        if block_type == "text":
            text = str(block.get("text", ""))
            if text:
                texts.append(text)
        elif include_tool_results and block_type == "tool_result":
            name = str(block.get("name", "tool"))
            result = str(block.get("result", ""))
            snippet = result[:500]
            texts.append(f"[tool:{name}] {snippet}")
    return "\n\n".join(part for part in texts if part).strip()


def content_to_markdown(content: Any) -> str:
    if isinstance(content, str):
        return content

    parts: List[str] = []
    for block in ensure_content_blocks(content):
        block_type = block.get("type")
        if block_type == "text":
            text = str(block.get("text", ""))
            if text:
                parts.append(text)
        elif block_type == "tool_result":
            args_json = json.dumps(block.get("arguments", {}) or {}, ensure_ascii=False)
            result = str(block.get("result", ""))
            success = bool(block.get("success", True))
            tool_call_id = block.get("tool_call_id", "")
            tool_lines = [
                "<tool>",
                f"name: {block.get('name', 'tool')}",
                f"args: {args_json}",
                f"result: {result}",
                f"success: {success}",
            ]
            # 保留 tool_call_id 用于差异对比功能
            if tool_call_id:
                tool_lines.append(f"tool_call_id: {tool_call_id}")
            tool_lines.append("</tool>")
            parts.append("\n".join(tool_lines))
    return "\n\n".join(part for part in parts if part).strip()


def extract_tool_result_blocks(content: Any) -> List[Dict[str, Any]]:
    return [
        dict(block)
        for block in ensure_content_blocks(content)
        if block.get("type") == "tool_result"
    ]


def dedupe_tool_result_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for block in blocks or []:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        key = (
            block.get("tool_call_id"),
            block.get("name"),
            json.dumps(
                block.get("arguments", {}) or {}, ensure_ascii=False, sort_keys=True
            ),
            block.get("result", ""),
            bool(block.get("success", True)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            make_tool_result_block(
                tool_name=block.get("name", "tool"),
                arguments=block.get("arguments", {}),
                result=block.get("result", ""),
                success=block.get("success", True),
                tool_call_id=block.get("tool_call_id"),
            )
        )
    return deduped


def normalize_tool_call(tool_call: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(tool_call, dict):
        return None

    function = tool_call.get("function", {}) or {}
    function_name = str(function.get("name", "") or "").strip()
    function_arguments = function.get("arguments", "{}")
    if isinstance(function_arguments, dict):
        function_arguments = json.dumps(function_arguments, ensure_ascii=False)
    else:
        function_arguments = str(function_arguments or "{}")

    try:
        parsed_arguments = json.loads(function_arguments)
    except Exception:
        return None

    if not isinstance(parsed_arguments, dict):
        return None

    normalized = {
        "id": str(tool_call.get("id", "") or ""),
        "type": str(tool_call.get("type", "function") or "function"),
        "function": {
            "name": function_name,
            "arguments": json.dumps(parsed_arguments, ensure_ascii=False),
        },
    }
    if not normalized["id"] or not function_name:
        return None
    return normalized


def normalize_message(message: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(message, dict):
        return None

    role = str(message.get("role", "") or "").strip()
    if role not in VALID_MESSAGE_ROLES:
        return None

    normalized: Dict[str, Any] = {"role": role}

    if message.get("timestamp"):
        normalized["timestamp"] = str(message.get("timestamp"))

    if role == "assistant":
        content = content_to_text(message.get("content", ""))
        if content:
            normalized["content"] = content
        tool_calls = [
            item
            for item in (
                normalize_tool_call(tool_call)
                for tool_call in (message.get("tool_calls") or [])
            )
            if item
        ]
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        # DeepSeek V4 thinking mode: 保留 reasoning_content
        reasoning = message.get("reasoning_content")
        if reasoning:
            normalized["reasoning_content"] = str(reasoning)
        if message.get("round_id"):
            normalized["round_id"] = str(message.get("round_id"))
        if not normalized.get("content") and not normalized.get("tool_calls") and not normalized.get("reasoning_content"):
            return None
        return normalized

    if role == "tool":
        tool_call_id = str(message.get("tool_call_id", "") or "").strip()
        if not tool_call_id:
            return None
        normalized["tool_call_id"] = tool_call_id
        normalized["content"] = content_to_text(message.get("content", ""))
        normalized["name"] = str(message.get("name", "tool") or "tool")
        normalized["arguments"] = normalize_tool_arguments(message.get("arguments", {}))
        normalized["success"] = bool(message.get("success", True))
        if message.get("round_id"):
            normalized["round_id"] = str(message.get("round_id"))
        return normalized

    normalized["content"] = content_to_text(message.get("content", ""))
    if role == "user":
        params = message.get("params")
        normalized["params"] = dict(params) if isinstance(params, dict) else {}
    return normalized


def consolidate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    保持消息列表平坦，不再合并。
    每个 assistant 消息只包含自己的内容和 tool_calls。
    每个 tool 结果独立为一条 tool 消息。
    """
    normalized: List[Dict[str, Any]] = []
    for message in messages or []:
        item = normalize_message(message)
        if item:
            normalized.append(item)
    return normalized


def get_user_round_ranges(messages: List[Dict[str, Any]]) -> List[tuple[int, int]]:
    canonical_messages = consolidate_messages(messages or [])
    user_indices = [
        idx for idx, msg in enumerate(canonical_messages) if msg.get("role") == "user"
    ]
    ranges: List[tuple[int, int]] = []
    for pos, start_idx in enumerate(user_indices):
        end_idx = (
            user_indices[pos + 1] if pos + 1 < len(user_indices) else len(canonical_messages)
        )
        ranges.append((start_idx, end_idx))
    return ranges


def group_messages_for_display(
    messages: List[Dict[str, Any]],
) -> List[List[Dict[str, Any]]]:
    canonical_messages = consolidate_messages(messages or [])
    batches: List[List[Dict[str, Any]]] = []
    current_batch: List[Dict[str, Any]] = []

    for msg in canonical_messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role == "user":
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([msg])
            continue
        current_batch.append(msg)

    if current_batch:
        batches.append(current_batch)
    return batches


def to_api_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    将内部消息格式转换为标准API请求格式。
    用于发送给API的消息构建。
    """
    normalized_message = normalize_message(message)
    if not normalized_message:
        return {}

    role = normalized_message.get("role")
    if role == "system":
        return {
            "role": "system",
            "content": _extract_text_content(normalized_message.get("content", "")),
        }
    elif role == "user":
        api_msg = {
            "role": "user",
            "content": _extract_text_content(normalized_message.get("content", "")),
        }
        params = normalized_message.get("params", {})
        if params:
            context_parts = [
                str(value[1])
                for value in params.values()
                if isinstance(value, (list, tuple)) and len(value) > 1
            ]
            combined = "\n\n".join(part for part in context_parts if part)
            if combined:
                api_msg["content"] = (
                    combined + "\n\n" + api_msg["content"]
                    if api_msg["content"]
                    else combined
                )
        return api_msg
    elif role == "assistant":
        api_msg: Dict[str, Any] = {
            "role": "assistant",
        }
        text = _extract_text_content(normalized_message.get("content", ""))
        if text:
            api_msg["content"] = text
        tool_calls = normalized_message.get("tool_calls")
        if tool_calls:
            api_msg["tool_calls"] = tool_calls
        # DeepSeek V4 thinking mode: 传递 reasoning_content
        reasoning = normalized_message.get("reasoning_content")
        if reasoning:
            api_msg["reasoning_content"] = reasoning
        return api_msg
    elif role == "tool":
        return {
            "role": "tool",
            "tool_call_id": str(normalized_message.get("tool_call_id", "")),
            "name": str(normalized_message.get("name", "")),
            "content": str(normalized_message.get("content", "") or ""),
        }
    return {
        "role": role,
        "content": _extract_text_content(normalized_message.get("content", "")),
    }


def messages_to_api(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    api_messages: List[Dict[str, Any]] = []
    for message in consolidate_messages(messages or []):
        api_message = to_api_message(message)
        if api_message:
            if api_message.get("role") == "user" and not api_message.get("content"):
                continue
            api_messages.append(api_message)
    return api_messages


def _extract_text_content(content: Any) -> str:
    """从复杂内容中提取纯文本"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    txt = str(block.get("text", ""))
                    if txt:
                        parts.append(txt)
        return " ".join(parts)
    return str(content)
