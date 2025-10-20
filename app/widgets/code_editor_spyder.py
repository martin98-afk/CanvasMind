# -*- coding: utf-8 -*-
import os
import sys
import time
import re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Tuple, Optional, Dict, Any
import jedi
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QObject, QRect, QEvent
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPainter, QCursor
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QVBoxLayout
from PyQt5.QtWidgets import QMainWindow, QWidget, QApplication, QToolTip
from qfluentwidgets import TransparentToolButton, MessageBoxBase
from qtpy import QtCore
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from app.utils.utils import get_icon  # 确保路径正确

# 禁用jedi子进程，避免在GUI应用中出现子进程问题
jedi.settings.use_subprocess = False
# 限制jedi缓存大小，防止内存占用过高
jedi.settings.cache_directory = os.path.expanduser("~/.jedi_cache")
jedi.settings.call_signatures_validity = 300  # 缓存5分钟

# 线程池用于异步处理补全请求
completion_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="JediCompletion")

class CompletionItemDelegate(QStyledItemDelegate):
    """自定义补全项绘制器，解决重叠、颜色和间距问题"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # 定义类型颜色，模仿PyCharm风格
        self.type_colors = {
            'function': QColor("#FFB86C"),  # 橙色
            'method': QColor("#FFB86C"),  # 橙色
            'class': QColor("#82AAFF"),  # 蓝色
            'module': QColor("#B267E6"),  # 紫色
            'instance': QColor("#F07178"),  # 红色
            'keyword': QColor("#C792EA"),  # 紫色
            'property': QColor("#FFCB6B"),  # 黄色
            'param': QColor("#F78C6C"),  # 橙红色
            'variable': QColor("#E0E0E0"),  # 灰白色
            'custom': QColor("#89DDFF"),  # 青色
            'unknown': QColor("#CCCCCC"),  # 浅灰色
            'variable_str': QColor("#FFCB6B"),  # 黄色 (类似 property)
            'variable_int': QColor("#F78C6C"),  # 橙红色 (类似 param)
            'variable_float': QColor("#F78C6C"),
            'variable_list': QColor("#E0E0E0"),  # 灰白色 (类似 variable)
            'variable_dict': QColor("#E0E0E0"),
            'variable_bool': QColor("#FFB86C"),  # 橙色 (类似 function)
            'variable_tuple': QColor("#E0E0E0"),
            'variable_set': QColor("#E0E0E0"),
            # PyCharm 风格新增
            'builtin': QColor("#FFB86C"), # 内置函数/类型
            'enum': QColor("#82AAFF"), # 枚举
            'attribute': QColor("#E0E0E0"), # 类属性
        }
        # 定义类型字符（单个字母，简洁明了）
        self.type_chars = {
            'function': 'Ƒ',
            'method': 'ℳ',
            'class': '𝒞',
            'module': 'ℳ',
            'instance': 'ℐ',
            'keyword': '𝕂',
            'property': '𝒫',
            'param': '𝒫',
            'variable': '𝒱',
            'custom': '★',  # 自定义补全使用星号
            'variable_str': '𝒱',
            'variable_int': '𝒱',
            'variable_float': '𝒱',
            'variable_list': '𝒱',
            'variable_dict': '𝒱',
            'variable_bool': '𝒱',
            'variable_tuple': '𝒱',
            'variable_set': '𝒱',
            # PyCharm 风格新增
            'builtin': 'ℬ',
            'enum': 'ℰ',
            'attribute': '𝒜', # 类属性
        }
        # --- 新增：描述截断参数 ---
        self.max_description_length = 60  # 可以根据需要调整
        self.truncation_suffix = "..."  # 截断后缀
        # --- 新增：详情信息截断参数 ---
        self.max_detail_length = 40  # 用于显示函数签名等

    def _truncate_description(self, description: str) -> str:
        """截断描述文本"""
        if len(description) > self.max_description_length:
            return description[:self.max_description_length - len(self.truncation_suffix)] + self.truncation_suffix
        return description

    def _truncate_detail(self, detail: str) -> str:
        """截断详情文本 (如函数签名)"""
        if len(detail) > self.max_detail_length:
            return detail[:self.max_detail_length - len(self.truncation_suffix)] + self.truncation_suffix
        return detail

    def paint(self, painter: QPainter, option, index):
        """
        绘制补全项，确保只绘制一次，使用不同颜色区分类型
        """
        # 1. 绘制背景
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2A3B4D"))
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.fillRect(option.rect, QColor("#19232D"))
            painter.setPen(QColor("#FFFFFF"))

        # 2. 获取数据 (使用 UserRole 存储的完整信息)
        item_data = index.data(Qt.UserRole)
        if item_data:
            name, type_name, description, detail = item_data
            # --- 在绘制前截断描述和详情 ---
            description = self._truncate_description(description)
            detail = self._truncate_detail(detail) if detail else ""
        else:
            # 兼容旧数据格式
            name = index.data(Qt.DisplayRole) or index.data()
            type_name = ""
            description = ""
            detail = ""

        # 3. 计算区域
        padding = 10
        char_width = 20  # 字符宽度
        char_spacing = 10  # 字符和文字之间的间距
        rect = option.rect.adjusted(padding, 0, -padding, 0)

        # 类型字符区域
        char_rect = QRect(rect.left(), rect.top(), char_width, rect.height())

        # 名称区域（从字符右边开始）
        name_start_x = rect.left() + char_width + char_spacing
        name_rect = QRect(
            name_start_x,
            rect.top(),
            rect.width() - char_width - char_spacing - 10,  # 减去右边内边距
            rect.height()
        )

        # 4. 绘制类型字符（单个字母，使用类型颜色）
        type_char = self.type_chars.get(type_name, '?')
        type_color = self.type_colors.get(type_name, self.type_colors['unknown'])
        painter.setPen(type_color)
        char_font = painter.font()
        char_font.setPointSize(char_font.pointSize() + 1)  # 比主文字大1号
        char_font.setBold(True)  # 加粗显示
        painter.setFont(char_font)
        painter.drawText(
            char_rect,
            Qt.AlignCenter,  # 居中显示
            type_char
        )
        # 恢复原字体
        painter.setFont(option.font)

        # 5. 绘制主名称（白色）
        painter.setPen(QColor("#FFFFFF"))  # 使用白色绘制名称
        name_font = painter.font()
        name_font.setPointSize(name_font.pointSize() + 1)  # 稍大一点
        painter.setFont(name_font)

        # --- 修改：支持详情信息 (如函数签名) ---
        if (description or detail) and name_rect.width() > 150:
            # 计算描述和详情区域（右侧）
            desc_font = painter.font()
            desc_font.setPointSize(desc_font.pointSize() - 1)
            desc_font.setItalic(True)
            painter.setFont(desc_font)
            painter.setPen(QColor("#AAAAAA"))

            # 组合描述和详情，用分号分隔
            combined_info = ""
            if description:
                combined_info += description
            if detail:
                if combined_info:
                    combined_info += "; " # 分隔符
                combined_info += detail

            # 截断组合信息
            combined_info = self._truncate_detail(combined_info) # 复用detail的截断逻辑

            # 详情文本宽度
            fm = painter.fontMetrics()
            info_width = fm.width(combined_info)
            # 详情区域矩形
            info_rect = QRect(
                name_rect.right() - info_width - 5,  # 右侧留5px间距
                name_rect.top(),
                info_width,
                name_rect.height()
            )
            # 绘制详情和描述
            painter.drawText(
                info_rect,
                Qt.AlignRight | Qt.AlignVCenter,
                combined_info
            )
            # 绘制名称（左侧，不覆盖详情）
            name_only_rect = QRect(
                name_rect.left(),
                name_rect.top(),
                name_rect.width() - info_width - 15,  # 留出空间给详情和间距
                name_rect.height()
            )
            painter.setFont(name_font)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                name_only_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                name
            )
            # 恢复原字体
            painter.setFont(option.font)
        else:
            # 没有详情或描述，直接绘制名称
            painter.drawText(
                name_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                name
            )
            # 恢复原字体
            painter.setFont(option.font)

    def sizeHint(self, option, index):
        """返回补全项的推荐尺寸"""
        size = super().sizeHint(option, index)
        return QSize(size.width(), 40)  # 保持40px高度

class CompletionWorker(QObject):
    """异步补全工作线程"""
    completion_ready = pyqtSignal(list)  # 发送补全结果
    error_occurred = pyqtSignal(str)  # 发送错误信息
    # 新增信号：用于发送延迟补全请求的结果
    delayed_completion_ready = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.running = True

    def _find_identifier_at_position(self, code: str, line: int, column: int) -> str:
        """
        根据行号和列号找到代码中的标识符。
        例如，在 "self.name" 中，如果光标在 'na' 上，返回 "name"。
        """
        lines = code.split('\n')
        if not (0 <= line - 1 < len(lines)):
            return ""
        line_text = lines[line - 1]
        # 从光标位置向左找到标识符的开始
        start = column - 1  # column 是1-based, 转为0-based
        while start >= 0 and (line_text[start].isalnum() or line_text[start] == '_'):
            start -= 1
        start += 1  # 回到标识符的第一个字符
        # 从光标位置向右找到标识符的结束
        end = column - 1
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] == '_'):
            end += 1
        if start < end:
            return line_text[start:end]
        return ""

    def _guess_type_from_code(self, code: str, line: int, column: int, name: str) -> str:
        """
        尝试从代码中直接推断变量类型
        这是一个简单的启发式方法，适用于简单的赋值语句
        """
        # 首先，尝试找到光标位置的标识符，确保它与 Jedi 返回的 name 匹配
        identifier_at_cursor = self._find_identifier_at_position(code, line, column)
        # print(f"Debug: Jedi name: '{name}', Identifier at cursor: '{identifier_at_cursor}'") # 调试用
        if identifier_at_cursor != name:
            # 如果 Jedi 返回的 name 与光标位置的标识符不匹配（例如 'self.name' vs 'name'），
            # 我们仍然可以尝试查找 name (即 'name') 的定义
            # 但更准确的做法是只对直接匹配的变量名进行代码推断
            # 这里我们继续尝试查找 name
            pass

        try:
            lines = code.split('\n')
            # 从当前行向上搜索，寻找赋值语句
            # 例如，对于 self.name，我们查找 name = ...
            search_line = line - 2  # 从当前行的上一行开始
            # 增加向上搜索的范围
            max_search_lines = 50 # 可配置
            start_search_line = max(0, search_line - max_search_lines)
            while search_line >= start_search_line:
                line_text = lines[search_line].strip()
                # 更精确的匹配，避免注释和字符串
                if '=' in line_text and not line_text.strip().startswith('#'):
                    # 使用正则表达式进行更精确的赋值匹配
                    # 匹配 "name = value" 或 "obj.name = value"
                    assignment_pattern = rf'(\b{re.escape(name)}\b|\.+\s*\.\s*\b{re.escape(name)}\b)\s*='
                    match = re.search(assignment_pattern, line_text)
                    if match:
                        # print(f"Debug: Found assignment for '{name}': {line_text}") # 调试用
                        # 提取等号右边的部分
                        parts = line_text.split('=', 1)
                        if len(parts) == 2:
                            right_part = parts[1].strip()
                            # 简单的类型推断
                            if right_part.startswith(('"', "'")):
                                return 'variable_str'
                            elif re.match(r'^-?\d+$', right_part): # 匹配整数（包括负数）
                                return 'variable_int'
                            elif re.match(r'^-?\d*\.\d+$', right_part): # 匹配浮点数（包括负数）
                                return 'variable_float'
                            elif right_part.startswith('[') and right_part.endswith(']'):
                                return 'variable_list'
                            elif right_part.startswith('{') and right_part.endswith('}') and ':' in right_part:
                                return 'variable_dict'
                            elif right_part.lower() in ['true', 'false']:
                                return 'variable_bool'
                            elif right_part.startswith('(') and right_part.endswith(')'):
                                return 'variable_tuple'
                            elif right_part.startswith('{') and right_part.endswith('}') and ':' not in right_part:
                                return 'variable_set'
                            else:
                                # 尝试推断是否为类实例
                                # 查找右侧是否包含函数调用 (...)
                                call_match = re.search(r'(\w+)\s*\(', right_part)
                                if call_match:
                                     potential_class_name = call_match.group(1)
                                     # 这里可以尝试检查 potential_class_name 是否在代码中被定义为 class
                                     # 但这需要更复杂的解析，暂时假设是 instance
                                     return 'instance'
                                return 'variable'  # 通用变量类型
                search_line -= 1
        except Exception as e:
            print(f"[Jedi] Error during type guess from code for '{name}': {e}")
            pass
        return None

    def _parse_jedi_completion(self, comp) -> Tuple[str, str, str, str]:
        """解析 jedi 的 completion 对象，提取类型、描述、详情和更精确的类型信息"""
        name = comp.name
        # 1. 获取原始类型
        original_type_name = getattr(comp, 'type', 'unknown')
        description = getattr(comp, 'description', '')
        # 2. 获取详情 (params, full_name, etc.)
        detail = getattr(comp, 'params', '') or getattr(comp, 'full_name', '') or getattr(comp, 'string_name', '')
        # 3. 尝试从 jedi 结果中推断更精确的类型
        refined_type_name = original_type_name
        if original_type_name == 'unknown':
            # 检查 jedi 的详细信息
            # full_name 通常包含模块和类路径，如 <inline>.Component.inputs
            full_name = getattr(comp, 'full_name', '')
            if full_name:
                if '.<locals>.' in full_name:
                    # 局部变量或函数
                    refined_type_name = 'variable'
                elif full_name.startswith('<inline>.'):
                    # 内联代码中的定义，可能是类属性
                    if '.' in full_name.split('<inline>.', 1)[1]:
                        refined_type_name = 'attribute' # 类属性或方法
                    else:
                        refined_type_name = 'variable' # 模块级变量
                elif full_name.startswith('__builtin__') or full_name.startswith('builtins.'):
                    refined_type_name = 'builtin'
                elif full_name.startswith('typing.'):
                    refined_type_name = 'builtin' # typing 模块中的类型
                elif full_name.startswith('enum.'):
                    refined_type_name = 'enum'
                else:
                    # 尝试从 full_name 猜测类型
                    last_part = full_name.split('.')[-1]
                    if last_part[0].isupper(): # 首字母大写，可能是类
                        refined_type_name = 'class'
                    elif '(' in description: # 描述中包含括号，可能是函数
                        refined_type_name = 'function'
                    else:
                        refined_type_name = 'instance' # 默认为实例
            # 4. 检查 definition 对象 (如果可用)
            try:
                definitions = comp.defined_names
                if definitions:
                    def_type = definitions[0].type
                    if def_type in ['class', 'function', 'module', 'instance']:
                        refined_type_name = def_type
            except AttributeError:
                pass # 如果没有 defined_names 属性，忽略

        # 5. 检查 string_name (jedi 0.19+)
        string_name = getattr(comp, 'string_name', '')
        if refined_type_name == 'unknown' and string_name:
            if string_name in ['function', 'method', 'class', 'module', 'instance', 'keyword', 'property', 'param']:
                refined_type_name = string_name
            elif string_name == 'builtin':
                refined_type_name = 'builtin'

        # 6. 检查 docstring 或其他属性 (可选，增加复杂度)
        # 例如，如果 docstring 包含 "class" 或 "Class"，可以推断为 class

        return name, refined_type_name, description, detail


    def request_completions(self, code: str, line: int, column: int,
                            site_packages_path: Optional[str] = None):
        """请求补全"""
        if not self.running:
            return
        try:
            start_time = time.time()
            # --- 修改：在创建 Script 对象前临时修改 sys.path ---
            added_to_path = False
            original_path = list(sys.path) if site_packages_path else None # 保存原始路径
            if site_packages_path and site_packages_path not in sys.path:
                sys.path.insert(0, site_packages_path)
                added_to_path = True
                print(f"[Jedi] Added {site_packages_path} to sys.path temporarily.")
            with open(r"D:\work\CanvasMind\app\components\base.py", "r", encoding="utf-8") as f:
                base_code = f.read()
            # 创建 Script 对象
            script = jedi.Script(code=code + base_code, path='<inline>')

            # 获取补全结果
            jedi_comps = script.complete(line=line, column=column)
            completions = []
            seen = set()
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or name in seen:
                    continue
                seen.add(name)
                # --- 使用新的解析方法 ---
                name, type_name, description, detail = self._parse_jedi_completion(comp)
                # --- 新增：尝试从代码中推断类型 (作为后备) ---
                if type_name in ['instance', 'statement', 'unknown']:
                    precise_type = self._guess_type_from_code(code, line, column, name)
                    if precise_type:
                        type_name = precise_type
                        print(f"Debug: Guessed type for '{name}' as '{type_name}' from code.")
                completions.append((name, type_name, description, detail))
                if len(completions) >= 100:
                    break

            # --- 修改：在获取结果后立即恢复 sys.path (如果需要) ---
            if added_to_path and original_path is not None:
                sys.path[:] = original_path  # 恢复原始路径
                print(f"[Jedi] Restored original sys.path.")

            elapsed = time.time() - start_time
            print(f"[Jedi] Completion took {elapsed:.3f}s for {len(completions)} items")
            self.completion_ready.emit(completions)
        except Exception as e:
            # 确保在出错时也恢复路径
            if added_to_path and original_path is not None:
                sys.path[:] = original_path
                print(f"[Jedi] Restored original sys.path after error.")
            print(f"[Jedi] Error during completion: {e}")
            self.error_occurred.emit(str(e))

    def request_delayed_completion(self, code: str, line: int, column: int, site_packages_path: Optional[str] = None):
        """处理延迟的补全请求 (对应原来的 _on_completions_ready_callback)"""
        try:
            # --- 修改：在创建 Script 对象前临时修改 sys.path ---
            added_to_path = False
            original_path = list(sys.path) if site_packages_path else None # 保存原始路径
            if site_packages_path and site_packages_path not in sys.path:
                sys.path.insert(0, site_packages_path)
                added_to_path = True
                print(f"[Jedi] Added {site_packages_path} to sys.path temporarily (delayed).")

            # 创建 Script 对象
            script = jedi.Script(code=code, path='<inline>')

            # 获取补全结果
            jedi_comps = script.complete(line=line, column=column)
            completions = []
            seen = set()
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or name in seen:
                    continue
                seen.add(name)
                # --- 使用新的解析方法 ---
                name, type_name, description, detail = self._parse_jedi_completion(comp)
                # --- 新增：尝试从代码中推断类型 (作为后备) ---
                if type_name in ['instance', 'statement', 'unknown']:
                    precise_type = self._guess_type_from_code(code, line, column, name)
                    if precise_type:
                        type_name = precise_type
                completions.append((name, type_name, description, detail))
                if len(completions) >= 100:
                    break

            # --- 修改：在获取结果后立即恢复 sys.path (如果需要) ---
            if added_to_path and original_path is not None:
                sys.path[:] = original_path  # 恢复原始路径

            # 发射信号到 GUI 线程
            self.delayed_completion_ready.emit(completions)
        except Exception as e:
            # 确保在出错时也恢复路径
            if added_to_path and original_path is not None:
                sys.path[:] = original_path
                print(f"[Jedi] Restored original sys.path after error in delayed request.")
            import traceback
            print(f"[Jedi] Error in delayed completion task: {traceback.format_exc()}")
            self.error_occurred.emit(f"Delayed completion error: {e}")

class JediCodeEditor(CodeEditor):
    """增强的代码编辑器，支持Jedi补全"""
    def __init__(self, parent=None, code_parent=None, python_exe_path=None, popup_offset=2, dialog=None):
        super().__init__()
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self.parent = code_parent
        self._jedi_environment = None
        self.custom_completions = set()
        self.add_custom_completions([
            'global_variable', 'Exception',  # 内置常量
            'True', 'False', 'None',
            # 内置异常
            'Exception', 'ValueError', 'TypeError', 'RuntimeError',
            'KeyError', 'IndexError', 'AttributeError', 'ImportError',
            'OSError', 'FileNotFoundError', 'PermissionError',
            # 常用内置函数（作为变量名也可能出现）
            'float', 'list', 'dict', 'tuple',
            'print', 'input', 'open', 'range', 'enumerate',
            'sorted', 'reversed', 'filter', 'enumerate',
            'type', 'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr', 'delattr', 'vars',
            'locals', 'eval', 'exec', 'repr', 'complex', 'round', 'strip', 'split', 'join', 'replace', 'lower',
            # 常见日志/调试变量
            'logger', 'debug', 'info', 'warning', 'error',
            # 常见 self 属性（提示用户可能想输入的）
            'self', '__init__', '__name__', '__main__', '__file__', '__package__', '__doc__', '__version__',
        ])
        # --- 新增：使用时间衰减的补全使用记录 ---
        self.completion_usage = {} # 使用普通字典存储 (name, last_used_time, count)
        self.max_usage_records = 500
        self.usage_decay_factor = 0.9 # 每次更新时衰减旧计数
        self.usage_decay_interval = 60 * 5 # 5分钟衰减一次

        self.max_completions = 80
        self._completing = False
        self.dialog = dialog
        # --- 保留原来的 site-packages 逻辑 ---
        self.set_jedi_environment(str(python_exe_path) if python_exe_path else None)

        # --- 高性能补全相关 ---
        self.completion_worker = CompletionWorker()
        self.completion_future: Optional[Future] = None
        self.pending_completion_request = None
        self._input_delay_timer = QTimer()
        self._input_delay_timer.setSingleShot(True)
        self._input_delay_timer.timeout.connect(self._on_input_delay_timeout)
        self._input_delay_ms = 20  # 进一步降低延迟，提高响应速度

        # --- 补全弹窗 ---
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.popup.setFocusPolicy(Qt.NoFocus)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.popup.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 自定义滚动条样式
        self.popup.setStyleSheet("""
            QListWidget {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
            }
            QScrollBar:vertical {
                width: 8px;
                background-color: #2A3B4D;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #32414B;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4A5C6D;
            }
        """)
        popup_font = QFont('Consolas', 12)  # 增大字体
        self.popup.setFont(popup_font)
        self.popup.setItemDelegate(CompletionItemDelegate())
        self.popup.itemClicked.connect(self._on_completion_selected)
        self.popup.itemEntered.connect(self._on_item_hovered) # 用于显示docstring
        self.popup.setUniformItemSizes(True)
        self.popup.setMaximumWidth(1200)
        self.popup.setMinimumWidth(500)
        self.popup.hide()

        # --- 补全框自动关闭定时器 ---
        self._popup_timeout_timer = QTimer()
        self._popup_timeout_timer.setSingleShot(True)
        self._popup_timeout_timer.timeout.connect(self._on_popup_timeout)
        self._popup_timeout_duration = 10000  # 10秒后自动关闭

        # --- 设置编辑器 ---
        self._font_family = 'Consolas'
        self._current_font_size = 13
        font = QFont('Consolas', 13)
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=font,
            show_blanks=False,
            edge_line=True,
            auto_unindent=True,
            close_quotes=True,
            indent_guides=True,
            folding=True,
            intelligent_backspace=True,
            automatic_completions=False,
            completions_hint=True,
            highlight_current_line=True,
        )

        # --- 快捷键 ---
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self._request_completions)

        # --- 定时器 ---
        self._auto_complete_timer = QTimer()
        self._auto_complete_timer.setSingleShot(True)
        self._auto_complete_timer.timeout.connect(self._trigger_auto_completion)

        # --- 添加放大按钮 ---
        self._create_fullscreen_button("放大" if dialog is None else "缩小")

        # --- 连接补全工作线程信号 ---
        self.completion_worker.completion_ready.connect(self._on_completions_ready)
        self.completion_worker.error_occurred.connect(self._on_completion_error)
        # 连接新增的延迟补全信号
        self.completion_worker.delayed_completion_ready.connect(self._on_delayed_completions_ready)

        # --- 定义类型字符字典 ---
        self.type_chars = {
            'function': 'Ƒ',
            'method': 'ℳ',
            'class': '𝒞',
            'module': 'ℳ',
            'instance': 'ℐ',
            'keyword': '𝕂',
            'property': '𝒫',
            'param': '𝒫',
            'variable': '𝒱',
            'custom': '★',
            'variable_str': '𝒱',
            'variable_int': '𝒱',
            'variable_float': '𝒱',
            'variable_list': '𝒱',
            'variable_dict': '𝒱',
            'variable_bool': '𝒱',
            'variable_tuple': '𝒱',
            'variable_set': '𝒱',
            # PyCharm 风格新增
            'builtin': 'ℬ',
            'enum': 'ℰ',
            'attribute': '𝒜', # 类属性
        }

        # --- 新增：用于记录上次衰减时间 ---
        self._last_decay_time = time.time()

    def _create_fullscreen_button(self, type="放大"):
        """创建全屏按钮"""
        self.fullscreen_button = TransparentToolButton(get_icon(type), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")
        if type == "放大":
            self.fullscreen_button.clicked.connect(self._open_fullscreen_editor)
        else:
            self.fullscreen_button.clicked.connect(self.dialog.accept)
        self._update_button_position()

    def resizeEvent(self, event):
        """重写调整大小事件以更新按钮位置"""
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        """更新按钮位置到右上角"""
        button_width = self.fullscreen_button.width()
        button_height = self.fullscreen_button.height()
        x = self.width() - button_width - 30
        y = 6
        self.fullscreen_button.move(x, y)

    def _open_fullscreen_editor(self):
        """打开全屏编辑器"""
        current_code = self.toPlainText()
        dialog = FullscreenCodeDialog(initial_code=current_code, parent=self.parent_widget, code_parent=self.parent)
        if dialog.exec_() == 1:
            new_code = dialog.get_code()
            self.setPlainText(new_code)

    def wheelEvent(self, event):
        """处理鼠标滚轮事件以缩放字体"""
        if event.modifiers() == Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._increase_font_size()
            else:
                self._decrease_font_size()
            event.accept()
        else:
            super().wheelEvent(event)

    def _increase_font_size(self):
        """增加字体大小"""
        if self._current_font_size < 30:
            self._current_font_size += 1
            self._apply_font()

    def _decrease_font_size(self):
        """减少字体大小"""
        if self._current_font_size > 8:
            self._current_font_size -= 1
            self._apply_font()

    def _apply_font(self):
        """应用当前字体设置"""
        font = QFont(self._font_family, self._current_font_size)
        self.set_font(font)

    def set_jedi_environment(self, python_exe_path):
        """设置Jedi环境 (仅用于获取site-packages路径)"""
        if python_exe_path and os.path.exists(python_exe_path):
            python_dir = os.path.dirname(os.path.abspath(python_exe_path))
            site_packages = os.path.join(python_dir, "Lib", "site-packages")
            if os.path.isdir(site_packages):
                self._target_site_packages = site_packages
                print(f"[Jedi] Target site-packages: {site_packages}")
            else:
                self._target_site_packages = None
                print(f"[Jedi] Warning: site-packages not found at {site_packages}")
        else:
            # 如果没有提供exe路径，尝试使用当前Python环境的site-packages
            import site
            if site.getsitepackages():
                self._target_site_packages = site.getsitepackages()[0]
                print(f"[Jedi] Using current Python's site-packages: {self._target_site_packages}")
            else:
                self._target_site_packages = None
                print(f"[Jedi] Warning: Could not determine site-packages path")

    def add_custom_completions(self, words):
        """添加自定义补全"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def _decay_usage_counts(self):
        """定期衰减补全使用计数"""
        current_time = time.time()
        if current_time - self._last_decay_time > self.usage_decay_interval:
            print(f"[Usage] Decaying usage counts.")
            for name in list(self.completion_usage.keys()):
                last_time, count = self.completion_usage[name]
                # 计算时间衰减因子 (基于上次使用时间)
                time_factor = 1.0 # 基础因子
                # 简单的线性衰减，可根据需要调整公式
                if current_time - last_time > self.usage_decay_interval * 2:
                    time_factor *= 0.5
                # 应用计数衰减
                new_count = int(count * self.usage_decay_factor * time_factor)
                if new_count <= 0:
                    del self.completion_usage[name]
                else:
                    self.completion_usage[name] = (last_time, new_count)
            self._last_decay_time = current_time

    def _get_class_attributes_from_code(self, code: str, class_name: str) -> List[str]:
        """从代码中提取类的属性"""
        # 这是一个简化的实现，可以使用 AST 解析来更精确地实现
        lines = code.split('\n')
        attributes = set()
        in_class = False
        current_class = ""
        for line in lines:
            if line.strip().startswith('class '):
                parts = line.strip().split(' ', 1)
                if len(parts) > 1:
                    cls_name = parts[1].split('(')[0].strip(':')
                    if cls_name == class_name:
                        in_class = True
                        current_class = cls_name
                    else:
                        in_class = False
            elif in_class and line.strip().startswith('def '):
                # 遇到方法定义，通常属性定义在 __init__ 或其他方法之前
                continue
            elif in_class and 'self.' in line:
                # 查找 self.attribute = ...
                match = re.search(r'self\.(\w+)', line)
                if match:
                    attr_name = match.group(1)
                    if not attr_name.startswith('_'): # 排除私有属性
                        attributes.add(attr_name)
        return list(attributes)

    def _is_inside_type_annotation(self, text: str, pos: int) -> bool:
        """检查光标是否在类型注解中"""
        # 简单检查：光标前是否有冒号且后面有等号或换行（var: type = ...）或在函数定义中 (def func(param: type))
        before_cursor = text[:pos]
        after_cursor = text[pos:]
        # 检查是否在函数参数类型注解中 (def func(param: ...)
        func_def_pattern = r'def\s+\w+\s*\([^)]*'
        last_func_start = before_cursor.rfind('def ')
        if last_func_start != -1:
            func_line = before_cursor[last_func_start:]
            if ':' in func_line and '(' in func_line and ')' not in func_line or ')' in after_cursor:
                # 在 def ( ... : ... ) 结构中
                colon_pos_in_func = func_line.rfind(':')
                if colon_pos_in_func != -1:
                    # 检查光标是否在最后一个冒号之后
                    if len(before_cursor) - len(func_line) + colon_pos_in_func < pos:
                        return True
        # 检查是否在变量类型注解中 (var: ...)
        var_ann_pattern = r'\w+\s*:\s*[^=\n]*'
        last_var_start = max(before_cursor.rfind('\n'), 0)
        var_line = before_cursor[last_var_start:].strip()
        if ':' in var_line and '=' not in var_line or var_line.split('=')[0].count(':') > var_line.split('=')[0].count('('):
             # 粗略判断，更精确的需要AST
             if var_line.endswith(':'):
                 return True
        return False

    def _is_inside_function_call(self, text: str, pos: int) -> bool:
        """检查光标是否在函数调用内部"""
        before_cursor = text[:pos]
        after_cursor = text[pos:]

        # 简单的检查：查找未匹配的括号
        open_parens = before_cursor.count('(') - before_cursor.count(')')
        if open_parens > 0:
            # 检查光标后是否有 ')'
            if ')' in after_cursor:
                return True
        return False

    def _is_contextual_completion(self, text: str, pos: int) -> Tuple[bool, str]:
        """检查上下文补全类型"""
        before_cursor = text[:pos].lower()
        after_cursor = text[pos:].lower()
        current_line = self.textCursor().block().text()[:self.textCursor().columnNumber()]

        # 检查 'from ... import ...'
        if re.search(r'from\s+[\w.]+\s+import\s+', before_cursor):
            return True, 'from_import'

        # 检查 'import ...'
        if before_cursor.endswith('import '):
            return True, 'import'

        # 检查 'except ... :'
        if current_line.strip().startswith('except ') and ':' in current_line:
            return True, 'except'

        # 检查 'with ... :'
        if current_line.strip().startswith('with ') and ':' in current_line:
            return True, 'with'

        # 检查 'for ... in ... :'
        if 'for ' in current_line and ' in ' in current_line and ':' in current_line:
             in_pos = current_line.find(' in ')
             colon_pos = current_line.find(':')
             cursor_pos_in_line = self.textCursor().columnNumber()
             if in_pos < cursor_pos_in_line < colon_pos:
                 return True, 'for_in'

        # 检查类型注解
        if self._is_inside_type_annotation(text, pos):
            return True, 'type_annotation'

        # 检查函数参数 (逗号分隔)
        if self._is_inside_function_call(text, pos):
            # 粗略判断是否在逗号后
            last_comma_before = before_cursor.rfind(',')
            last_open_paren_before = before_cursor.rfind('(')
            if last_comma_before != -1 and last_open_paren_before != -1 and last_comma_before > last_open_paren_before:
                return True, 'function_param'

        return False, ''

    def eventFilter(self, obj, event):
        """事件过滤器，用于处理点击补全框外部关闭补全框"""
        if obj == self.popup and event.type() == QEvent.MouseButtonPress:
            # 如果点击发生在补全框外部，则隐藏补全框
            # 这里使用全局鼠标位置与补全框边界比较
            global_mouse_pos = QCursor.pos()
            popup_rect = self.popup.geometry()
            if not popup_rect.contains(global_mouse_pos):
                print(f"[Jedi] Clicked outside popup, hiding.")
                self.popup.hide()
                self._popup_timeout_timer.stop()
                return True # 拦截事件
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """处理按键事件"""
        modifiers = event.modifiers()
        key = event.key()

        # 处理Shift+Enter (修正：调用自身的方法)
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            # 直接调用集成在类内的方法
            self._handle_shift_enter(cursor)
            event.accept() # 确保事件被处理
            return # 直接返回，不执行后续逻辑

        # 处理补全弹窗导航
        if self.popup.isVisible():
            if key == Qt.Key_Escape:
                self.popup.hide()
                self._popup_timeout_timer.stop()  # 停止超时计时器
                event.accept()
                return
            elif key == Qt.Key_Tab:
                # 检查是否有选中项，如果有则应用，否则执行默认Tab行为
                if self.popup.currentItem():
                    self._apply_selected_completion()
                    event.accept()
                    return
                else:
                    # No item selected, let super handle Tab for indentation
                    super().keyPressEvent(event)
                    return
            elif key == Qt.Key_Return: # PyCharm 风格：回车确认
                if self.popup.currentItem():
                    self._apply_selected_completion()
                    event.accept()
                    return
                else:
                    # No item selected, let super handle Enter
                    super().keyPressEvent(event)
                    return
            elif key == Qt.Key_Up:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(max(0, current - 1))
                event.accept()
                return
            elif key == Qt.Key_Down:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(min(self.popup.count() - 1, current + 1))
                event.accept()
                return

        # 隐藏弹窗
        if event.text() in '()[]{}.,;:!? ' and self.popup.isVisible():
            self.popup.hide()
            self._popup_timeout_timer.stop()  # 停止超时计时器

        # 处理Enter/Return的缩进逻辑 (只处理普通回车，不处理Shift+Enter)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            cursor_pos = cursor.positionInBlock()
            line_before_cursor = text[:cursor_pos]
            line_after_cursor = text[cursor_pos:]
            open_count = line_before_cursor.count('[') + line_before_cursor.count('(') + line_before_cursor.count('{')
            close_count = line_before_cursor.count(']') + line_before_cursor.count(')') + line_before_cursor.count('}')
            if open_count > close_count:
                leading_spaces = len(text) - len(text.lstrip())
                new_indent = ' ' * (leading_spaces + 4)
                cursor.insertText('\n' + new_indent)
                if line_after_cursor.strip().startswith(']') or line_after_cursor.strip().startswith(
                        ')') or line_after_cursor.strip().startswith('}'):
                    cursor.insertText('\n' + ' ' * leading_spaces)
                    cursor.movePosition(QTextCursor.PreviousBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock)
                    self.setTextCursor(cursor)
                event.accept()
                return

        # 记录光标位置和文本状态，以便在删除时也能触发补全
        cursor = self.textCursor()
        old_pos = cursor.position()
        old_text = self.toPlainText()
        # 执行默认的 keyPressEvent
        super().keyPressEvent(event)

        # 判断是否为删除操作（Backspace 或 Delete）
        is_delete = (key == Qt.Key_Backspace) or (key == Qt.Key_Delete)
        # 根据输入内容决定是否触发补全
        text = event.text()
        should_trigger = False
        # 增加更多触发条件，模仿PyCharm
        if text == '.':
            should_trigger = True
        elif text == ' ' and old_text.endswith('import '):  # import 后
            should_trigger = True
        elif text == ' ' and old_text.endswith('from '):  # from 后
            should_trigger = True
        elif text == ' ' and (old_text.endswith('def ') or old_text.endswith('class ')): # def/class 后
            should_trigger = True
        elif ',' in text and self._is_inside_function_call(old_text, old_pos): # 参数分隔符后
             should_trigger = True
        elif text.isalnum() or text == '_':
            prefix = self._get_completion_prefix()
            if len(prefix) >= 1:  # 更灵敏
                should_trigger = True
        elif is_delete:  # 删除操作
            # 在删除后，检查是否应该显示补全
            if self._should_show_completion_on_delete():
                should_trigger = True

        if should_trigger:
            self._input_delay_timer.start(self._input_delay_ms)
            # 如果触发了补全，重新启动超时计时器
            if self.popup.isVisible():
                self._popup_timeout_timer.start(self._popup_timeout_duration)

    # --- 新增：集成的 Shift+Enter 处理方法 ---
    def _handle_shift_enter(self, cursor):
        """处理 Shift+Enter 事件，在当前行末尾换行并保持缩进"""
        cursor.movePosition(QTextCursor.EndOfLine)
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        cursor.insertText('\n' + indent)
        self.setTextCursor(cursor)  # 注意：这里使用 self 而不是 self.code_editor

    def _should_show_completion_on_delete(self) -> bool:
        """判断删除字符时是否应该显示补全"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        # 如果光标在开头，可能不需要补全
        if pos <= 0:
            return False
        # 检查光标前一个字符是否是字母、数字或下划线（即还在标识符内）
        prev_char = text[pos - 1] if pos > 0 else ''
        if prev_char.isalnum() or prev_char == '_':
            return True
        # 如果光标在点号前，也需要补全
        if pos > 0 and text[pos - 1] == '.':
            return True
        return False

    def _on_input_delay_timeout(self):
        """输入延迟超时回调"""
        self._request_completions()

    def _trigger_auto_completion(self):
        """触发自动补全"""
        self._request_completions()

    def _request_completions(self):
        """请求补全"""
        if self._completing:
            return
        if self.completion_future and not self.completion_future.done():
            cursor = self.textCursor()
            text = self.toPlainText()
            line = cursor.blockNumber() + 1
            column = cursor.columnNumber()
            # 传递 _target_site_packages
            self.pending_completion_request = (text, line, column, self._target_site_packages)
            return

        cursor = self.textCursor()
        text = self.toPlainText()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber()
        # 传递 _target_site_packages
        self.completion_future = completion_pool.submit(
            self.completion_worker.request_completions,
            text, line, column, self._target_site_packages
        )

    def _on_completions_ready(self, completions: List[Tuple[str, str, str, str]]): # 增加 detail 参数
        """收到补全结果"""
        if self.pending_completion_request:
            text, line, column, env = self.pending_completion_request
            self.pending_completion_request = None
            # 调用 CompletionWorker 的新方法处理延迟请求
            self.completion_worker.request_delayed_completion(text, line, column, self._target_site_packages)
            return

        current_prefix = self._get_completion_prefix()
        self._filter_and_show_completions(completions, current_prefix)

    def _on_delayed_completions_ready(self, completions: List[Tuple[str, str, str, str]]): # 增加 detail 参数
        """处理延迟补全请求的结果"""
        current_prefix = self._get_completion_prefix()
        self._filter_and_show_completions(completions, current_prefix)

    def _get_completion_prefix_from_text(self, text: str, line: int, column: int):
        """从指定文本位置获取补全前缀"""
        lines = text.split('\n')
        if 0 <= line - 1 < len(lines):
            line_text = lines[line - 1]
            start = column
            while start > 0:
                ch = line_text[start - 1]
                if ch.isalnum() or ch == '_':
                    start -= 1
                else:
                    break
            return line_text[start:column]
        return ""

    def _filter_and_show_completions(self, completions: List[Tuple[str, str, str, str]], current_prefix: str): # 增加 detail 参数
        """过滤并显示补全项"""
        seen = {name for name, _, _, _ in completions} # 修改：解包detail
        for word in self.custom_completions:
            if word.lower().startswith(current_prefix.lower()) and word not in seen and len(word) >= 2:
                completions.append((word, 'custom', '', '')) # 修改：添加空的detail
                seen.add(word)

        if not completions:
            self.popup.hide()
            self._popup_timeout_timer.stop()  # 停止超时计时器
            return

        # --- 优化排序算法 ---
        def sort_key(item):
            name, type_name, description, detail = item # 修改：解包detail
            # 1. 完全匹配权重 (最高)
            is_exact_match = -1 if name.lower() == current_prefix.lower() else 0
            # 2. 前缀匹配权重 (次高)
            starts_with_prefix = -1 if name.lower().startswith(current_prefix.lower()) else 0
            # 3. 使用频率权重 (带时间衰减)
            self._decay_usage_counts() # 衰减计数
            usage_time, usage_count = self.completion_usage.get(name, (0, 0))
            # 计算基于时间和频率的分数
            time_factor = 1.0
            current_time = time.time()
            if current_time - usage_time < 60: # 1分钟内
                time_factor = 2.0
            elif current_time - usage_time < 300: # 5分钟内
                time_factor = 1.5
            # 综合分数
            usage_score = usage_count * time_factor

            # 4. 上下文感知权重 (新增)
            context_score = 0
            cursor = self.textCursor()
            text = self.toPlainText()
            pos = cursor.position()
            current_line = cursor.block().text()
            current_pos_in_line = cursor.columnNumber()

            # 检查上下文类型
            is_contextual, context_type = self._is_contextual_completion(text, pos)
            if is_contextual:
                if context_type == 'type_annotation':
                    if type_name in ['class', 'builtin']:
                        context_score += 1000
                elif context_type == 'from_import':
                    if type_name == 'module':
                        context_score += 1000
                elif context_type == 'except':
                    if 'exception' in description.lower() or type_name == 'class':
                        context_score += 980
                elif context_type == 'with':
                    # 优先显示上下文管理器，可能需要更复杂的判断
                    context_score += 960
                elif context_type == 'for_in':
                    # 优先显示可迭代对象
                    if type_name in ['variable', 'instance', 'builtin'] and ('list' in description.lower() or 'dict' in description.lower() or 'iter' in description.lower()):
                        context_score += 920
                elif context_type == 'function_param':
                    # 在函数参数中，优先显示参数名或相关类型
                    context_score += 850

            # 检查是否在 'self.' 或 'cls.' 后
            if pos >= 5:  # 确保有足够字符
                before_cursor = text[max(0, pos - 5):pos].lower()
                if before_cursor.endswith('self.') or before_cursor.endswith('cls.'):
                    # 在 'self.' 或 'cls.' 后，优先显示属性和方法
                    if type_name in ['property', 'method', 'attribute', 'instance']:
                        context_score += 1000
                    # 尝试分析当前类的属性 (需要解析代码)
                    # ... (可以添加更复杂的类分析逻辑) ...

            # 检查是否在 'import ' 后
            if pos >= 7:
                before_cursor = text[max(0, pos - 7):pos].lower()
                if before_cursor.endswith('import '):
                    # 在 'import ' 后，优先显示模块
                    if type_name == 'module':
                        context_score += 1000

            # 检查是否在 if/elif/while 后
            if current_line.strip().endswith(('if ', 'elif ', 'while ')):
                if type_name == 'variable' and 'bool' in description.lower(): # 简单判断
                    context_score += 950

            # 检查是否在参数类型注解中 (def func(param: ...) 或 var: ...)
            # 这个逻辑比较复杂，这里只做简单示例
            if self._is_inside_type_annotation(text, pos):
                # 可能是类型注解，优先显示类名
                if type_name == 'class':
                    context_score += 800

            # 5. 类型权重 (新增)
            type_priority = {
                'keyword': 900,  # 关键字优先级高
                'function': 700,  # 函数
                'method': 650,  # 方法
                'class': 600,  # 类
                'attribute': 550, # 类属性 (比普通变量高)
                'variable': 500,  # 变量
                'variable_str': 500,
                'variable_int': 500,
                'variable_float': 500,
                'variable_list': 500,
                'variable_dict': 500,
                'variable_bool': 500,
                'variable_tuple': 500,
                'variable_set': 500,
                'property': 450,  # 属性
                'param': 400,  # 参数
                'instance': 350,  # 实例
                'module': 300,  # 模块
                'custom': 250,  # 自定义
                'builtin': 750, # 内置函数/类型
                'enum': 620, # 枚举
                'unknown': 100,  # 未知
            }
            type_score = type_priority.get(type_name, 0)

            # 6. 名称长度权重 (较短的名称可能更常用，但低于前缀匹配)
            length_score = len(name)

            # 综合评分
            # 顺序：完全匹配 > 前缀匹配 > 上下文/类型 > 使用频率 > 长度 > 字母顺序
            return (
                is_exact_match,        # 完全匹配优先
                starts_with_prefix,    # 然后是前缀匹配
                -(context_score + type_score), # 上下文和类型
                -usage_score,          # 使用频率 (带时间衰减)
                length_score,          # 长度
                name.lower()           # 字母顺序
            )

        completions.sort(key=sort_key)
        completions = completions[:self.max_completions]

        self.popup.clear()
        for name, type_name, description, detail in completions: # 修改：解包detail
            item = QListWidgetItem(name)
            # 包含更多信息 (name, type_name, description, detail)
            item.setData(Qt.UserRole, (name, type_name, description, detail))
            item.setData(Qt.DisplayRole, name)  # 确保兼容性
            self.popup.addItem(item)

        if self.popup.count() > 0:
            self._show_popup()
            self.popup.setCurrentRow(0)
            # --- 安装事件过滤器 ---
            self.popup.installEventFilter(self)
            # 显示补全框后，启动超时计时器
            self._popup_timeout_timer.start(self._popup_timeout_duration)
        else:
            self.popup.hide()
            self._popup_timeout_timer.stop()  # 停止超时计时器

    def _on_completion_error(self, error_msg: str):
        """处理补全错误"""
        print(f"[Jedi] Completion error: {error_msg}")
        self.popup.hide()
        self._popup_timeout_timer.stop()  # 停止超时计时器

    def _on_popup_timeout(self):
        """补全框超时回调"""
        if self.popup.isVisible():
            self.popup.hide()
            print("[Jedi] Popup closed due to timeout.")

    def _on_item_hovered(self, item):
        """当鼠标悬停在补全项上时显示docstring"""
        item_data = item.data(Qt.UserRole)
        if item_data:
            name, type_name, description, detail = item_data
            # 尝试从 Jedi 获取 docstring
            cursor = self.textCursor()
            text = self.toPlainText()
            line = cursor.blockNumber() + 1
            column = cursor.columnNumber()
            try:
                script = jedi.Script(code=text, path='<inline>')
                # 尝试获取悬停项的定义以获取docstring
                # 这里简化处理，实际可能需要更复杂的逻辑
                definitions = script.goto(line=line, column=column-1, follow_imports=True)
                if definitions:
                    docstring = definitions[0].docstring()
                    if docstring:
                        QToolTip.showText(QCursor.pos(), docstring)
                        return
            except:
                pass
            # 如果 Jedi 获取失败或没有docstring，使用 description
            if description:
                QToolTip.showText(QCursor.pos(), description)

    def _show_popup(self):
        """显示补全弹窗，确保位置跟随光标，并动态调整宽度和位置"""
        # 获取光标矩形（相对于编辑器控件本身）
        cursor_rect = self.cursorRect()
        print(f"Debug: cursor_rect = {cursor_rect}")  # 调试用，可以删除
        # 获取编辑器控件本身相对于屏幕的左上角坐标
        editor_global_pos = self.mapToGlobal(QtCore.QPoint(0, 0))
        print(f"Debug: editor_global_pos = {editor_global_pos}")  # 调试用，可以删除

        # --- 微调补全框位置 ---
        # 使用 cursor_rect.topLeft() 获取基准点
        base_point = cursor_rect.topLeft()
        # 计算光标在屏幕上的绝对位置
        # 通常 cursor_rect.bottom() 是光标底部的位置，我们需要这个位置
        screen_cursor_pos = QtCore.QPoint(
            editor_global_pos.x() + base_point.x(),
            editor_global_pos.y() + cursor_rect.bottom()
        )
        # 可选：添加一个微小的垂直偏移以微调位置
        # 这个值可能需要根据字体和行高进行调整
        vertical_offset = 0  # 例如，-2, -1, 0, 1, 2
        screen_cursor_pos.setY(screen_cursor_pos.y() + vertical_offset)

        # --- 修改：动态计算最佳宽度，使用截断后的描述和详情 ---
        max_width = 0
        # --- 新增：定义截断参数，与 CompletionItemDelegate 保持一致 ---
        max_description_length = 60  # 与 delegate 中保持一致
        max_detail_length = 40
        truncation_suffix = "..."
        for i in range(self.popup.count()):
            item = self.popup.item(i)
            item_data = item.data(Qt.UserRole)
            if item_data:
                name, type_name, description, detail = item_data
                # --- 在计算宽度时也截断描述和详情 ---
                if len(description) > max_description_length:
                    truncated_description = description[
                                            :max_description_length - len(truncation_suffix)] + truncation_suffix
                else:
                    truncated_description = description
                if detail and len(detail) > max_detail_length:
                    truncated_detail = detail[:max_detail_length - len(truncation_suffix)] + truncation_suffix
                else:
                    truncated_detail = detail or ""
            else:
                name = item.text()
                type_name = ""
                truncated_description = ""
                truncated_detail = ""

            # 计算该项所需宽度 (使用截断后的描述和详情)
            fm = self.popup.fontMetrics()
            char_width = fm.width(self.type_chars.get(type_name, '?')) + 20
            name_width = fm.width(name) + 20
            # --- 使用截断后的描述和详情宽度 ---
            desc_width = fm.width(truncated_description) + 20 if truncated_description else 0
            detail_width = fm.width(truncated_detail) + 20 if truncated_detail else 0
            total_width = char_width + name_width + desc_width + detail_width + 40
            max_width = max(max_width, total_width)

        # 设置弹窗宽度（限制在屏幕范围内）
        screen_width = self.screen().geometry().width()
        popup_width = min(max_width, screen_width - 100)
        popup_width = max(popup_width, 500)
        self.popup.setFixedWidth(popup_width)

        # 调整弹窗位置，确保不超出屏幕边界
        x = screen_cursor_pos.x()
        y = screen_cursor_pos.y()

        # 检查右边是否超出屏幕
        if x + popup_width > screen_width:
            x = screen_width - popup_width - 10

        # 检查底部是否超出屏幕
        screen_height = self.screen().geometry().height()
        item_height = self.popup.sizeHintForRow(0) if self.popup.count() > 0 else 40
        visible_items = min(self.popup.count(), 15)
        popup_height = item_height * visible_items + 10

        self.popup.move(x, y)
        self.popup.setFixedHeight(popup_height)
        self.popup.show()
        self.popup.setFocus()

    def _get_completion_prefix(self):
        """获取补全前缀"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        start = pos
        while start > 0:
            ch = text[start - 1]
            if ch.isalnum() or ch == '_':
                start -= 1
            else:
                break
        return text[start:pos]

    def _apply_selected_completion(self):
        """应用选中的补全"""
        if not self.popup.currentItem() or self._completing:
            self.popup.hide()
            self._popup_timeout_timer.stop()  # 停止超时计时器
            return

        self._completing = True
        try:
            item = self.popup.currentItem()
            completion_data = item.data(Qt.UserRole)
            if completion_data:
                completion, _, _, _ = completion_data # 修改：解包detail
            else:
                completion = item.text()

            # 更新使用记录 (带时间衰减)
            current_time = time.time()
            if completion in self.completion_usage:
                old_time, old_count = self.completion_usage[completion]
                # 覆盖时间，增加计数
                self.completion_usage[completion] = (current_time, old_count + 1)
            else:
                # 新增记录
                self.completion_usage[completion] = (current_time, 1)

            # 限制记录数量
            if len(self.completion_usage) > self.max_usage_records:
                # 按时间排序，删除最旧的
                sorted_items = sorted(self.completion_usage.items(), key=lambda x: x[1][0])
                oldest_key = sorted_items[0][0]
                del self.completion_usage[oldest_key]

            cursor = self.textCursor()
            prefix = self._get_completion_prefix()
            if prefix:
                # 智能替换：选择 'my_variable' 时替换整个 'my_var'
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
            cursor.insertText(completion)
            self.setTextCursor(cursor)

        finally:
            self._completing = False
            self.popup.hide()
            self._popup_timeout_timer.stop()  # 停止超时计时器

    def _on_completion_selected(self, item):
        """处理补全选择"""
        self._apply_selected_completion()

    def focusOutEvent(self, event):
        """处理焦点丢失事件"""
        # 焦点丢失时隐藏补全框
        self.popup.hide()
        self._popup_timeout_timer.stop()  # 停止超时计时器
        QToolTip.hideText() # 隐藏可能显示的tooltip
        super().focusOutEvent(event)

    def __del__(self):
        """清理资源"""
        if hasattr(self, 'completion_worker'):
            self.completion_worker.running = False

class FullscreenCodeDialog(MessageBoxBase):
    """全屏代码对话框"""
    def __init__(self, initial_code="", parent=None, code_parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码编辑器")
        self.code_editor = JediCodeEditor(parent=parent, code_parent=code_parent, dialog=self)
        self.code_editor.setPlainText(initial_code)
        self.code_editor.setMinimumSize(1000, 600)
        self.viewLayout.addWidget(self.code_editor)
        self.buttonGroup.hide()

    def get_code(self):
        return self.code_editor.toPlainText()

class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jedi Code Editor with Smart Completion")
        self.resize(800, 600)
        self.editor = JediCodeEditor()
        self.editor.set_text("import os\nos.\nx = 'hello'\nx.")
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.editor)
        self.setCentralWidget(central)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win.editor.setFocus()
    sys.exit(app.exec_())