# -*- coding: utf-8 -*-
import re

from PyQt5.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter


# --- 新增：Python 语法高亮器 ---
class PythonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlighting_rules = []

        # 关键字
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0000FF"))  # 蓝色
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def",
            "del", "elif", "else", "except", "exec", "finally", "for",
            "from", "global", "if", "import", "in", "is", "lambda",
            "not", "or", "pass", "print", "raise", "return", "try",
            "while", "with", "yield", "None", "True", "False"
        ]
        for keyword in keywords:
            pattern = r'\b' + keyword + r'\b'
            self.highlighting_rules.append((re.compile(pattern), keyword_format))

        # 字符串 (单引号和双引号)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#008000"))  # 绿色
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), string_format))
        self.highlighting_rules.append((re.compile(r"'[^']*'"), string_format))

        # 注释
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#808080"))  # 灰色
        self.highlighting_rules.append((re.compile(r'#.*'), comment_format))

        # 内建函数和类型 (例如 len, print, int, str)
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#008B8B"))  # 深青色
        builtins = [
            "len", "max", "min", "sum", "int", "float", "str", "list",
            "dict", "set", "tuple", "print", "range", "enumerate",
            "zip", "map", "filter", "input", "open", "type", "id",
            "hasattr", "getattr", "setattr", "isinstance", "issubclass"
        ]
        for builtin in builtins:
            pattern = r'\b' + builtin + r'\b'
            self.highlighting_rules.append((re.compile(pattern), builtin_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            matches = pattern.finditer(text)
            for match in matches:
                start, end = match.span()
                self.setFormat(start, end - start, fmt)