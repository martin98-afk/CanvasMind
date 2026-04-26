# -*- coding: utf-8 -*-
"""
Git Diff 差异对比模块

提供生成 HTML diff 报告和在 PyQt WebEngine 中显示的功能
样式贴近 GitHub 网页实现
"""

import difflib
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from loguru import logger


class DiffHtmlGenerator:
    """Git Diff HTML 生成器 - GitHub 风格"""

    # GitHub 风格的深色主题样式
    DARK_THEME_CSS = """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            line-height: 1.5;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }

        /* 主容器：文件树和内容并排 */
        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* 文件树侧边栏 */
        .file-tree {
            width: 260px;
            min-width: 260px;
            background: #161b22;
            border-right: 1px solid #30363d;
            display: flex;
            flex-direction: column;
        }

        .file-tree-header {
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            border-bottom: 1px solid #30363d;
            flex-shrink: 0;
        }

        /* 统计信息合并到文件树顶部 */
        .file-tree-stats {
            padding: 10px 16px;
            background: #161b22;
            border-bottom: 1px solid #30363d;
            display: flex;
            gap: 12px;
            font-size: 12px;
            flex-shrink: 0;
        }

        .file-tree-stats .stat-item {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .file-tree-stats .count {
            font-weight: 600;
        }

        .file-tree-stats .stat-item.added .count { color: #3fb950; }
        .file-tree-stats .stat-item.deleted .count { color: #f85149; }

        .file-tree-list {
            flex: 1;
            overflow-y: auto;
            padding: 6px 0;
        }

        .file-item {
            display: flex;
            align-items: center;
            padding: 8px 16px;
            cursor: pointer;
            transition: background 0.15s;
            border-left: 3px solid transparent;
            text-decoration: none;
            color: inherit;
        }

        .file-item:hover {
            background: #1f6feb1a;
        }

        .file-item.active {
            background: #1f6feb26;
            border-left-color: #1f6feb;
        }

        .file-icon {
            margin-right: 8px;
            font-size: 14px;
        }

        .file-name {
            flex: 1;
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .file-additions {
            font-size: 12px;
            color: #3fb950;
            margin-left: 8px;
        }

        .file-deletions {
            font-size: 12px;
            color: #f85149;
            margin-left: 4px;
        }

        /* 差异内容区域 */
        .diff-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        /* 文件块 */
        .file-block {
            margin-bottom: 30px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            overflow: hidden;
        }

        /* 固定的文件头 */
        .file-header {
            position: sticky;
            top: 0;
            z-index: 10;
            background: #21262d;
            padding: 12px 16px;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
        }

        .file-header .file-icon {
            margin-right: 10px;
        }

        .file-header .file-path {
            color: #58a6ff;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 14px;
            flex: 1;
        }

        .file-stats {
            display: flex;
            gap: 12px;
            font-size: 12px;
        }

        .add-count { color: #3fb950; }
        .del-count { color: #f85149; }

        /* 差异表格 */
        .diff-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
        }

        .diff-table tr:hover {
            background: #1f2937;
        }

        /* 行号列 */
        .line-num {
            width: 60px;
            padding: 0 8px;
            text-align: right;
            color: #6e7681;
            background: #0d1117;
            user-select: none;
            border-right: 1px solid #30363d;
            vertical-align: top;
            white-space: nowrap;
        }

        .line-num.old {
            background: rgba(248, 81, 73, 0.1);
        }

        .line-num.new {
            background: rgba(63, 185, 80, 0.1);
        }

        /* 代码内容列 */
        .line-content {
            padding: 0 12px;
            white-space: pre;
            vertical-align: top;
        }

        /* 行类型样式 */
        .add-line {
            background: rgba(63, 185, 80, 0.15);
        }

        .add-line .line-num {
            background: rgba(63, 185, 80, 0.2);
            color: #3fb950;
        }

        .add-line .line-content {
            color: #3fb950;
        }

        .del-line {
            background: rgba(248, 81, 73, 0.15);
        }

        .del-line .line-num {
            background: rgba(248, 81, 73, 0.2);
            color: #f85149;
        }

        .del-line .line-content {
            color: #f85149;
        }

        .context-line .line-content {
            color: #c9d1d9;
        }

        /* Hunk 头 */
        .hunk-header {
            background: rgba(31, 111, 235, 0.15) !important;
        }

        .hunk-header td {
            color: #58a6ff;
            padding: 4px 8px;
            font-size: 11px;
            border-top: 1px solid rgba(31, 111, 235, 0.3);
        }

        /* 行前缀符号 */
        .line-prefix {
            width: 20px;
            text-align: center;
            user-select: none;
        }

        .add-line .line-prefix { color: #3fb950; }
        .del-line .line-prefix { color: #f85149; }

        /* 无差异提示 */
        .no-diff {
            text-align: center;
            padding: 60px 20px;
            color: #6e7681;
        }

        .no-diff-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        /* 滚动条样式 */
        .file-tree-stats::-webkit-scrollbar,
        .file-tree-list::-webkit-scrollbar,
        .diff-container::-webkit-scrollbar {
            width: 8px;
        }

        .file-tree-stats::-webkit-scrollbar-track,
        .file-tree-list::-webkit-scrollbar-track,
        .diff-container::-webkit-scrollbar-track {
            background: #161b22;
        }

        .file-tree-stats::-webkit-scrollbar-thumb,
        .file-tree-list::-webkit-scrollbar-thumb,
        .diff-container::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 4px;
        }

        .file-tree-stats::-webkit-scrollbar-thumb:hover,
        .file-tree-list::-webkit-scrollbar-thumb:hover,
        .diff-container::-webkit-scrollbar-thumb:hover {
            background: #484f58;
        }
    </style>
    """

    @classmethod
    def escape_html(cls, text: str) -> str:
        """HTML 实体转义"""
        if not text:
            return ""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))

    @classmethod
    def generate_html_report(cls, diff_output: str, session_id: str = "") -> str:
        """生成完整的 HTML diff 报告"""
        if diff_output is None:
            diff_output = ""

        # 解析 diff
        files = cls._parse_diff(diff_output)

        # 计算统计
        total_additions = sum(f["additions"] for f in files)
        total_deletions = sum(f["deletions"] for f in files)
        total_files = len(files)

        # 生成文件树 HTML
        file_tree_html = ""
        file_blocks_html = ""

        for i, file_info in enumerate(files):
            file_id = f"file-{i}"
            file_tree_html += cls._generate_file_tree_item(file_info, file_id, i)
            file_blocks_html += cls._generate_file_block(file_info, file_id, i)

        # 如果没有差异
        if not files:
            file_blocks_html = '''
            <div class="no-diff">
                <div class="no-diff-icon">&#9989;</div>
                <h2>没有检测到文件差异</h2>
                <p>当前会话没有修改任何文件，或所有文件已恢复到原始状态</p>
            </div>
            '''

        # 生成完整 HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件差异对比报告</title>
    {cls.DARK_THEME_CSS}
