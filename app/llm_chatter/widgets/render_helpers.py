# -*- coding: utf-8 -*-
"""
UI 渲染辅助函数
"""

import hashlib
import json
from html import escape


def format_tool_block(
    tool_name: str,
    tool_args: dict,
    result: str = None,
    success: bool = True,
) -> str:
    """格式化工具块为纯文本标记，用于存储"""
    args_json = json.dumps(tool_args, ensure_ascii=False)
    result_str = str(result) if result else ""

    return (
        f"<tool>\nname: {tool_name}\nargs: {args_json}\n"
        f"result: {result_str}\nsuccess: {success}\n</tool>"
    )


def render_tool_block(
    tool_name: str,
    tool_args: dict,
    result: str = None,
    success: bool = None,
    collapsed: bool = False,
    tool_call_id: str = None,
) -> str:
    """渲染工具块，参数预览单行显示，结果区域可折叠"""
    max_args_display = 80

    args_preview = json.dumps(tool_args, ensure_ascii=False)
    if len(args_preview) > max_args_display:
        args_preview = args_preview[:max_args_display] + "..."

    status_html = ""
    if success is not None:
        status_color = "#4CAF50" if success else "#F44336"
        status_text = "✓" if success else "✗"
        status_html = (
            f'<span style="color: {status_color}; font-weight: bold; '
            f'margin-left: 6px;">{status_text}</span>'
        )

    is_sub_agent_task = tool_name == "task"
    icon = "🤖" if is_sub_agent_task else "🔧"
    title_color = "#9C27B0" if is_sub_agent_task else "#FFA500"

    if is_sub_agent_task:
        agent_name = tool_args.get("agent", "unknown")
        task_desc = tool_args.get("description", "")[:50]
        if len(tool_args.get("description", "")) > 50:
            task_desc += "..."
        args_preview = f"[{agent_name}] {task_desc}"

    def strip_code_blocks(text: str) -> str:
        import re

        text = re.sub(r"```[\w]*\n", "", text)
        text = re.sub(r"```", "", text)
        return text

    file_edit_tools = {"write", "edit", "multiedit", "patch"}
    is_file_edit = tool_name in file_edit_tools and tool_args.get("path")

    diff_icon_html = ""
    if is_file_edit and tool_call_id:
        diff_icon_html = f'''
        <span class="tool-diff-icon-btn" data-tool-call-id="{escape(tool_call_id)}"
            role="button" tabindex="0"
            style="display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; background: transparent; cursor: pointer; padding: 4px; margin-left: 8px; border-radius: 4px;"
            onclick="event.stopPropagation(); window._requestToolDiff(this.dataset.toolCallId)"
            onkeydown="if(event.key === 'Enter' || event.key === ' '){{ event.preventDefault(); event.stopPropagation(); window._requestToolDiff(this.dataset.toolCallId); }}"
            title="查看文件差异">
            <img src="qrc:/icons/差异对比.svg" style="width: 16px; height: 16px;" />
        </span>'''

    if result is not None:
        result_str = str(result)
        result_stripped = strip_code_blocks(result_str[:500])
        result_escaped = escape(result_stripped)
        result_html = f"""
        <div style="padding: 8px 12px; border-top: 1px solid #3d3d3d; font-size: 12px;">
            <div style="color: #888; margin-bottom: 4px;">{"调用子智能体" if is_sub_agent_task else "参数"}:</div>
            <pre style="margin: 0; padding: 6px; background: #1e1e1e; border-radius: 4px; overflow-x: auto; color: #d4d4d4; font-size: 11px;">{escape(json.dumps(tool_args, ensure_ascii=False, indent=2))}</pre>
            <div style="color: #888; margin: 8px 0 4px;">{"子智能体结果" if is_sub_agent_task else "结果"}</div>
            <pre style="margin: 0; padding: 6px; background: #1e1e1e; border-radius: 4px; overflow-x: auto; color: #d4d4d4; font-size: 11px; max-height: 400px; overflow-y: auto;">{result_escaped}</pre>
        </div>"""
    else:
        result_html = f"""
        <div style="padding: 8px 12px; border-top: 1px solid #3d3d3d; font-size: 12px;">
            <div style="color: #888; margin-bottom: 4px;">{"调用子智能体" if is_sub_agent_task else "参数"}:</div>
            <pre style="margin: 0; padding: 6px; background: #1e1e1e; border-radius: 4px; overflow-x: auto; color: #d4d4d4; font-size: 11px;">{escape(json.dumps(tool_args, ensure_ascii=False, indent=2))}</pre>
        </div>"""

    block_seed = "|".join(
        [
            str(tool_name or ""),
            json.dumps(tool_args or {}, ensure_ascii=False, sort_keys=True),
            str(result or ""),
            str(success),
        ]
    )
    block_key = "tool-" + hashlib.sha1(block_seed.encode("utf-8")).hexdigest()[:12]
    expanded_attr = "false" if collapsed else "true"
    body_style = "" if collapsed else ' style="height:auto; opacity:1;"'

    # 参数预览区域 + 对比按钮（参数可换行，按钮固定在右侧）
    preview_section = f"""<span style="display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; min-width: 0; width: 100%; margin-left: 15px;">
        <span style="color: #888; font-size: 11px; font-weight: normal; word-break: break-all; text-align: right; min-width: 0;">{escape(args_preview)}</span>
        {diff_icon_html}
    </span>"""

    return f"""<div class="cm-collapsible tool-block" data-block-key="{block_key}" data-expanded="{expanded_attr}" data-tool-call-id="{escape(tool_call_id or '')}" style="margin: 8px 0; background: #252525; border: 1px solid #3d3d3d; border-radius: 6px;">
    <button type="button" class="cm-collapsible__summary tool-block__summary" aria-expanded="{expanded_attr}" style="cursor: pointer; padding: 6px 10px; color: {title_color}; font-size: 13px; font-weight: 500; display: flex; align-items: flex-start; gap: 10px; width: 100%; background: transparent; border: none; text-align: left; box-sizing: border-box; flex-wrap: nowrap;">
        <span style="display: inline-flex; align-items: center; gap: 6px; min-width: 0; flex: 0 1 auto;">
            <span class="cm-collapsible__chevron" aria-hidden="true"></span>
            <span style="flex: 0 0 auto;">{icon}</span>
            <span style="white-space: nowrap; flex: 0 0 auto;">{escape(tool_name)}</span>
            {status_html}
        </span>
        {preview_section}
    </button>
    <div class="cm-collapsible__body"{body_style}>
        {result_html}
    </div>
</div>"""


def format_timestamp(ts: str) -> str:
    """格式化时间戳"""
    if not ts:
        return ""
    if len(ts) > 5:
        return ts[-5:]
    return ts
