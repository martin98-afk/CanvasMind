# -*- coding: utf-8 -*-
import os
import platform
import re
import locale
from qfluentwidgets import FluentIcon, ToolButton
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QMenu,
)
from PyQt5.QtCore import Qt, QProcess, pyqtSignal
from PyQt5.QtGui import (
    QTextCursor,
    QColor,
    QTextCharFormat,
    QFont,
    QKeyEvent,
    QPalette,
)

from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class InlineTerminal(QTextEdit):
    command_entered = pyqtSignal(str)
    interrupt_requested = pyqtSignal()
    completion_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._history_index = -1
        self._command_start_pos = 0
        self._max_line_count = 10000
        self._completing = False
        self._setup_style()
        self._setup_context_menu()

    def _setup_style(self):
        # 优先使用 Cascadia Code 或 Consolas 等宽字体
        font = QFont("Cascadia Code", 10)
        if not font.fixedPitch():
            font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                padding: 4px;
            }
        """)

        self.setUndoRedoEnabled(False)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.setTabStopDistance(30)
        # 解决滚动条样式适配
        self.verticalScrollBar().setStyleSheet("width: 8px;")

    def _setup_context_menu(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        copy_action = menu.addAction("复制")
        paste_action = menu.addAction("粘贴")
        menu.addSeparator()
        clear_action = menu.addAction("清空终端")

        copy_action.triggered.connect(self.copy)
        paste_action.triggered.connect(self.paste)
        clear_action.triggered.connect(self.clear)
        menu.exec_(self.mapToGlobal(pos))

    def keyPressEvent(self, event: QKeyEvent):
        cursor = self.textCursor()

        # 1. 保护机制：如果光标在只读区，尝试输入时自动跳到末尾
        if cursor.position() < self._command_start_pos:
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_C:
                super().keyPressEvent(event)  # 允许复制
                return
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)

        # 2. 回车键执行命令
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cmd = self._get_current_input()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText("\n")
            self._command_start_pos = cursor.position()
            self.command_entered.emit(cmd)
            self._history_index = -1
            event.accept()
            return

        # 3. 退格键保护：不能删除提示符之前的文字
        if event.key() == Qt.Key_Backspace:
            if cursor.position() <= self._command_start_pos:
                if not cursor.hasSelection():
                    event.accept()
                    return

        # 4. 历史记录导航 (向上/向下)
        if event.key() == Qt.Key_Up:
            self._navigate_history(-1)
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self._navigate_history(1)
            event.accept()
            return

        # 5. Ctrl+C 中断信号
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            if not cursor.hasSelection():
                self.interrupt_requested.emit()
                event.accept()
                return

        # 6. Home键跳到命令开头而不是行首
        if event.key() == Qt.Key_Home:
            cursor.setPosition(self._command_start_pos)
            self.setTextCursor(cursor)
            event.accept()
            return

        # 7. Tab键补全
        if event.key() == Qt.Key_Tab:
            if not self._completing:
                self._completing = True
                self.completion_requested.emit(self._get_current_input())
            event.accept()
            return

        self._completing = False
        super().keyPressEvent(event)

    def _navigate_history(self, direction):
        if not self._history:
            return

        if direction == -1:  # Up
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
        else:  # Down
            if self._history_index > -1:
                self._history_index -= 1

        if self._history_index == -1:
            self._replace_command("")
        else:
            cmd = self._history[-(self._history_index + 1)]
            self._replace_command(cmd)

    def _get_current_input(self):
        cursor = self.textCursor()
        cursor.setPosition(self._command_start_pos)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        return cursor.selectedText()

    def _replace_command(self, text):
        cursor = self.textCursor()
        cursor.setPosition(self._command_start_pos)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def append_output(self, text):
        """解析 ANSI 转义序列并追加文本"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        ansi_clean = re.compile(
            r"\x1b(\[[0-9;]*[A-Za-z]|\][^\x07]*\x07|\[[0-9;]*H|\[[0-9]*[JKJ]|\[[0-9]*;[0-9]*H|\=)"
        )
        color_pattern = re.compile(r"\x1b\[([\d;]*)m")

        text = ansi_clean.sub("", text)

        parts = color_pattern.split(text)
        current_fmt = QTextCharFormat()
        current_fmt.setForeground(QColor("#D4D4D4"))

        for part in parts:
            if part.startswith("\x1b[") or not part:
                codes = part.strip("\x1b[").strip("m").split(";")
                for code in codes:
                    if code in ("0", ""):
                        current_fmt = QTextCharFormat()
                        current_fmt.setForeground(QColor("#D4D4D4"))
                    elif code == "1":
                        current_fmt.setFontWeight(QFont.Bold)
                    elif "30" <= code <= "37" or "90" <= code <= "97":
                        current_fmt.setForeground(self._get_ansi_color(code))
            else:
                cursor.insertText(part, current_fmt)

        self._command_start_pos = cursor.position()
        self.ensureCursorVisible()

    def _get_ansi_color(self, code):
        colors = {
            "30": "#000000",
            "31": "#CD3131",
            "32": "#0DBC79",
            "33": "#E5E510",
            "34": "#2472C8",
            "35": "#BC3FBC",
            "36": "#11A8CD",
            "37": "#E5E5E5",
            "90": "#666666",
            "91": "#F14C4C",
            "92": "#23D18B",
            "93": "#F5F543",
            "94": "#3B8EEA",
            "95": "#D670D6",
            "96": "#29B8DB",
            "97": "#FFFFFF",
        }
        return QColor(colors.get(code, "#D4D4D4"))

    def add_to_history(self, cmd):
        if cmd.strip() and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._history_index = -1

    def do_completion(self, completion):
        if completion:
            cursor = self.textCursor()
            cursor.setPosition(self._command_start_pos)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertText(completion)
            self.setTextCursor(cursor)
        self._completing = False