</head>
<body>
    <!-- 主容器：文件树和内容区域并排 -->
    <div class="main-container">
        <!-- 文件树侧边栏 -->
        <div class="file-tree">
            <div class="file-tree-header">
                已修改的文件
                <span style="font-weight: 400; opacity: 0.7">({total_files})</span>
            </div>
            <!-- 统计信息合并到文件树 -->
            <div class="file-tree-stats">
                <div class="stat-item added">
                    <span class="count">+{total_additions}</span>
                </div>
                <div class="stat-item deleted">
                    <span class="count">-{total_deletions}</span>
                </div>
                <div class="stat-item" style="margin-left: auto; color: #8b949e;">
                    <span>{datetime.now().strftime("%H:%M")}</span>
                </div>
            </div>
            <div class="file-tree-list">
                {file_tree_html}
            </div>
        </div>

        <!-- 差异内容区域 -->
        <div class="diff-container" id="diff-container">
            {file_blocks_html}
        </div>
    </div>

    <script>
        // 文件点击滚动到对应位置
        document.querySelectorAll('.file-item').forEach(item => {{
            item.addEventListener('click', function(e) {{
                e.preventDefault();
                const targetId = this.getAttribute('data-target');
                const target = document.getElementById(targetId);
                if (target) {{
                    // 移除其他 active
                    document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
                    // 添加 active
                    this.classList.add('active');
                    // 滚动到目标
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
            }});
        }});

        // 监听滚动，更新文件树 active 状态
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    const id = entry.target.id;
                    const correspondingItem = document.querySelector(`.file-item[data-target="${{id}}"]`);
                    if (correspondingItem) {{
                        document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
                        correspondingItem.classList.add('active');
                    }}
                }}
            }});
        }}, {{ threshold: 0.1 }});

        document.querySelectorAll('.file-block').forEach(block => {{
            observer.observe(block);
        }});

        // 默认激活第一个文件
        const firstItem = document.querySelector('.file-item');
        if (firstItem) firstItem.classList.add('active');
    </script>
