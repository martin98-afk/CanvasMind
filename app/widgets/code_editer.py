import ast

from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QMessageBox
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton,
    TextEdit as FluentTextEdit
)

from app.utils.python_syntax_highlighter import PythonSyntaxHighlighter


# --- 代码编辑器 (新增语法高亮，优化同步) ---
class CodeEditorWidget(QWidget):
    """代码编辑器 - 支持Python语法高亮和自动同步"""
    code_changed = pyqtSignal()  # 代码改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_syntax_highlighting()
        self._setup_auto_sync()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # 代码编辑器
        self.code_editor = FluentTextEdit()
        font = QFont("Consolas", 10)
        self.code_editor.setFont(font)
        self.code_editor.setPlainText(self._get_default_code_template())
        self.code_editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.code_editor)
        # 操作按钮
        button_layout = QHBoxLayout()
        save_btn = PrimaryPushButton("💾 保存代码")
        save_btn.clicked.connect(self._save_code)
        format_btn = PushButton("🧹 格式化代码")
        format_btn.clicked.connect(self._format_code)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(format_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _setup_syntax_highlighting(self):
        """设置语法高亮"""
        self.highlighter = PythonSyntaxHighlighter(self.code_editor.document())

    def _setup_auto_sync(self):
        """设置自动同步"""
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def _on_text_changed(self):
        """文本改变时启动同步定时器"""
        self.code_changed.emit()
        self._sync_timer.start(1000)  # 1秒后解析

    def _parse_and_sync(self):
        """解析代码并同步到UI"""
        try:
            code = self.code_editor.toPlainText()
            if not code.strip():
                return
            # 解析Python代码
            tree = ast.parse(code)
            # 查找组件类定义
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 解析类属性
                    self._parse_component_class(node, code)
                    break
        except SyntaxError:
            # 语法错误时不处理
            pass
        except Exception as e:
            print(f"解析代码失败: {e}")

    def _parse_component_class(self, class_node, code):
        """解析组件类"""
        # 这里可以发送信号给主界面更新UI
        pass

    def _get_default_code_template(self):
        """获取默认代码模板"""
        return '''from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
        
class MyComponent(BaseComponent):
    name = ""
    category = ""
    description = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }
    
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output_data": result
        }
'''

    def _save_code(self):
        """保存代码"""
        # 实现保存逻辑
        QMessageBox.information(self, "保存", "代码已保存！")

    def _format_code(self):
        """格式化代码"""
        # 简单的格式化（实际项目中可以使用 autopep8 或 black）
        code = self.code_editor.toPlainText()
        # 这里可以添加格式化逻辑
        self.code_editor.setPlainText(code)

    def get_code(self):
        """获取代码"""
        return self.code_editor.toPlainText()

    def set_code(self, code):
        """设置代码"""
        self.code_editor.setPlainText(code)
        self._parse_and_sync()