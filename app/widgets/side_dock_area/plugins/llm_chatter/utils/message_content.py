# -*- coding: utf-8 -*-
import json
import re
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
            args_json = json.dumps(
                block.get("arguments", {}) or {}, ensure_ascii=False
            )
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
            json.dumps(block.get("arguments", {}) or {}, ensure_ascii=False, sort_keys=True),
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


def repair_misordered_tool_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_blocks = ensure_content_blocks(blocks)
    if not normalized_blocks:
        return []

    text_indices = [
        i for i, block in enumerate(normalized_blocks) if block.get("type") == "text"
    ]
    tool_indices = [
        i
        for i, block in enumerate(normalized_blocks)
        if block.get("type") == "tool_result"
    ]

    if (
        len(text_indices) != 1
        or not tool_indices
        or text_indices[0] != 0
        or any(idx < text_indices[0] for idx in tool_indices)
    ):
        return normalized_blocks

    text = str(normalized_blocks[0].get("text", ""))
    if text.count("<think>") < 2:
        return normalized_blocks

    match = re.search(r"</think>\s*", text, re.IGNORECASE)
    if not match:
        return normalized_blocks

    split_pos = match.end()
    before = text[:split_pos]
    after = text[split_pos:]
    if not before.strip() or not after.strip():
        return normalized_blocks

    repaired: List[Dict[str, Any]] = [make_text_block(before)]
    repaired.extend(
        block
        for block in normalized_blocks
        if block.get("type") == "tool_result"
    )
    repaired.append(make_text_block(after))
    return repaired


def repair_grouped_tool_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_blocks = ensure_content_blocks(blocks)
    if len(normalized_blocks) < 4:
        return normalized_blocks

    if normalized_blocks[0].get("type") != "text":
        return normalized_blocks
    if normalized_blocks[-1].get("type") != "text":
        return normalized_blocks

    middle_blocks = normalized_blocks[1:-1]
    if not middle_blocks or any(
        block.get("type") != "tool_result" for block in middle_blocks
    ):
        return normalized_blocks

    trailing_text = str(normalized_blocks[-1].get("text", ""))
    think_matches = list(
        re.finditer(r"<think>[\s\S]*?</think>\s*", trailing_text, re.IGNORECASE)
    )
    if not think_matches:
        return normalized_blocks

    think_segments = [match.group(0) for match in think_matches if match.group(0).strip()]
    if not think_segments:
        return normalized_blocks

    repaired: List[Dict[str, Any]] = [normalized_blocks[0]]
    for idx, tool_block in enumerate(middle_blocks):
        repaired.append(tool_block)
        if idx < len(think_segments):
            repaired.append(make_text_block(think_segments[idx]))

    consumed_end = think_matches[-1].end()
    tail = trailing_text[consumed_end:]
    if len(think_segments) > len(middle_blocks):
        remaining = "".join(think_segments[len(middle_blocks) :])
        if remaining.strip():
            repaired.append(make_text_block(remaining))
    if tail.strip():
        repaired.append(make_text_block(tail))

    return repaired


