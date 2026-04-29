# -*- coding: utf-8 -*-
"""
Git Diff 差异对比模块

提供生成 HTML diff 报告和在 PyQt WebEngine 中显示的功能
样式 100% 复刻 GitHub 网页合并差异审核界面
"""

import difflib
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from loguru import logger


class DiffHtmlGenerator:
    """Git Diff HTML 生成器 - GitHub 风格 100% 复刻"""

    # GitHub Dark 主题样式 - 完整复刻 GitHub Diff Review Interface
    GITHUB_DARK_CSS = """
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --gh-bg-primary: #0d1117;
            --gh-bg-secondary: #161b22;
            --gh-bg-tertiary: #21262d;
            --gh-border: #30363d;
            --gh-text-primary: #c9d1d9;
            --gh-text-secondary: #8b949e;
            --gh-text-link: #58a6ff;
            --gh-green-bg: rgba(63, 185, 80, 0.15);
            --gh-green-text: #3fb950;
            --gh-green-border: rgba(63, 185, 80, 0.4);
            --gh-red-bg: rgba(248, 81, 73, 0.15);
            --gh-red-text: #f85149;
            --gh-red-border: rgba(248, 81, 73, 0.4);
            --gh-blue-bg: rgba(31, 111, 235, 0.15);
            --gh-blue-text: #388bfd;
            --gh-blue-border: rgba(31, 111, 235, 0.4);
            --gh-purple-bg: rgba(163, 113, 247, 0.15);
            --gh-purple-text: #a371f7;
            --gh-font-mono: 'Consolas', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            --gh-font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }

        body {
            font-family: var(--gh-font-sans);
            background: var(--gh-bg-primary);
            color: var(--gh-text-primary);
            line-height: 1.5;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            font-size: 12px;
        }

        .diff-app {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        .file-tree {
            width: 280px;
            min-width: 280px;
            background: var(--gh-bg-secondary);
            border-right: 1px solid var(--gh-border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .file-tree-header {
            padding: 12px 16px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--gh-text-secondary);
            border-bottom: 1px solid var(--gh-border);
            flex-shrink: 0;
        }

        .file-tree-header .file-count {
            font-weight: 400;
            margin-left: 4px;
            opacity: 0.7;
        }

        .diff-summary {
            padding: 10px 16px;
            background: var(--gh-bg-tertiary);
            border-bottom: 1px solid var(--gh-border);
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 12px;
            flex-shrink: 0;
        }

        .diff-summary .summary-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .diff-summary .additions {
            color: var(--gh-green-text);
        }

        .diff-summary .deletions {
            color: var(--gh-red-text);
        }

        .diff-summary .separator {
            color: var(--gh-border);
        }

        .file-list {
            flex: 1;
            overflow-y: auto;
        }

        .file-item {
            display: flex;
            align-items: center;
            padding: 8px 16px;
            cursor: pointer;
            transition: background 0.1s;
            border-left: 3px solid transparent;
            text-decoration: none;
            color: var(--gh-text-primary);
            font-size: 12px;
        }

        .file-item:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        .file-item.active {
            background: rgba(56, 139, 253, 0.15);
            border-left-color: var(--gh-blue-text);
        }

        .file-item .file-icon {
            margin-right: 10px;
            font-size: 14px;
            opacity: 0.8;
        }

        .file-item .file-name {
            flex: 1;
            font-family: var(--gh-font-mono);
            font-size: 12px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .file-item .file-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            padding: 1px 6px;
            border-radius: 10px;
            margin-left: 8px;
        }

        .file-item .file-badge.added {
            background: var(--gh-green-bg);
            color: var(--gh-green-text);
        }

        .file-item .file-badge.deleted {
            background: var(--gh-red-bg);
            color: var(--gh-red-text);
        }

        .file-item .file-badge.renamed {
            background: var(--gh-purple-bg);
            color: var(--gh-purple-text);
        }

        .diff-content {
            flex: 1;
            overflow-y: auto;
        }

        .file-block {
            border-bottom: 1px solid var(--gh-border);
        }

        .file-block:last-child {
            border-bottom: none;
        }

        .file-header {
            position: sticky;
            top: 0;
            z-index: 10;
            background: var(--gh-bg-tertiary);
            padding: 10px 16px;
            border-bottom: 1px solid var(--gh-border);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .file-header .file-icon {
            font-size: 16px;
        }

        .file-header .file-path {
            color: var(--gh-text-link);
            font-family: var(--gh-font-mono);
            font-size: 13px;
            flex: 1;
        }

        .file-header .file-stats {
            display: flex;
            gap: 12px;
            font-size: 12px;
            font-family: var(--gh-font-mono);
        }

        .file-header .add-stat {
            color: var(--gh-green-text);
        }

        .file-header .del-stat {
            color: var(--gh-red-text);
        }

        .diff-table {
            width: 100%;
            border-collapse: collapse;
            font-family: var(--gh-font-mono);
            font-size: 12px;
        }

        .diff-line {
            display: flex;
        }

        .diff-line:hover {
            filter: brightness(1.1);
        }

        .line-num {
            width: 50px;
            min-width: 50px;
            padding: 0 8px;
            text-align: right;
            color: #6e7681;
            background: var(--gh-bg-primary);
            user-select: none;
            border-right: 1px solid var(--gh-border);
            vertical-align: top;
            white-space: pre;
            display: inline-block;
            font-size: 11px;
            line-height: 20px;
        }

        .line-num.old {
            background: rgba(248, 81, 73, 0.08);
            border-right-color: rgba(248, 81, 73, 0.2);
        }

        .line-num.new {
            background: rgba(63, 185, 80, 0.08);
            border-right-color: rgba(63, 185, 80, 0.2);
        }

        .line-sign {
            width: 20px;
            min-width: 20px;
            text-align: center;
            user-select: none;
            display: inline-block;
            vertical-align: top;
            font-size: 12px;
            line-height: 20px;
        }

        .line-code {
            flex: 1;
            padding: 0 12px;
            white-space: pre;
            vertical-align: top;
            display: inline-block;
            line-height: 20px;
            font-size: 12px;
            min-height: 20px;
        }

        .diff-line.added {
            background: var(--gh-green-bg);
        }

        .diff-line.added .line-num.new {
            color: var(--gh-green-text);
            background: rgba(63, 185, 80, 0.12);
        }

        .diff-line.added .line-sign {
            color: var(--gh-green-text);
        }

        .diff-line.added .line-code {
            color: var(--gh-green-text);
        }

        .diff-line.deleted {
            background: var(--gh-red-bg);
        }

        .diff-line.deleted .line-num.old {
            color: var(--gh-red-text);
            background: rgba(248, 81, 73, 0.12);
        }

        .diff-line.deleted .line-sign {
            color: var(--gh-red-text);
        }

        .diff-line.deleted .line-code {
            color: var(--gh-red-text);
        }

        .diff-line.context {
            background: transparent;
        }

        .diff-line.context .line-num {
            color: #6e7681;
        }

        .diff-line.context .line-sign {
            color: #6e7681;
        }

        .diff-line.context .line-code {
            color: var(--gh-text-primary);
        }

        .diff-line.hunk-header {
            background: var(--gh-blue-bg);
            border-top: 1px solid var(--gh-blue-border);
            border-bottom: 1px solid var(--gh-blue-border);
        }

        .diff-line.hunk-header .line-num {
            color: transparent;
            background: transparent;
            border: none;
        }

        .diff-line.hunk-header .line-sign {
            color: var(--gh-blue-text);
        }

        .diff-line.hunk-header .line-code {
            color: var(--gh-blue-text);
            font-size: 11px;
        }

        .diff-line.blank .line-code {
            background: var(--gh-bg-secondary);
        }

        .word-add {
            background: rgba(63, 185, 80, 0.35);
            border-radius: 2px;
        }

        .word-del {
            background: rgba(248, 81, 73, 0.35);
            border-radius: 2px;
            text-decoration: line-through;
        }

        .no-diff {
            text-align: center;
            padding: 80px 20px;
            color: var(--gh-text-secondary);
        }

        .no-diff-icon {
            font-size: 64px;
            margin-bottom: 20px;
            opacity: 0.5;
        }

        .no-diff h2 {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--gh-text-primary);
        }

        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--gh-bg-secondary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--gh-border);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #484f58;
        }

        ::-webkit-scrollbar-corner {
            background: var(--gh-bg-secondary);
        }
    </style>
    """

    @classmethod
    def escape_html(cls, text: str) -> str:
        """HTML 实体转义"""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    @classmethod
    def generate_html_report(cls, diff_output: str, session_id: str = "", lazy_load: bool = True) -> str:
        """生成完整的 HTML diff 报告
        
        Args:
            diff_output: diff 文本
            session_id: 会话 ID
            lazy_load: 是否启用懒加载（启用后只渲染前3个文件，后续滚动加载）
        """
        if diff_output is None:
            diff_output = ""

        # 解析 diff
        files = cls._parse_diff(diff_output)

        # 计算统计
        total_additions = sum(f["additions"] for f in files)
        total_deletions = sum(f["deletions"] for f in files)
        total_files = len(files)

        # 生成文件树 HTML 和懒加载数据
        file_tree_html = ""
        file_blocks_html = ""

        # 预渲染前 3 个文件用于首屏快速显示
        preload_count = 3 if lazy_load and total_files > 3 else total_files
        
        # 生成所有文件的懒加载数据
        files_json = cls._generate_file_data_json(files)
        
        for i, file_info in enumerate(files):
            file_id = f"file-{i}"
            file_tree_html += cls._generate_file_tree_item(file_info, file_id, i)
            
            # 只预渲染前 preload_count 个文件
            if i < preload_count:
                file_blocks_html += cls._generate_file_block(file_info, file_id, i)

        # 如果没有差异
        if not files:
            file_blocks_html = """
            <div class="no-diff">
                <div class="no-diff-icon">&#9989;</div>
                <h2>没有检测到文件差异</h2>
                <p>当前会话没有修改任何文件，或所有文件已恢复到原始状态</p>
            </div>
            """

        # 生成完整 HTML
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件差异对比报告</title>
    {cls.GITHUB_DARK_CSS}
