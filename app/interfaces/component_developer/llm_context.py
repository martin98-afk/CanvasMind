from pathlib import Path

from app.interfaces.component_developer.constants import LLM_CODE_CONTEXT, COMPONENT_EXTENSION_PATH
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import ContextRegistry
from app.utils.utils import resource_path


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

    def _get_component_paths(self):
        """获取当前组件的路径信息"""
        full_path = self.parent.component_tree._current_editing_component or ""
        source_file = self.parent.storage_manager._current_component_file
        extension_base = Path(resource_path(COMPONENT_EXTENSION_PATH))
        
        component_abs_path = ""
        extension_abs_path = ""
        
        if source_file:
            uuid_str = source_file.stem
            component_abs_path = str(source_file)
            extension_abs_path = str(extension_base / uuid_str)
        
        return full_path, component_abs_path, extension_abs_path

    def _build_code_prefix(self, full_path, component_abs_path, extension_abs_path):
        """构建代码前缀信息"""
        prefix_parts = []
        if full_path:
            prefix_parts.append(f"组件路径: {full_path}")
        if component_abs_path:
            prefix_parts.append(f"源码文件: {component_abs_path}")
        if extension_abs_path:
            prefix_parts.append(f"扩展资源目录: {extension_abs_path}")
        
        if prefix_parts:
            return "# " + "\n# ".join(prefix_parts) + "\n\n"
        return ""

    def extract_current_code(self) -> str:
        """返回带组件名称、路径信息和完整代码的上下文字符串"""
        name = self.parent.name_edit.text().strip() or "未命名组件"
        code = self.parent.code_editor.get_code()
        
        full_path, component_abs_path, extension_abs_path = self._get_component_paths()
        path_prefix = self._build_code_prefix(full_path, component_abs_path, extension_abs_path)
        
        if not code.strip():
            return f"{name} 全部代码", "代码为空", None
        return f"{name} 全部代码", path_prefix + code, None

    def extract_selected_code(self) -> str:
        """返回带组件名称、路径信息、行号范围和选中代码的上下文字符串"""
        name = self.parent.name_edit.text().strip() or "未命名组件"
        editor = self.parent.code_editor.code_editor  # 假设这是 QPlainTextEdit 或类似
        cursor = editor.textCursor()
        
        full_path, component_abs_path, extension_abs_path = self._get_component_paths()
        path_prefix = self._build_code_prefix(full_path, component_abs_path, extension_abs_path)

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
            return f"{name} {start_line_num}~{end_line_num}行代码", path_prefix + selected_text, None
        else:
            # 未选中则返回完整代码（与 extract_current_code_for_llm 一致）
            code = self.parent.code_editor.get_code()
            if not code.strip():
                return f"{name} 全部代码", "代码为空", None
            return f"{name} 全部代码", path_prefix + code, None

    def send_preset_generate_llm_request(self, question):
        # 右边栏切换到大模型
        self.parent.llm_chatter._first_show = True
        self.parent.side_dock_area.switch_to("大模型对话")
        self.parent.llm_chatter.send_preset_question(question)