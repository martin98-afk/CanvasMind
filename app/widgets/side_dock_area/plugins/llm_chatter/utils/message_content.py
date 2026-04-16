# -*- coding: utf-8 -*-
import json
from typing import Any, Dict, List, Optional


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
            parts.append(
                "\n".join(
                    [
                        "<tool>",
                        f"name: {block.get('name', 'tool')}",
                        f"args: {args_json}",
                        f"result: {result}",
                        f"success: {success}",
                        "</tool>",
                    ]
                )
            )
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


def consolidate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    保持消息列表平坦，不再合并。
    每个 assistant 消息只包含自己的内容和 tool_calls。
    每个 tool 结果独立为一条 tool 消息。
    """
    return list(messages or [])


def to_api_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    将内部消息格式转换为标准API请求格式。
    用于发送给API的消息构建。
    """
    role = message.get("role")
    if role == "system":
        return {
            "role": "system",
            "content": _extract_text_content(message.get("content", "")),
        }
    elif role == "user":
        return {
            "role": "user",
            "content": _extract_text_content(message.get("content", "")),
        }
    elif role == "assistant":
        api_msg: Dict[str, Any] = {
            "role": "assistant",
        }
        text = _extract_text_content(message.get("content", ""))
        if text:
            api_msg["content"] = text
        tool_calls = message.get("tool_calls")
        if tool_calls:
            api_msg["tool_calls"] = [
                {
                    "id": str(tc.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    },
                }
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
        return api_msg
    elif role == "tool":
        return {
            "role": "tool",
            "tool_call_id": str(message.get("tool_call_id", "")),
            "name": str(message.get("name", "")),
            "content": str(message.get("content", "") or ""),
        }
    return {"role": role, "content": _extract_text_content(message.get("content", ""))}


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