</head>
<body>
    <div class="diff-app">
        <div class="file-tree">
            <div class="file-tree-header">
                已修改的文件
                <span class="file-count">({total_files})</span>
            </div>
            <div class="diff-summary">
                <span class="summary-item additions">
                    <span>+{total_additions}</span>
                </span>
                <span class="separator">|</span>
                <span class="summary-item deletions">
                    <span>-{total_deletions}</span>
                </span>
                <span class="separator" style="margin-left: auto; opacity: 0.5;">
                    {datetime.now().strftime("%H:%M")}
                </span>
            </div>
            <div class="file-list">
                {file_tree_html}
            </div>
        </div>

        <div class="diff-content" id="diff-content">
            {file_blocks_html}
        </div>
    </div>

    <script>
        // 文件数据存储（用于懒加载）
        window._diffFiles = {files_json};
        window._loadedFiles = new Set({list(range(preload_count))});
        window._preloadCount = {preload_count};
        
        function loadFileContent(fileId, index) {{
            if (window._loadedFiles.has(index)) return;
            window._loadedFiles.add(index);
            
            const fileInfo = window._diffFiles[index];
            if (!fileInfo) return;
            
            const container = document.getElementById('diff-content');
            const placeholder = document.getElementById('placeholder-' + fileId);
            
            if (placeholder) {{
                placeholder.outerHTML = fileInfo.html;
            }} else {{
                // 直接追加
                const div = document.createElement('div');
                div.id = fileId;
                div.className = 'file-block';
                div.innerHTML = fileInfo.header + '<div class="diff-table">' + fileInfo.rows + '</div>';
                container.appendChild(div);
            }}
        }}
        
        // 点击文件列表项时加载并滚动
        document.querySelectorAll('.file-item').forEach(item => {{
            item.addEventListener('click', function(e) {{
                e.preventDefault();
                const targetId = this.getAttribute('data-target');
                const index = parseInt(targetId.replace('file-', ''));
                
                // 加载文件内容
                loadFileContent(targetId, index);
                
                // 更新激活状态
                document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
                this.classList.add('active');
                
                // 滚动到目标位置
                const target = document.getElementById(targetId);
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
            }});
        }});

        // 滚动时懒加载可见区域的文件
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    const id = entry.target.id;
                    const index = parseInt(id.replace('file-', ''));
                    loadFileContent(id, index);
                    
                    // 更新激活状态
                    const correspondingItem = document.querySelector(`.file-item[data-target="${{id}}"]`);
                    if (correspondingItem) {{
                        document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
                        correspondingItem.classList.add('active');
                    }}
                }}
            }});
        }}, {{ threshold: 0.1, rootMargin: '200px' }});

        // 观察已加载的文件块
        document.querySelectorAll('.file-block').forEach(block => {{
            observer.observe(block);
        }});

        // 激活第一个文件
        const firstItem = document.querySelector('.file-item');
        if (firstItem) firstItem.classList.add('active');
    </script>
