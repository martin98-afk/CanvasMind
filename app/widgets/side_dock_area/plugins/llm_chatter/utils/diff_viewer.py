# -*- coding: utf-8 -*-
"""
Git Diff 差异对比模块

提供生成 HTML diff 报告和在 PyQt WebEngine 中显示的功能
"""

import difflib
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from loguru import logger


class DiffHtmlGenerator:
    """Git Diff HTML 生成器"""

    # GitHub 风格的暗色主题样式
    DARK_THEME_CSS = """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            line-height: 1.6;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #238636 0%, #2ea043 100%);
            padding: 20px 30px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .header h1 { color: #fff; font-size: 1.5rem; }
        .summary { display: flex; gap: 20px; margin-top: 15px; flex-wrap: wrap; }
        .stat {
            background: rgba(255,255,255,0.15);
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.9rem;
        }
        .stat.added { color: #80ff80; }
        .stat.removed { color: #ff8080; }

        .file-list { margin-bottom: 20px; }
        .file-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            margin-bottom: 15px;
            overflow: hidden;
        }
        .file-header {
            background: #21262d;
            padding: 12px 20px;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .file-icon { font-size: 1.2rem; }
        .file-path {
            color: #58a6ff;
            font-family: 'Consolas', monospace;
            font-size: 0.9rem;
            word-break: break-all;
        }
        .file-stats { margin-left: auto; display: flex; gap: 15px; font-size: 0.85rem; }
        .add-count { color: #3fb950; }
        .del-count { color: #f85149; }

        .diff-content { overflow-x: auto; }
        .diff-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.85rem;
        }
        .diff-table tr { background: #161b22; }
        .diff-table tr:nth-child(even) { background: #0d1117; }
        .line-num {
            width: 50px;
            padding: 2px 10px;
            text-align: right;
            color: #6e7681;
            background: #21262d;
            user-select: none;
            border-right: 1px solid #30363d;
        }
        .line-content { padding: 2px 15px; white-space: pre; }
        .add-line { background: rgba(63, 185, 80, 0.15) !important; }
        .add-line .line-content { color: #3fb950; }
        .add-line .line-num { background: rgba(63, 185, 80, 0.2); color: #3fb950; }
        .del-line { background: rgba(248, 81, 73, 0.15) !important; }
        .del-line .line-content { color: #f85149; }
        .del-line .line-num { background: rgba(248, 81, 73, 0.2); color: #f85149; }
        .context-line { background: #161b22; }
        .context-line .line-content { color: #c9d1d9; }
        .hunk-header { background: rgba(31, 111, 235, 0.12) !important; }
        .hunk-header .line-content { color: #58a6ff; font-style: italic; }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-modified { background: rgba(31, 111, 235, 0.25); color: #58a6ff; }
        .badge-added { background: rgba(35, 134, 54, 0.25); color: #3fb950; }
        .badge-deleted { background: rgba(248, 81, 73, 0.25); color: #f85149; }

        .no-diff {
            text-align: center;
            padding: 40px;
            color: #6e7681;
        }
        .no-diff-icon { font-size: 3rem; margin-bottom: 10px; }

        .footer {
            text-align: center;
            color: #6e7681;
            padding: 20px;
            font-size: 0.85rem;
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

        # 生成文件列表 HTML
        files_html = ""
        for file_info in files:
            files_html += cls._generate_file_html(file_info)

        # 如果没有差异
        if not files:
            files_html = '''
            <div class="no-diff">
                <div class="no-diff-icon">✅</div>
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
    <div class="header">
        <h1>📊 文件差异对比报告</h1>
        <div class="summary">
            <span class="stat">📁 变更文件: {len(files)} 个</span>
            <span class="stat added">➕ 新增: {total_additions} 行</span>
            <span class="stat removed">➖ 删除: {total_deletions} 行</span>
            <span class="stat">📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
        </div>
    </div>

    <div class="file-list">
        {files_html}
    </div>

    <div class="footer">
        生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        {' | 会话: ' + session_id[:8] + '...' if session_id else ''}
        | CanvasMind LLM Chatter
    </div>
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
    def _generate_file_html(cls, file_info: Dict) -> str:
        """生成单个文件差异的 HTML"""
        path = file_info["path"]
        additions = file_info["additions"]
        deletions = file_info["deletions"]
        lines = file_info["lines"]

        # 获取文件图标
        if path.endswith(".py"):
            icon = "🐍"
        elif path.endswith(".json"):
            icon = "📄"
        elif path.endswith((".js", ".ts")):
            icon = "📜"
        elif path.endswith((".html", ".css")):
            icon = "🌐"
        else:
            icon = "📝"

        # 获取文件状态 badge
        if additions > 0 and deletions > 0:
            badge_class = "badge-modified"
            badge_text = "已修改"
        elif additions > 0:
            badge_class = "badge-added"
            badge_text = "新增"
        else:
            badge_class = "badge-deleted"
            badge_text = "删除"

        # 生成行 HTML
        lines_html = ""
        for line in lines:
            if line.startswith("@@"):
                lines_html += f'''
                <tr class="hunk-header">
                    <td class="line-num">...</td>
                    <td class="line-content">{cls.escape_html(line)}</td>
                </tr>
                '''
            elif line.startswith("+"):
                lines_html += f'''
                <tr class="add-line">
                    <td class="line-num">+</td>
                    <td class="line-content">{cls.escape_html(line[1:])}</td>
                </tr>
                '''
            elif line.startswith("-"):
                lines_html += f'''
                <tr class="del-line">
                    <td class="line-num">-</td>
                    <td class="line-content">{cls.escape_html(line[1:])}</td>
                </tr>
                '''
            else:
                content = line[1:] if line.startswith(" ") else line
                lines_html += f'''
                <tr class="context-line">
                    <td class="line-num"> </td>
                    <td class="line-content">{cls.escape_html(content)}</td>
                </tr>
                '''

        return f'''
        <div class="file-card">
            <div class="file-header">
                <span class="file-icon">{icon}</span>
                <span class="file-path">{cls.escape_html(path)}</span>
                <span class="badge {badge_class}">{badge_text}</span>
                <div class="file-stats">
                    <span class="add-count">+{additions}</span>
                    <span class="del-count">-{deletions}</span>
                </div>
            </div>
            <div class="diff-content">
                <table class="diff-table">
                    {lines_html}
                </table>
            </div>
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
                    # 获取所有匹配的备份文件，按文件名排序（最早的在前）
                    bak_files = sorted(backup_dir.glob(f"{Path(current_path).stem}*.bak"))
                    if bak_files:
                        backup_path = bak_files[0]  # 选择最早的备份
                        logger.debug(f"[DiffHtml] 使用最早的备份: {backup_path.name}")

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
            import traceback
            traceback.print_exc()
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
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        from PyQt5.QtCore import Qt
        from PyQt5.QtWebEngineWidgets import QWebEngineView

        self._window = QDialog(parent)
        self._dialog_class = QDialog
        self._window.setWindowTitle("文件差异对比")
        self._window.resize(1000, 700)

        if parent:
            self._window.setWindowFlags(
                self._window.windowFlags() | Qt.Dialog
            )

        # 创建布局
        layout = QVBoxLayout(self._window)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 WebEngineView
        self._webview = QWebEngineView()
        self._webview.setStyleSheet("background: #0d1117;")

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