</body>
</html>'''

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
                    files.append({
                        "path": current_file,
                        "additions": current_stats["additions"],
                        "deletions": current_stats["deletions"],
                        "lines": current_lines
                    })

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
            files.append({
                "path": current_file,
                "additions": current_stats["additions"],
                "deletions": current_stats["deletions"],
                "lines": current_lines
            })

        return files

    @classmethod
    def _generate_file_tree_item(cls, file_info: Dict, file_id: str, index: int) -> str:
        """生成文件树项 HTML"""
        path = file_info["path"]
        additions = file_info["additions"]
        deletions = file_info["deletions"]

        # 获取文件图标
        if path.endswith(".py"):
            icon = "&#128464;"  # 蛇
        elif path.endswith(".json"):
            icon = "&#128196;"  # 文档
        elif path.endswith((".js", ".ts")):
            icon = "&#128203;"  # 脚本
        elif path.endswith((".html", ".css")):
            icon = "&#127760;"  # 网页
        else:
            icon = "&#128196;"  # 通用文件

        file_name = Path(path).name

        return f'''
        <a href="#{file_id}" class="file-item" data-target="{file_id}">
            <span class="file-icon">{icon}</span>
            <span class="file-name" title="{cls.escape_html(path)}">{cls.escape_html(file_name)}</span>
            {f'<span class="file-additions">+{additions}</span>' if additions > 0 else ''}
            {f'<span class="file-deletions">-{deletions}</span>' if deletions > 0 else ''}
        </a>
        '''

    @classmethod
    def _generate_file_block(cls, file_info: Dict, file_id: str, index: int) -> str:
        """生成文件块 HTML"""
        path = file_info["path"]
        additions = file_info["additions"]
        deletions = file_info["deletions"]
        lines = file_info["lines"]

        # 获取文件图标
        if path.endswith(".py"):
            icon = "&#128464;"
        elif path.endswith(".json"):
            icon = "&#128196;"
        elif path.endswith((".js", ".ts")):
            icon = "&#128203;"
        elif path.endswith((".html", ".css")):
            icon = "&#127760;"
        else:
            icon = "&#128196;"

        # 生成差异行 HTML
        diff_rows_html = ""
        old_line_num = 1
        new_line_num = 1

        for line in lines:
            if line.startswith("@@"):
                # 解析 hunk 头获取起始行号
                import re
                match = re.search(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
                if match:
                    old_line_num = int(match.group(1))
                    new_line_num = int(match.group(2))

                diff_rows_html += f'''
                <tr class="hunk-header">
                    <td colspan="3">{cls.escape_html(line)}</td>
                </tr>
                '''
            elif line.startswith("-"):
                diff_rows_html += f'''
                <tr class="del-line">
                    <td class="line-num old">{old_line_num}</td>
                    <td class="line-num"></td>
                    <td class="line-prefix">-</td>
                    <td class="line-content">{cls.escape_html(line[1:])}</td>
                </tr>
                '''
                old_line_num += 1
            elif line.startswith("+"):
                diff_rows_html += f'''
                <tr class="add-line">
                    <td class="line-num"></td>
                    <td class="line-num new">{new_line_num}</td>
                    <td class="line-prefix">+</td>
                    <td class="line-content">{cls.escape_html(line[1:])}</td>
                </tr>
                '''
                new_line_num += 1
            elif line.startswith(" "):
                diff_rows_html += f'''
                <tr class="context-line">
                    <td class="line-num">{old_line_num}</td>
                    <td class="line-num">{new_line_num}</td>
                    <td class="line-prefix"> </td>
                    <td class="line-content">{cls.escape_html(line[1:] if line else '')}</td>
                </tr>
                '''
                old_line_num += 1
                new_line_num += 1
            else:
                # 没有前缀的行（difflib 可能产生）
                diff_rows_html += f'''
                <tr class="context-line">
                    <td class="line-num"></td>
                    <td class="line-num"></td>
                    <td class="line-prefix"></td>
                    <td class="line-content">{cls.escape_html(line)}</td>
                </tr>
                '''

        return f'''
        <div class="file-block" id="{file_id}">
            <div class="file-header">
                <span class="file-icon">{icon}</span>
                <span class="file-path">{cls.escape_html(path)}</span>
                <div class="file-stats">
                    {f'<span class="add-count">+{additions}</span>' if additions > 0 else ''}
                    {f'<span class="del-count">-{deletions}</span>' if deletions > 0 else ''}
                </div>
            </div>
            <table class="diff-table">
                <tbody>
                    {diff_rows_html}
                </tbody>
            </table>
        </div>
        '''

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

                    # 在备份目录中查找匹配的文件
                    backup_path = None
                    bak_files = sorted(backup_dir.glob(f"{Path(current_path).stem}*.bak"))
                    if bak_files:
                        backup_path = bak_files[0]  # 选择最早的备份

                    if not backup_path:
                        logger.debug(f"[DiffHtml] 未找到备份: {filename}")
                        continue

                    # 读取文件内容
                    with open(backup_path, 'r', encoding='utf-8', errors='replace') as f:
                        old_content = f.read()
                    with open(current_path, 'r', encoding='utf-8', errors='replace') as f:
                        new_content = f.read()

                    # 使用 difflib 生成 unified diff
                    old_lines = old_content.splitlines(keepends=True)
                    new_lines = new_content.splitlines(keepends=True)

                    diff = difflib.unified_diff(
                        old_lines,
                        new_lines,
                        fromfile=filename,
                        tofile=filename,
                        lineterm='\n'
                    )

                    diff_text = ''.join(diff)
                    if diff_text:
                        diff_parts.append(diff_text)
                        logger.debug(f"[DiffHtml] {filename}: 找到差异")

                except Exception as e:
                    logger.warning(f"[DiffHtml] 对比失败 {current_path}: {e}")
                    continue

            result = "\n".join(diff_parts)
            logger.info(f"[DiffHtml] 对比完成: {len(result)} 字符, {len(diff_parts)} 个文件")
            return result

        except Exception as e:
            logger.error(f"[DiffHtml] 获取 diff 失败: {e}")
            return ""

    @classmethod
    def generate_report_for_files(cls, file_paths: List[str], session_id: str = "") -> str:
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
            self._window.setWindowFlags(
                self._window.windowFlags() | Qt.Dialog
            )

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