</body>
</html>"""

        return html

    @classmethod
    def _parse_diff(cls, diff_output: str) -> List[Dict]:
        """解析 unified diff 输出"""
        if not diff_output:
            return []

        files = []
        current_file = None
        current_lines = []
        current_stats = {"additions": 0, "deletions": 0}

        for line in diff_output.split("\n"):
            # 检测新文件开始
            if line.startswith("--- "):
                # 保存之前的文件
                if current_file and current_lines:
                    files.append(
                        {
                            "path": current_file,
                            "additions": current_stats["additions"],
                            "deletions": current_stats["deletions"],
                            "lines": current_lines,
                        }
                    )

                # 提取文件名
                parts = line[4:].strip()
                if parts.startswith("a/") or parts.startswith("b/"):
                    current_file = parts[2:]
                else:
                    current_file = parts

                current_lines = []
                current_stats = {"additions": 0, "deletions": 0}
                continue

            if current_file is None:
                continue

            # 统计
            if line.startswith("+") and not line.startswith("+++"):
                current_stats["additions"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_stats["deletions"] += 1

            current_lines.append(line)

        # 保存最后一个文件
        if current_file and current_lines:
            files.append(
                {
                    "path": current_file,
                    "additions": current_stats["additions"],
                    "deletions": current_stats["deletions"],
                    "lines": current_lines,
                }
            )

        return files

    @classmethod
    def _generate_file_tree_item(cls, file_info: Dict, file_id: str, index: int) -> str:
        """生成文件树项 HTML"""
        path = file_info["path"]
        additions = file_info["additions"]
        deletions = file_info["deletions"]

        icon = cls._get_file_icon(path)
        file_name = Path(path).name

        badges = ""
        if additions > 0:
            badges += f'<span class="file-badge added">+{additions}</span>'
        if deletions > 0:
            badges += f'<span class="file-badge deleted">-{deletions}</span>'

        return f'''
        <a href="#{file_id}" class="file-item" data-target="{file_id}">
            <span class="file-icon">{icon}</span>
            <span class="file-name" title="{cls.escape_html(path)}">{cls.escape_html(file_name)}</span>
            {badges}
        </a>
        '''
    
    @classmethod
    def _generate_file_data_json(cls, files: List[Dict]) -> str:
        """生成文件数据 JSON（用于懒加载），包含每个文件的完整 HTML"""
        import json
        
        files_data = []
        for i, file_info in enumerate(files):
            file_id = f"file-{i}"
            rows_html = cls._generate_file_block_rows(file_info)
            header_html = cls._generate_file_block_header(file_info, file_id)
            
            files_data.append({
                "id": file_id,
                "header": header_html,
                "rows": rows_html
            })
        
        return json.dumps(files_data, ensure_ascii=False)
    
    @classmethod
    def _generate_file_block_header(cls, file_info: Dict, file_id: str) -> str:
        """生成文件块头部 HTML"""
        path = file_info["path"]
        additions = file_info["additions"]
        deletions = file_info["deletions"]
        icon = cls._get_file_icon(path)
        
        return f'''<div class="file-header">
            <span class="file-icon">{icon}</span>
            <span class="file-path">{cls.escape_html(path)}</span>
            <div class="file-stats">
                {f'<span class="add-stat">+{additions}</span>' if additions > 0 else ""}
                {f'<span class="del-stat">-{deletions}</span>' if deletions > 0 else ""}
            </div>
        </div>'''
    
    @classmethod
    def _generate_file_block_rows(cls, file_info: Dict) -> str:
        """生成文件块的行内容 HTML（不含外层容器）"""
        lines = file_info["lines"]
        diff_rows_html = ""
        old_line_num = 1
        new_line_num = 1

        for line in lines:
            if line.startswith("@@"):
                match = re.search(r"@@ -(\d+),?\d* \+(\d+),?\d* @@", line)
                if match:
                    old_line_num = int(match.group(1))
                    new_line_num = int(match.group(2))

                diff_rows_html += f"""
                <div class="diff-line hunk-header">
                    <span class="line-num"></span>
                    <span class="line-num"></span>
                    <span class="line-sign"></span>
                    <span class="line-code">{cls.escape_html(line)}</span>
                </div>
                """
            elif line.startswith("-"):
                diff_rows_html += f"""
                <div class="diff-line deleted">
                    <span class="line-num old">{old_line_num}</span>
                    <span class="line-num"></span>
                    <span class="line-sign">-</span>
                    <span class="line-code">{cls.escape_html(line[1:])}</span>
                </div>
                """
                old_line_num += 1
            elif line.startswith("+"):
                diff_rows_html += f"""
                <div class="diff-line added">
                    <span class="line-num"></span>
                    <span class="line-num new">{new_line_num}</span>
                    <span class="line-sign">+</span>
                    <span class="line-code">{cls.escape_html(line[1:])}</span>
                </div>
                """
                new_line_num += 1
            elif line.startswith(" "):
                diff_rows_html += f"""
                <div class="diff-line context">
                    <span class="line-num">{old_line_num}</span>
                    <span class="line-num">{new_line_num}</span>
                    <span class="line-sign"></span>
                    <span class="line-code">{cls.escape_html(line[1:] if line else "")}</span>
                </div>
                """
                old_line_num += 1
                new_line_num += 1
            else:
                diff_rows_html += f"""
                <div class="diff-line context">
                    <span class="line-num"></span>
                    <span class="line-num"></span>
                    <span class="line-sign"></span>
                    <span class="line-code">{cls.escape_html(line)}</span>
                </div>
                """
        
        return diff_rows_html

    @classmethod
    def _generate_file_block(cls, file_info: Dict, file_id: str, index: int) -> str:
        """生成文件块 HTML（包含头部和内容）"""
        header_html = cls._generate_file_block_header(file_info, file_id)
        rows_html = cls._generate_file_block_rows(file_info)
        
        return f'''
        <div class="file-block" id="{file_id}">
            {header_html}
            <div class="diff-table">
                {rows_html}
            </div>
        </div>
        '''

    @classmethod
    def _get_file_icon(cls, path: str) -> str:
        """获取文件图标"""
        if path.endswith(".py"):
            return "&#128464;"
        elif path.endswith(".json"):
            return "&#128196;"
        elif path.endswith((".js", ".ts")):
            return "&#128203;"
        elif path.endswith((".html", ".css")):
            return "&#127760;"
        else:
            return "&#128196;"

    @classmethod
    def get_diff_for_files(cls, file_paths: List[str], session_id: str = "") -> str:
        """获取指定文件的差异（直接从备份目录对比）"""
        try:
            # 过滤存在的文件
            existing_files = [f for f in file_paths if Path(f).exists()]

            if not existing_files:
                logger.warning("[DiffHtml] 没有找到有效的文件路径")
                return ""

            # 备份目录: canvas_files/backups/{session_id}/
            backup_dir = Path("canvas_files/backups") / session_id

            if not backup_dir.exists():
                logger.warning(f"[DiffHtml] 备份目录不存在: {backup_dir}")
                return ""

            # 生成 unified diff
            diff_parts = []

            for current_path in existing_files:
                try:
                    filename = Path(current_path).name
                    file_stem = Path(current_path).stem

                    # 在备份目录中查找匹配的文件（跳过 .after.bak）
                    backup_path = None
                    bak_files = sorted(
                        f for f in backup_dir.glob(f"{file_stem}*.bak")
                        if not f.name.endswith('.after.bak')
                    )
                    if bak_files:
                        backup_path = bak_files[0]  # 选择最早的备份

                    if not backup_path:
                        logger.debug(f"[DiffHtml] 未找到备份: {filename}")
                        continue

                    # 读取文件内容
                    with open(
                        backup_path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        old_content = f.read()
                    with open(
                        current_path, "r", encoding="utf-8", errors="replace"
                    ) as f:
                        new_content = f.read()

                    # 使用 difflib 生成 unified diff（确保每行都有换行符，处理单行文件无末尾换行符的情况）
                    def normalize_lines(content):
                        lines = content.splitlines(keepends=True)
                        if lines and not lines[-1].endswith('\n'):
                            lines[-1] += '\n'
                        return lines

                    old_lines = normalize_lines(old_content)
                    new_lines = normalize_lines(new_content)

                    diff = difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=filename,
                        tofile=filename,
                        lineterm="\n",
                    )

                    diff_text = "".join(diff)
                    if diff_text:
                        diff_parts.append(diff_text)
                        logger.debug(f"[DiffHtml] {filename}: 找到差异")

                except Exception as e:
                    logger.warning(f"[DiffHtml] 对比失败 {current_path}: {e}")
                    continue

            result = "\n".join(diff_parts)
            logger.info(
                f"[DiffHtml] 对比完成: {len(result)} 字符, {len(diff_parts)} 个文件"
            )
            return result

        except Exception as e:
            logger.error(f"[DiffHtml] 获取 diff 失败: {e}")
            return ""

    @classmethod
    def generate_report_for_files(
        cls, file_paths: List[str], session_id: str = ""
    ) -> str:
        """为指定文件生成 diff 报告"""
        diff_output = cls.get_diff_for_files(file_paths, session_id)
        return cls.generate_html_report(diff_output or "", session_id)


class DiffViewerWindow:
    """PyQt WebEngine 差异查看窗口"""

    _instances = []

    @classmethod
    def close_all(cls):
        """关闭所有实例"""
        for window in cls._instances[:]:
            try:
                window.close()
            except Exception:
                pass
        cls._instances.clear()

    def __init__(self, parent=None):
        """初始化窗口"""
        from PyQt5.QtWidgets import QDialog, QHBoxLayout
        from PyQt5.QtCore import Qt
        from PyQt5.QtWebEngineWidgets import QWebEngineView

        self._window = QDialog(parent)
        self._dialog_class = QDialog
        self._window.setWindowTitle("文件差异对比")
        self._window.resize(1200, 800)

        if parent:
            self._window.setWindowFlags(self._window.windowFlags() | Qt.WindowModal)

        # 创建布局
        layout = QHBoxLayout(self._window)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 WebEngineView
        self._webview = QWebEngineView()

        layout.addWidget(self._webview)

        # 注册关闭事件
        self._window.destroyed.connect(lambda: self._on_closed())
        self._instances.append(self)

    def _on_closed(self):
        """窗口关闭回调"""
        if self in self._instances:
            self._instances.remove(self)

    def load_html(self, html_content: str):
        """加载 HTML 内容"""
        self._webview.setHtml(html_content)

    def show(self):
        """显示窗口"""
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def close(self):
        """关闭窗口"""
        self._window.close()

    @property
    def widget(self):
        """获取底层窗口部件"""
        return self._window