class ShellConsoleToolWindow(ToolWindow):
    name = "Shell 命令行"
    icon = get_icon("shell")
    singleton = True
    default_position = DockPosition.BOTTOM
    CATEGORIES = ["运行画布"]

    def __init__(self, page, button):
        self.process = None
        self.working_directory = os.getcwd()
        # 获取系统编码，Windows 下 PowerShell 通常是 GBK/CP936
        self.encoding = locale.getpreferredencoding()
        super().__init__(page, button)
        self.setWindowTitle("Terminal")

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.terminal = InlineTerminal()
        self.terminal.command_entered.connect(self._on_command_entered)
        self.terminal.interrupt_requested.connect(self._interrupt_process)
        self.terminal.completion_requested.connect(self._on_completion_requested)
        self._completion_options = []
        self._completion_index = 0

        layout.addWidget(self.terminal, 1)

        self._start_shell()
        self._print_welcome()

    def _setup_title_bar(self):
        title_bar = self.get_title_bar()
        title_bar.set_title("Shell 命令行")

        self.cwd_label = QLabel(self._shorten_path(self.working_directory))
        self.cwd_label.setObjectName("cwdLabel")
        self.cwd_label.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: normal;"
        )
        title_bar.insert_button(1, self.cwd_label)

        self.stop_btn = ToolButton(FluentIcon.PAUSE)
        self.stop_btn.setToolTip("中断当前命令 (Ctrl+C)")
        self.stop_btn.clicked.connect(self._interrupt_process)
        title_bar.add_button(self.stop_btn)

        self.clear_btn = ToolButton(FluentIcon.DELETE)
        self.clear_btn.setToolTip("清空屏幕")
        self.clear_btn.clicked.connect(self._clear_terminal)
        title_bar.add_button(self.clear_btn)

        self.restart_btn = ToolButton(FluentIcon.SYNC)
        self.restart_btn.setToolTip("重启会话")
        self.restart_btn.clicked.connect(self._restart_shell)
        title_bar.add_button(self.restart_btn)

    def _shorten_path(self, path):
        if len(path) > 50:
            return "..." + path[-47:]
        return path

    def _print_welcome(self):
        welcome = f"PyQt Terminal Shell [Version 1.0]\n系统编码: {self.encoding}\n\n"
        self.terminal.append_output(welcome)
        self._update_prompt()

    def _update_prompt(self):
        prompt = f"\x1b[92mPS {self.working_directory}>\x1b[0m "
        self.terminal.append_output(prompt)

    def _on_completion_requested(self, current_input):
        if not current_input:
            return

        base = os.path.basename(current_input)
        dir_path = os.path.dirname(current_input)
        if not dir_path:
            dir_path = "."

        try:
            entries = os.listdir(dir_path)
        except OSError:
            entries = []

        matches = []
        for entry in entries:
            if entry.startswith(base):
                full_path = os.path.join(dir_path, entry)
                if os.path.isdir(full_path):
                    matches.append(os.path.join(dir_path, entry) + os.sep)
                else:
                    matches.append(os.path.join(dir_path, entry))

        if len(matches) == 1:
            self.terminal.do_completion(matches[0])
        elif len(matches) > 1:
            self._completion_options = matches
            self._completion_index = 0
            self.terminal.do_completion(matches[0])
            self.terminal.append_output("\n")
            self.terminal.append_output("  ".join(matches) + "\n")
            self._update_prompt()
            last_cmd = self.terminal._get_current_input()
            self.terminal._replace_command(last_cmd)

    def _start_shell(self):
        if self.process:
            self.process.kill()

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyRead.connect(self._read_output)

        env = self.process.processEnvironment()
        # 强制设置 Python 在终端输出时不缓冲
        env.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(env)

        if platform.system() == "Windows":
            self.process.start("powershell.exe", ["-NoLogo", "-NoExit"])
        else:
            self.process.start("/bin/bash", ["-i"])

    def _read_output(self):
        if self.process:
            data = self.process.readAll().data()
            try:
                # 尝试使用系统编码解码，通常解决 Windows 下乱码
                text = data.decode(self.encoding)
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            self.terminal.append_output(text)

    def _on_command_entered(self, cmd):
        cmd_stripped = cmd.strip()
        if not cmd_stripped:
            self._update_prompt()
            return

        self.terminal.add_to_history(cmd_stripped)

        # 特殊处理内部命令
        if cmd_stripped.lower() in ("cls", "clear"):
            self.terminal.clear()
            self._update_prompt()
            return

        if cmd_stripped.lower().startswith("cd "):
            path = cmd_stripped[3:].strip().strip('"')
            if os.path.isdir(path):
                os.chdir(path)
                self.working_directory = os.getcwd()
                self.cwd_label.setText(self._shorten_path(self.working_directory))
                self.process.write(
                    f'cd "{self.working_directory}"\n'.encode(self.encoding)
                )
                self._update_prompt()
                return

        self.process.write((cmd + "\n").encode(self.encoding))

    def _interrupt_process(self):
        """发送 Ctrl+C 中断信号"""
        if self.process and self.process.state() == QProcess.Running:
            # 在某些 Windows 环境下，直接写 \x03 可能无效
            # 但对于交互式 shell 通常是有用的
            self.process.write(b"\x03")

    def _clear_terminal(self):
        self.terminal.clear()
        self._update_prompt()

    def _restart_shell(self):
        self._start_shell()
        self.terminal.clear()
        self._print_welcome()

    def cleanup(self):
        if self.process:
            self.process.kill()
            self.process.waitForFinished(1000)
