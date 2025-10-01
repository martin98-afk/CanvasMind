from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import QRegExp


def make_format(color, bold=False, italic=False):
    """快速生成格式"""
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """接近 PyCharm 的 Python 语法高亮器"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Darcula 风格配色
        self.styles = {
            "keyword": make_format("#CC7832", bold=True),
            "builtin": make_format("#A9B7C6"),
            "constant": make_format("#9876AA", bold=True),
            "string": make_format("#6A8759"),
            "fstring_var": make_format("#FFC66D", bold=True),
            "comment": make_format("#808080", italic=True),
            "numbers": make_format("#6897BB"),
            "class": make_format("#A9B7C6", bold=True),
            "function": make_format("#A9B7C6"),
            "decorator": make_format("#BBB529"),
            "todo": make_format("#FF6B68", bold=True),  # TODO/FIXME 高亮
            "error": make_format("#FF5555", bold=True),  # 错误提示
        }

        # 关键字
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def", "del", "elif",
            "else", "except", "False", "finally", "for", "from", "global", "if", "import",
            "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass", "raise",
            "return", "True", "try", "while", "with", "yield", "self", "cls", "super"
        ]

        # 内置函数（剔除 self/cls）
        builtins = [
            "abs", "dict", "help", "min", "setattr", "all", "dir", "hex", "next",
            "slice", "any", "divmod", "id", "object", "sorted", "ascii", "enumerate",
            "input", "oct", "staticmethod", "bin", "eval", "int", "open", "str",
            "bool", "exec", "isinstance", "ord", "sum", "bytearray", "filter", "issubclass",
            "pow", "super", "bytes", "float", "iter", "print", "tuple", "callable",
            "format", "len", "property", "type", "chr", "frozenset", "list", "range",
            "vars", "classmethod", "getattr", "locals", "repr", "zip", "compile",
            "globals", "map", "reversed", "__import__", "complex", "hasattr", "max",
            "round", "delattr", "hash", "memoryview", "set",
        ]

        # 正则规则表
        self.rules = []

        # 关键字
        self.rules += [(r"\b%s\b" % w, 0, self.styles["keyword"]) for w in keywords]
        # 内置函数
        self.rules += [(r"\b%s\b" % w, 0, self.styles["builtin"]) for w in builtins]
        # 常量
        self.rules += [(r"\b(True|False|None|self|cls)\b", 0, self.styles["constant"])]
        # 数字
        self.rules += [(r"\b[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?\b", 0, self.styles["numbers"])]
        self.rules += [(r"\b0x[0-9A-Fa-f]+\b", 0, self.styles["numbers"])]
        # 装饰器
        self.rules += [(r"@\w+", 0, self.styles["decorator"])]
        # 类定义
        self.rules += [(r"\bclass\s+(\w+)", 1, self.styles["class"])]
        # 函数定义
        self.rules += [(r"\bdef\s+(\w+)", 1, self.styles["function"])]

        # 编译规则
        self.rules = [(QRegExp(pat), idx, fmt) for pat, idx, fmt in self.rules]

        # 多行字符串 delimiter
        self.tri_single = QRegExp("'''")
        self.tri_double = QRegExp('"""')

    def highlightBlock(self, text):
        """逐行高亮"""
        # 基础规则
        for expression, nth, fmt in self.rules:
            index = expression.indexIn(text, 0)
            while index >= 0:
                length = expression.matchedLength()
                if nth != 0:
                    index = expression.pos(nth)
                    length = len(expression.cap(nth))
                self.setFormat(index, length, fmt)
                index = expression.indexIn(text, index + length)

        # 注释
        if "#" in text:
            comment_index = text.find("#")
            self.setFormat(comment_index, len(text) - comment_index, self.styles["comment"])
            # TODO/FIXME 高亮
            for marker in ["TODO", "FIXME"]:
                idx = text.find(marker, comment_index)
                if idx != -1:
                    self.setFormat(idx, len(marker), self.styles["todo"])

        # f-string & 普通字符串（单行）
        string_re = QRegExp(r"([fF]?[rR]?(\"([^\"\\]|\\.)*\"|'([^'\\]|\\.)*'))")
        i = string_re.indexIn(text)
        while i >= 0:
            length = string_re.matchedLength()
            string_text = string_re.cap(1)

            if string_text.startswith(("f", "F")):
                self.setFormat(i, length, self.styles["string"])
                # f-string 内部 {}
                brace_re = QRegExp(r"\{[^}]*\}")
                bi = brace_re.indexIn(string_text)
                while bi >= 0:
                    self.setFormat(i + bi, len(brace_re.cap(0)), self.styles["fstring_var"])
                    bi = brace_re.indexIn(string_text, bi + len(brace_re.cap(0)))
            else:
                self.setFormat(i, length, self.styles["string"])

            i = string_re.indexIn(text, i + length)

        # --- 多行字符串处理 ---
        self.setCurrentBlockState(0)

        if not self.match_multiline(text, self.tri_single, 1, self.styles["string"]):
            self.match_multiline(text, self.tri_double, 2, self.styles["string"])

    def match_multiline(self, text, delimiter, in_state, style):
        """处理多行字符串，避免影响后续内容"""
        start = 0

        # 如果前一个 block 已经在字符串里，就继续染色
        if self.previousBlockState() == in_state:
            start = 0
        else:
            start = delimiter.indexIn(text)

        while start >= 0:
            end = delimiter.indexIn(text, start + 3)
            if end >= 0:
                # 找到闭合
                length = end - start + 3
                self.setCurrentBlockState(0)
            else:
                # 未闭合，持续到行尾
                self.setCurrentBlockState(in_state)
                length = len(text) - start
            self.setFormat(start, length, style)
            start = delimiter.indexIn(text, start + length)

        return self.currentBlockState() == in_state
