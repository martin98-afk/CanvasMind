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
    """接近 PyCharm 的 Python 语法高亮器（增强版）"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Darcula 风格配色（优化对比度）
        self.styles = {
            "keyword": make_format("#CC7832", bold=True),        # 关键字
            "builtin": make_format("#A9B7C6"),                   # 内置函数
            "constant": make_format("#9876AA", bold=True),       # True/False/None
            "string": make_format("#6A8759"),                    # 字符串
            "fstring_var": make_format("#FFC66D", bold=True),    # f-string 变量
            "comment": make_format("#808080", italic=True),      # 注释
            "numbers": make_format("#6897BB"),                   # 数字
            "class": make_format("#A9B7C6", bold=True),          # 类名
            "function": make_format("#A9B7C6"),                  # 函数名
            "decorator": make_format("#BBB529"),                 # 装饰器
            "type_annotation": make_format("#A9B7C6", italic=True),  # 类型注解
            "todo": make_format("#FF6B68", bold=True),           # TODO/FIXME
            "error": make_format("#FF5555", bold=True),          # 错误
        }

        # 关键字（不含 self/cls/super）
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def", "del", "elif",
            "else", "except", "False", "finally", "for", "from", "global", "if", "import",
            "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass", "raise",
            "return", "True", "try", "while", "with", "yield"
        ]

        # 内置函数（含 self/cls/super）
        builtins = [
            "abs", "dict", "help", "min", "setattr", "all", "dir", "hex", "next",
            "slice", "any", "divmod", "id", "object", "sorted", "ascii", "enumerate",
            "input", "oct", "staticmethod", "bin", "eval", "int", "open", "str",
            "bool", "exec", "isinstance", "ord", "sum", "bytearray", "filter", "issubclass",
            "pow", "super", "bytes", "float", "iter", "print", "tuple", "callable",
            "format", "len", "property", "type", "chr", "frozenset", "list", "range",
            "vars", "classmethod", "getattr", "locals", "repr", "zip", "compile",
            "globals", "map", "reversed", "__import__", "complex", "hasattr", "max",
            "round", "delattr", "hash", "memoryview", "set", "self", "cls"
        ]

        # 正则规则表
        self.rules = []

        # 1. 关键字（优先级最高）
        self.rules += [(r"\b%s\b" % w, 0, self.styles["keyword"]) for w in keywords]
        # 2. 常量（True/False/None）
        self.rules += [(r"\b(True|False|None)\b", 0, self.styles["constant"])]
        # 3. 内置函数（包括 self/cls）
        self.rules += [(r"\b%s\b" % w, 0, self.styles["builtin"]) for w in builtins]
        # 4. 数字
        self.rules += [(r"\b[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?\b", 0, self.styles["numbers"])]
        self.rules += [(r"\b0[xX][0-9A-Fa-f]+\b", 0, self.styles["numbers"])]
        self.rules += [(r"\b0[oO][0-7]+\b", 0, self.styles["numbers"])]
        self.rules += [(r"\b0[bB][01]+\b", 0, self.styles["numbers"])]
        # 5. 装饰器
        self.rules += [(r"@\w+", 0, self.styles["decorator"])]
        # 6. 类定义
        self.rules += [(r"\bclass\s+(\w+)", 1, self.styles["class"])]
        # 7. 函数定义
        self.rules += [(r"\bdef\s+(\w+)", 1, self.styles["function"])]
        # 8. 类型注解（参数和返回值）
        self.rules += [(r":\s*(\w+)", 1, self.styles["type_annotation"])]
        self.rules += [(r"->\s*(\w+)", 1, self.styles["type_annotation"])]

        # 编译规则（预编译正则表达式提升性能）
        self.compiled_rules = [(QRegExp(pat), idx, fmt) for pat, idx, fmt in self.rules]

        # 多行字符串 delimiter
        self.tri_single = QRegExp("'''")
        self.tri_double = QRegExp('"""')

    def highlightBlock(self, text):
        """逐行高亮"""
        # 1. 基础规则（关键字、数字等）
        for expression, nth, fmt in self.compiled_rules:
            index = expression.indexIn(text)
            while index >= 0:
                if nth == 0:
                    length = expression.matchedLength()
                else:
                    index = expression.pos(nth)
                    length = len(expression.cap(nth))
                if length > 0:
                    self.setFormat(index, length, fmt)
                index = expression.indexIn(text, index + length)

        # 2. 注释（必须在字符串之后处理，避免字符串内 # 被误判）
        comment_start = -1
        in_string = False
        quote_char = None
        escaped = False

        # 简单状态机：跳过字符串内的 #
        for i, char in enumerate(text):
            if char == '\\' and not escaped:
                escaped = True
                continue
            if not escaped:
                if char in ('"', "'"):
                    if not in_string:
                        in_string = True
                        quote_char = char
                    elif char == quote_char:
                        in_string = False
                        quote_char = None
                elif char == '#' and not in_string:
                    comment_start = i
                    break
            escaped = False

        if comment_start != -1:
            self.setFormat(comment_start, len(text) - comment_start, self.styles["comment"])
            # TODO/FIXME 高亮
            for marker in ["TODO", "FIXME", "HACK", "XXX"]:
                idx = text.find(marker, comment_start)
                if idx != -1:
                    self.setFormat(idx, len(marker), self.styles["todo"])

        # 3. 字符串（单行）- 必须在注释之后，因为注释可能包含引号
        # 支持: "str", 'str', r"str", R'str', b"str", B'str', f"str", F'str' 及其组合
        string_re = QRegExp(r"([fF]?[rR]?[bB]?\"\"\"|([fF]?[rR]?[bB]?\"([^\"\\]|\\.)*\")|([fF]?[rR]?[bB]?'''|([fF]?[rR]?[bB]?'([^'\\]|\\.)*')))")
        i = string_re.indexIn(text)
        while i >= 0:
            full_match = string_re.cap(0)
            length = len(full_match)

            # 检查是否为多行字符串（已由下面的 match_multiline 处理）
            if full_match.startswith(('"""', "'''")):
                i = string_re.indexIn(text, i + length)
                continue

            # 单行字符串
            is_fstring = full_match.startswith(('f', 'F'))
            self.setFormat(i, length, self.styles["string"])

            if is_fstring:
                # 高亮 f-string 中的 {} 内容（但跳过 {{ 和 }}）
                content = full_match
                brace_start = 0
                while True:
                    open_brace = content.find('{', brace_start)
                    if open_brace == -1:
                        break
                    # 跳过转义的 {{
                    if open_brace + 1 < len(content) and content[open_brace + 1] == '{':
                        brace_start = open_brace + 2
                        continue
                    close_brace = content.find('}', open_brace)
                    if close_brace == -1:
                        break
                    # 提取 { 和 } 之间的内容（不包括格式说明符 :...）
                    inner = content[open_brace+1:close_brace]
                    if ':' in inner:
                        var_part = inner.split(':', 1)[0]
                        var_len = len(var_part)
                        self.setFormat(i + open_brace + 1, var_len, self.styles["fstring_var"])
                    else:
                        self.setFormat(i + open_brace + 1, len(inner), self.styles["fstring_var"])
                    brace_start = close_brace + 1

            i = string_re.indexIn(text, i + length)

        # 4. 多行字符串处理
        self.setCurrentBlockState(0)

        # 检查是否从多行字符串中继续
        prev_state = self.previousBlockState()
        if prev_state == 1:  # 三单引号
            self.match_multiline(text, self.tri_single, 1, self.styles["string"])
        elif prev_state == 2:  # 三双引号
            self.match_multiline(text, self.tri_double, 2, self.styles["string"])
        else:
            # 新开始的多行字符串
            if not self.match_multiline(text, self.tri_single, 1, self.styles["string"]):
                self.match_multiline(text, self.tri_double, 2, self.styles["string"])

    def match_multiline(self, text, delimiter, in_state, style):
        """处理多行字符串，避免影响后续内容"""
        start = 0
        set_state = False

        # 如果前一个 block 已经在字符串里
        if self.previousBlockState() == in_state:
            start = 0
            set_state = True
        else:
            start = delimiter.indexIn(text)
            if start >= 0:
                set_state = True

        if not set_state:
            return False

        while start >= 0:
            # 跳过转义的引号（但 Python 中三引号不能转义，所以简化处理）
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

        return self.currentBlockState() != 0