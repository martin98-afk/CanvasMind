from app.interfaces.component_developer.constants import LLM_CODE_CONTEXT
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import ContextRegistry


class LLMContextProvider:
    # system_prompt = LLM_CODE_CONTEXT

    def __init__(self, parent):
        self.parent = parent
        self.context_register = ContextRegistry()
        self._register_contexts()

    def _register_contexts(self):
        """注册所有支持的大模型上下文类型"""
        self.context_register.register("当前代码", self.extract_current_code, lambda *args, **kwargs: None)
        self.context_register.register("当前选中区域", self.extract_selected_code, lambda *args, **kwargs: None)

    def extract_current_code(self) -> str:
        """返回带组件名称和完整代码的上下文字符串"""
        name = self.parent.name_edit.text().strip() or "未命名组件"
        code = self.parent.code_editor.get_code()
        if not code.strip():
            return f"{name} 全部代码", "代码为空", None
        return f"{name} 全部代码", code, None

    def extract_selected_code(self) -> str:
        """返回带组件名称、行号范围和选中代码的上下文字符串"""
        name = self.parent.name_edit.text().strip() or "未命名组件"
        editor = self.parent.code_editor.code_editor  # 假设这是 QPlainTextEdit 或类似
        cursor = editor.textCursor()

        if cursor.hasSelection():
            # 获取选中范围的起始/结束行号（从1开始）
            start_line = cursor.selectionStart()
            end_line = cursor.selectionEnd()
            doc = editor.document()
            start_block = doc.findBlock(start_line)
            end_block = doc.findBlock(end_line - 1)  # selectionEnd 是下一个字符位置
            start_line_num = start_block.blockNumber() + 1
            end_line_num = end_block.blockNumber() + 1

            selected_text = cursor.selectedText().replace('\u2029', '\n')  # PyQt5 用 \u2029 表示换行
            return f"{name} {start_line_num}~{end_line_num}行代码", selected_text, None
        else:
            # 未选中则返回完整代码（与 extract_current_code_for_llm 一致）
            code = self.parent.code_editor.get_code()
            if not code.strip():
                return f"{name} 全部代码", "代码为空", None
            return f"{name} 全部代码", code, None

    def send_preset_generate_llm_request(self, question):
        # 右边栏切换到大模型
        self.parent.llm_chatter._first_show = True
        self.parent.side_dock_area.switch_to("大模型对话")
        self.parent.llm_chatter.send_preset_question(question)