def normalize_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(message, dict):
        return None

    role = message.get("role")
    if role not in ("system", "user", "assistant", "tool"):
        return None

    normalized: Dict[str, Any] = {"role": role}
    if message.get("timestamp"):
        normalized["timestamp"] = message.get("timestamp")

    if role == "assistant":
        tool_call_args_by_id: Dict[str, Dict[str, Any]] = {}
        for tc in message.get("tool_calls", []) or []:
            if not isinstance(tc, dict):
                continue
            tool_call_id = str(tc.get("id") or "")
            function = tc.get("function", {}) or {}
            parsed_args = normalize_tool_arguments(function.get("arguments", {}))
            if tool_call_id and parsed_args:
                tool_call_args_by_id[tool_call_id] = parsed_args

        content_blocks = ensure_content_blocks(message.get("content", []))
        normalized_blocks: List[Dict[str, Any]] = []
        seen_tool_keys = set()

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = str(block.get("text", ""))
                if text.strip():
                    normalized_blocks.append(make_text_block(text))
                continue
            if block.get("type") == "tool_result":
                tool_call_id = block.get("tool_call_id")
                tool_arguments = normalize_tool_arguments(block.get("arguments", {}))
                if not tool_arguments and tool_call_id:
                    tool_arguments = tool_call_args_by_id.get(str(tool_call_id), {})
                tool_block = make_tool_result_block(
                    tool_name=block.get("name", "tool"),
                    arguments=tool_arguments,
                    result=block.get("result", ""),
                    success=block.get("success", True),
                    tool_call_id=tool_call_id,
                )
                key = (
                    tool_block.get("tool_call_id"),
                    tool_block.get("name"),
                    json.dumps(
                        tool_block.get("arguments", {}) or {},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    tool_block.get("result", ""),
                    bool(tool_block.get("success", True)),
                )
                if key in seen_tool_keys:
                    continue
                seen_tool_keys.add(key)
                normalized_blocks.append(tool_block)

        extra_tool_blocks = [
            make_tool_result_block(
                tool_name=item.get("name", "tool"),
                arguments=(
                    normalize_tool_arguments(item.get("arguments", {}))
                    or tool_call_args_by_id.get(str(item.get("tool_call_id") or ""), {})
                ),
                result=item.get("result", item.get("content", "")),
                success=item.get("success", True),
                tool_call_id=item.get("tool_call_id"),
            )
            for item in (message.get("tool_results", []) or [])
            if isinstance(item, dict)
        ]
        for tool_block in extra_tool_blocks:
            key = (
                tool_block.get("tool_call_id"),
                tool_block.get("name"),
                json.dumps(
                    tool_block.get("arguments", {}) or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                tool_block.get("result", ""),
                bool(tool_block.get("success", True)),
            )
            if key in seen_tool_keys:
                continue
            seen_tool_keys.add(key)
            normalized_blocks.append(tool_block)

        normalized["content"] = repair_grouped_tool_blocks(
            repair_misordered_tool_blocks(normalized_blocks)
        )

        if message.get("tool_calls"):
            normalized["tool_calls"] = [
                dict(tc) for tc in message.get("tool_calls", []) if isinstance(tc, dict)
            ]
        tool_blocks = extract_tool_result_blocks(normalized["content"])
        if tool_blocks:
            normalized["tool_results"] = [
                {
                    "tool_call_id": block.get("tool_call_id"),
                    "name": block.get("name", "tool"),
                    "arguments": block.get("arguments", {}),
                    "result": block.get("result", ""),
                    "content": block.get("result", ""),
                    "success": bool(block.get("success", True)),
                }
                for block in tool_blocks
            ]
        if message.get("round_id"):
            normalized["round_id"] = message.get("round_id")
        return normalized

    if role == "tool":
        tool_call_id = message.get("tool_call_id")
        if not tool_call_id:
            return None
        normalized["tool_call_id"] = tool_call_id
        if message.get("name"):
            normalized["name"] = message.get("name")
        normalized["arguments"] = message.get("arguments", {})
        normalized["content"] = str(
            message.get("result", message.get("content", "")) or ""
        )
        normalized["result"] = normalized["content"]
        normalized["success"] = bool(message.get("success", True))
        if message.get("round_id"):
            normalized["round_id"] = message.get("round_id")
        return normalized

    normalized["content"] = str(message.get("content", "") or "")
    if role == "user":
        normalized["params"] = message.get("params", {}) or {}
    return normalized


def consolidate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    consolidated: List[Dict[str, Any]] = []
    current_assistant: Optional[Dict[str, Any]] = None

    def flush_assistant():
        nonlocal current_assistant
        if not current_assistant:
            return
        normalized = normalize_message(current_assistant)
        if normalized:
            consolidated.append(normalized)
        current_assistant = None

    for raw_msg in messages or []:
        msg = normalize_message(raw_msg)
        if not msg:
            continue

        role = msg.get("role")
        if role in ("system", "user"):
            flush_assistant()
            consolidated.append(msg)
            continue

        if role == "assistant":
            if current_assistant is None:
                current_assistant = {
                    "role": "assistant",
                    "content": [],
                    "tool_calls": [],
                    "tool_results": [],
                }
                if msg.get("timestamp"):
                    current_assistant["timestamp"] = msg.get("timestamp")
                if msg.get("round_id"):
                    current_assistant["round_id"] = msg.get("round_id")

            current_assistant["content"] = ensure_content_blocks(
                current_assistant.get("content", [])
            ) + ensure_content_blocks(msg.get("content", []))

            if msg.get("tool_calls"):
                existing = current_assistant.setdefault("tool_calls", [])
                existing.extend(
                    dict(tc) for tc in msg.get("tool_calls", []) if isinstance(tc, dict)
                )

            if msg.get("tool_results"):
                existing_results = current_assistant.setdefault("tool_results", [])
                existing_results.extend(
                    dict(item)
                    for item in msg.get("tool_results", [])
                    if isinstance(item, dict)
                )
            continue

        if role == "tool":
            if current_assistant is None:
                current_assistant = {
                    "role": "assistant",
                    "content": [],
                    "tool_calls": [],
                    "tool_results": [],
                }
            tool_block = make_tool_result_block(
                tool_name=msg.get("name", "tool"),
                arguments=msg.get("arguments", {}),
                result=msg.get("result", msg.get("content", "")),
                success=msg.get("success", True),
                tool_call_id=msg.get("tool_call_id"),
            )
            current_assistant["content"] = ensure_content_blocks(
                current_assistant.get("content", [])
            ) + [tool_block]
            current_assistant.setdefault("tool_results", []).append(
                {
                    "tool_call_id": tool_block.get("tool_call_id"),
                    "name": tool_block.get("name", "tool"),
                    "arguments": tool_block.get("arguments", {}),
                    "result": tool_block.get("result", ""),
                    "content": tool_block.get("result", ""),
                    "success": bool(tool_block.get("success", True)),
                }
            )

    flush_assistant()
    return consolidated
