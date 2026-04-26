# -*- coding: utf-8 -*-
"""
UI 渲染辅助函数
"""

import json
import hashlib
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

    return f"<tool>\nname: {tool_name}\nargs: {args_json}\nresult: {result_str}\nsuccess: {success}\n</tool>"


def render_tool_block(
    tool_name: str,
    tool_args: dict,
    result: str = None,
    success: bool = None,
    collapsed: bool = False,
    tool_call_id: str = None,
) -> str:
    """渲染工具块 - 参数截断，结果可折叠"""
    max_args_display = 80

    args_preview = json.dumps(tool_args, ensure_ascii=False)
    if len(args_preview) > max_args_display:
        args_preview = args_preview[:max_args_display] + "..."

    status_html = ""
    if success is not None:
        status_color = "#4CAF50" if success else "#F44336"
        status_text = "✓" if success else "✗"
        status_html = f'<span style="color: {status_color}; font-weight: bold; margin-left: 6px;">{status_text}</span>'

    is_sub_agent_task = tool_name == "task"
    icon = "🤖" if is_sub_agent_task else "⚡"
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

    # 判断是否是需要文件操作的工具
    file_edit_tools = {"write", "edit", "multiedit", "patch"}
    is_file_edit = tool_name in file_edit_tools and tool_args.get("path")
    
    # 差异对比按钮
    diff_button_html = ""
    if is_file_edit and tool_call_id:
        diff_button_html = f'''
        <button type="button" class="tool-diff-btn" data-tool-call-id="{escape(tool_call_id)}" 
            style="cursor: pointer; padding: 2px 8px; font-size: 11px; background: #2d5a87; color: #fff; border: none; border-radius: 4px; margin-left: 4px;"
            onclick="window._requestToolDiff(this.dataset.toolCallId)"
            title="查看此工具产生的文件差异">📄 差异</button>'''

    if result is not None:
        result_str = str(result)
        result_stripped = strip_code_blocks(result_str[:500])
        result_escaped = escape(result_stripped)
        result_html = f"""
        <div style="padding: 8px 12px; border-top: 1px solid #3d3d3d; font-size: 12px;">
            <div style="color: #888; margin-bottom: 4px;">{"调用子智能体" if is_sub_agent_task else "参数"}:</div>
            <pre style="margin: 0; padding: 6px; background: #1e1e1e; border-radius: 4px; overflow-x: auto; color: #d4d4d4; font-size: 11px;">{escape(json.dumps(tool_args, ensure_ascii=False, indent=2))}</pre>
            <div style="color: #888; margin: 8px 0 4px; display: flex; align-items: center; gap: 8px;">{"子智能体结果" if is_sub_agent_task else "结果"}{diff_button_html}</div>
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
    body_style = "" if collapsed else " style=\"height:auto; opacity:1;\""

    return f"""<div class="cm-collapsible tool-block" data-block-key="{block_key}" data-expanded="{expanded_attr}" data-tool-call-id="{escape(tool_call_id or '')}" style="margin: 8px 0; background: #252525; border: 1px solid #3d3d3d; border-radius: 6px;">
    <button type="button" class="cm-collapsible__summary tool-block__summary" aria-expanded="{expanded_attr}" style="cursor: pointer; padding: 6px 10px; color: {title_color}; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; width: 100%; background: transparent; border: none; text-align: left;">
        <span class="cm-collapsible__chevron" aria-hidden="true"></span>
        <span>{icon}</span>
        <span>{escape(tool_name)}</span>
        {status_html}
        <span style="color: #888; font-size: 11px; font-weight: normal; margin-left: auto;">{escape(args_preview)}</span>
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
