# -*- coding: utf-8 -*-
import json
import os
import pickle
import re
import tempfile
import uuid
import base64

from NodeGraphQt import NodeObject
from PyQt5 import QtCore
from PyQt5.QtCore import QObject
from PyQt5.QtGui import QImage
from loguru import logger

# 导入业务相关的组件协议
from app.components.base import PROGRESS_MARKER, ComponentMessage, PropertyType
from app.utils.node_logger import NodeLogHandler
from app.utils.utils import ssh_send_file
from app.widgets.dialog_widget.component_log_message_box import LogMessageBox
from app.widgets.node_widget.html_widget import HtmlWidgetWrapper

# 导入图像预览控件
# 确保该路径指向你之前优化过的那个 ImageWidgetWrapper 所在的模块
from app.widgets.node_widget.image_widget import ImageWidgetWrapper
from app.widgets.node_widget.text_edit_widget import TextWidgetWrapper


class NodeSignals(QObject):
    """节点核心信号管理器"""
    intercepted_msg_signal = QtCore.pyqtSignal(dict)
    htmlReady = QtCore.pyqtSignal(object, bool)
    stream_data_updated = QtCore.pyqtSignal(object)


class BasicNodeWithGlobalProperty(NodeObject):
    """
    所有业务节点的基类
    集成了日志处理、中间协议分发、流式数据同步以及动态预览控件生成。
    """
    PATTERNS = {
        r'\s+': '_',
        r'\.+': '_'
    }

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.signals = NodeSignals()
        self.parent_window = None

        # --- 核心数据存储 ---
        self._output_values = {}
        self._input_values = {}
        self.column_select = {}
        self._node_logs = ""
        self._realtime_logs = ""
        self._bound_to_persistent_log = False

        # --- 动态控件管理 ---
        # 用于记录每个端口动态创建的图像预览控件，避免重复创建
        self._inline_widgets = {}  # 统一管理所有动态创建的 widget (image/text/chart)
        self._visual_dirty_buffer = set()  # 记录待更新 UI 的端口名
        self._visual_config = {}  # 记录哪些端口需要 display

        # --- 性能优化：UI 刷新节流控制 ---
        self._stream_buffer = set()  # 记录待同步到全局变量的端口
        self._ui_update_timer = QtCore.QTimer()
        self._ui_update_timer.setSingleShot(True)
        # 核心逻辑：统一由这个 timer 处理全局变量同步 + UI 控件刷新
        self._ui_update_timer.timeout.connect(self._sync_and_refresh_ui)
        self._ui_update_interval = 300  # 稍微延长刷新间隔(300ms)以减轻 WebEngine 压力

        # 绑定核心信号
        self.signals.intercepted_msg_signal.connect(self._message_router)
        self.signals.stream_data_updated.connect(self._on_stream_data_received)

        # 初始化持久化 ID
        self.model.add_property("persistent_id", str(uuid.uuid4()))

    @property
    def persistent_id(self):
        return self.model.get_property("persistent_id")

    @property
    def safe_name(self):
        """获取符合 Python 变量命名的节点名"""
        pattern = r'\s+'
        return re.sub(pattern, '_', self.name())

    # =========================== 日志与协议解析逻辑 =================================

    def init_logger(self):
        """初始化节点专属日志处理器"""
        self.log_capture = NodeLogHandler(self.persistent_id, self._log_message, use_file_logging=True)

    def _log_message(self, node_id, message):
        """
        处理来自 Subprocess 的原始日志输出
        """
        # 1. 解析日志，提取并截获中间协议数据
        message = self._parse_and_filter_logs(message)

        if isinstance(message, str) and message.strip():
            if not message.endswith('\n'):
                message += '\n'
            self._realtime_logs += message

            # 2. 通过 scheduler 推送日志（用于主界面日志面板同步）
            if hasattr(self, '_log_message_emitter'):
                run_id = getattr(self, '_current_run_id', "default")
                self._log_message_emitter(run_id, message)

            # 3. 同步到旧弹窗窗口（如果已打开）
            if hasattr(self, 'log_capture') and self.log_capture and self.log_capture.log_window:
                try:
                    self.log_capture.log_window.add_log_entry(message)
                except Exception as e:
                    logger.exception(f"Error sending log to window: {e}")

    def _parse_and_filter_logs(self, raw_text):
        """
        扫描日志行，拦截并解析特定的 JSON 协议数据 (PROGRESS_MARKER)
        """
        if not raw_text:
            return ""

        clean_lines = []
        lines = raw_text.splitlines()

        for line in lines:
            if PROGRESS_MARKER in line:
                try:
                    # 提取数据部分：[PROGRESS_DATA] {...JSON...}
                    json_str = line.split(PROGRESS_MARKER)[1].strip()
                    data = json.loads(json_str)

                    # 发送信号至消息路由中心
                    self.signals.intercepted_msg_signal.emit(data)

                    # 拦截成功后，该行不进入常规 UI 日志面板，保持日志整洁
                    continue
                except Exception as e:
                    logger.exception(f"解析拦截消息失败: {e}")

            clean_lines.append(line)

        return "\n".join(clean_lines)

    def get_logs(self):
        """从持久化日志文件读取历史内容"""
        if not hasattr(self, "log_capture"):
            self.init_logger()
        try:
            return self.log_capture.read_log_file()
        except Exception as e:
            logger.warning(f"读取日志失败: {e}")
            return "日志读取失败。"

    def show_logs(self):
        """弹出详细日志查看窗口"""
        log_content = self.get_logs()
        w = LogMessageBox(log_content, self.parent_window)
        if hasattr(self, "log_capture"):
            self.log_capture.set_log_window(w)
        w.show()

    # =========================== 数据输出与变量管理 =================================

    def set_output_value(self, port_name, value):
        if self._output_values is None: self._output_values = {}
        self._output_values[port_name] = value

    def clear_output_value(self):
        self._output_values = {}

    def get_output_value(self, port_name):
        if self._output_values is None: return None
        return self._output_values.get(port_name)

    def rename_variable(self, old_names: list[str], new_names: list[str]):
        """
        极速重命名优化：使用正则单次扫描全量替换属性中的变量名
        """
        if not old_names: return

        mapping = dict(zip(old_names, new_names))
        pattern = re.compile('|'.join(map(re.escape, sorted(old_names, key=len, reverse=True))))

        def _replace_func(match):
            return mapping[match.group(0)]

        def _process_value(val):
            val_type = type(val)
            if val_type is str:
                # 预过滤提高效率
                if "node_vars." in val or "input." in val:
                    return pattern.sub(_replace_func, val)
                return val
            if val_type is list:
                return [_process_value(i) for i in val]
            if val_type is dict:
                return {k: _process_value(v) for k, v in val.items()}
            return val

        for prop_name, current_val in self.model.custom_properties.items():
            if current_val is None: continue
            new_val = _process_value(current_val)
            if current_val != new_val:
                self.set_property(prop_name, new_val, push_undo=False)

    # =========================== 消息分发与动态控件处理 ===============================

    def _message_router(self, msg_dict: dict):
        """
        分发处理来自拦截协议的消息
        """
        try:
            msg = ComponentMessage(**msg_dict)
            parts = msg.method.split(".")
            namespace = parts[0] if len(parts) > 1 else "default"
            action = parts[1] if len(parts) > 1 else parts[0]

            handler_name = f"_handle_{namespace}_{action}"
            handler = getattr(self, handler_name, self._handle_unknown_method)
            handler(msg.params, msg)
        except Exception as e:
            logger.exception(f"消息路由失败: {e}")

    def _get_var_key(self, port_name):
        """生成全局变量映射 Key"""
        safe_name = self.name()
        safe_port_name = port_name
        for pattern, replacement in self.PATTERNS.items():
            safe_name = re.sub(pattern, replacement, safe_name)
            safe_port_name = re.sub(pattern, replacement, safe_port_name)
        return f"{safe_name}__{safe_port_name}"

    def _handle_stream_output(self, params: dict, msg: ComponentMessage):
        """
        优化后的消息处理器：只负责更新数据和标记 dirty，不直接刷新 UI
        """
        try:
            if self._output_values is None: self._output_values = {}
            extra = getattr(msg, 'extra', {})
            should_display = extra.get('display', False)

            for port_name, info in params.items():
                new_data = info.get("data")
                data_type = info.get("data_type", "str")

                # 1. 更新数据存储逻辑 (增量合并)
                old_val = self._output_values.get(port_name)
                if data_type == "str":
                    self._output_values[port_name] = (old_val or "") + str(new_data)
                elif data_type == "list":
                    if not isinstance(old_val, list): old_val = []
                    if isinstance(new_data, list):
                        old_val.extend(new_data)
                    else:
                        old_val.append(new_data)
                    self._output_values[port_name] = old_val
                else:
                    self._output_values[port_name] = new_data

                # 2. 标记需要同步到全局变量
                self._stream_buffer.add(port_name)

                # 3. 标记需要可视化刷新
                self._visual_config[port_name] = (should_display, data_type)
                if should_display:
                    self._visual_dirty_buffer.add(port_name)
                else:
                    # 如果 display 变为 False，标记需要检查是否移除控件
                    self._visual_dirty_buffer.add(port_name)

            # 触发节流计时器
            self.signals.stream_data_updated.emit(None)

        except Exception as e:
            logger.exception(f"流式结果处理失败: {e}")

    # =========================== 节流同步与渲染核心 ===============================

    def _sync_and_refresh_ui(self):
        """
        定时器触发：一次性处理全局变量更新和 UI 渲染
        """
        if not self.parent_window:
            return

        # --- A. 刷新可视化 UI (最耗时部分) ---
        self._process_visual_updates()

        # --- B. 同步全局变量 (逻辑同前) ---
        self._sync_buffer_to_global()

    def _process_visual_updates(self):
        """合并后的 UI 渲染逻辑"""
        for port_name in list(self._visual_dirty_buffer):
            should_display, data_type = self._visual_config.get(port_name, (False, "str"))
            data = self._output_values.get(port_name)

            # 1. 处理显示/隐藏切换
            widget_base_key = f"{data_type}_{port_name}"

            if not should_display:
                # 如果当前存在控件但被要求隐藏，则清理
                self._remove_inline_widget(widget_base_key)
                continue

            # 2. 根据类型执行具体的渲染
            if data_type == "image" or (isinstance(data, str) and data.startswith("data:image")):
                self._render_image(port_name, data)
            elif data_type == "str":
                self._render_text(port_name, data)
            elif data_type == "list":
                self._render_chart(port_name, data)

        self._visual_dirty_buffer.clear()

    # =========================== 具体渲染实现 ===============================

    def _render_text(self, port_name, content):
        key = f"text_{port_name}"
        if key not in self._inline_widgets:
            widget = TextWidgetWrapper(parent=self.view, name=key, default=f"预览: {port_name}",
                                       type=PropertyType.MULTILINE, window=self.parent_window)
            self._add_inline_widget(key, widget, tab='Visual')
        self._inline_widgets[key].set_value(content)

    def _render_chart(self, port_name, list_data):
        key = f"chart_{port_name}"
        # 性能优化：生成 HTML
        html_content = self._generate_echarts_html(port_name, list_data)

        if key not in self._inline_widgets:
            widget = HtmlWidgetWrapper(parent=self.view, name=key, default=html_content, window=self.parent_window)
            self._add_inline_widget(key, widget, tab='Visual')
        else:
            # 只有当内容变化时才 set_value (WebEngine 刷新开销极大)
            self._inline_widgets[key].set_value(html_content)

    def _render_image(self, port_name, image_data):
        key = f"preview_{port_name}"
        processed_img = self._process_image_data(image_data)
        if not processed_img: return

        if key not in self._inline_widgets:
            widget = ImageWidgetWrapper(parent=self.view, name=key, default=processed_img, window=self.parent_window)
            self._add_inline_widget(key, widget, tab='Preview')
        else:
            self._inline_widgets[key].set_value(processed_img)

    def _generate_echarts_html(self, title, data):
        """优化 HTML 生成性能：添加采样逻辑"""
        from pyecharts import options as opts
        from pyecharts.charts import Line
        from pyecharts.globals import ThemeType

        if not isinstance(data, list) or len(data) == 0: return ""

        # --- 性能优化：采样 ---
        # 如果数据点超过 500 个，进行等间隔采样，防止 WebEngine 渲染崩溃
        display_data = data
        if len(data) > 500:
            step = len(data) // 500
            display_data = data[::step]
            x_data = [i * step for i in range(len(display_data))]
        else:
            x_data = list(range(1, len(data) + 1))

        chart = Line(
            init_opts=opts.InitOpts(width="500px", height="280px", theme=ThemeType.DARK, bg_color="transparent"))
        chart.add_xaxis(x_data)
        chart.add_yaxis(series_name=title, y_axis=display_data, is_smooth=True,
                        symbol="none",  # 不渲染点，只渲染线，大幅提升性能
                        linestyle_opts=opts.LineStyleOpts(width=2),
                        label_opts=opts.LabelOpts(is_show=False))

        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title, title_textstyle_opts=opts.TextStyleOpts(font_size=12, color="#eee")),
            legend_opts=opts.LegendOpts(is_show=False),
            xaxis_opts=opts.AxisOpts(type_="value"),
            yaxis_opts=opts.AxisOpts(splitline_opts=opts.SplitLineOpts(is_show=True))
        )
        return chart.render_embed()

    # =========================== 辅助工具 ===============================

    def _add_inline_widget(self, key, widget, tab):
        if key in self.model._custom_prop:
            self.model._custom_prop.pop(key)
        self.view.set_proxy_mode(False)
        self.add_custom_widget(widget, tab=tab)
        self._inline_widgets[key] = widget
        self.view.draw_node()

    def _remove_inline_widget(self, key):
        # 检查多个可能的前缀
        for prefix in ["text_", "chart_", "preview_"]:
            full_key = prefix + key.split('_', 1)[-1]
            if full_key in self._inline_widgets:
                w = self._inline_widgets.pop(full_key)
                if full_key in self.model._custom_prop:
                    self.model._custom_prop.pop(full_key)
                self.view.remove_widget(w)
                self.view.draw_node()

    def _process_image_data(self, image_data):
        """解析图像数据逻辑 (封装原有的 base64/path 逻辑)"""
        if isinstance(image_data, str):
            if image_data.startswith("data:image"):
                try:
                    _, encoded = image_data.split(",", 1)
                    return QImage.fromData(base64.b64decode(encoded))
                except:
                    return None
            elif os.path.exists(image_data):
                img = QImage(image_data)
                return None if img.isNull() else img
        return image_data

    def _on_stream_data_received(self, _):
        if not self._ui_update_timer.isActive():
            self._ui_update_timer.start(self._ui_update_interval)

    def _sync_buffer_to_global(self):
        """同步全局变量的逻辑 (原有逻辑)"""
        if not self.parent_window or not self._stream_buffer:
            return
        has_changed = False
        scheduler = self.parent_window.scheduler
        for port_name in self._stream_buffer:
            var_key = self._get_var_key(port_name)
            var_obj = self.parent_window.global_variables.node_vars.get(var_key)
            if var_obj and var_obj.update_policy != "固定" and scheduler:
                current_val = self._output_values.get(port_name)
                scheduler.update_node_variable(var_key, current_val, var_obj.update_policy)
                has_changed = True
        self._stream_buffer.clear()
        if has_changed:
            scheduler.node_vars_changed.emit()
        if self.parent_window.property_panel and self.selected():
            self.parent_window.property_panel.update_properties(self)

    # =========================== 其它指令处理器 =================================

    def _handle_global_variable_clear(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value.startswith(params.get("type", "")):
            value = value.split("node_vars.")[1]
        if self.parent_window:
            self.parent_window._on_global_variables_changed(
                var_type="node_vars", var_name=value, action="clear"
            )

    def _handle_global_variable_add(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._add_output_to_global_variable(
                node=self, port_name=value,
            )

    def _handle_global_variable_delete(self, params: dict, msg: ComponentMessage):
        value = params.get("value", "")
        if value and self.parent_window:
            self.parent_window.property_panel._delete_output_from_global_variable(
                node=self, port_name=value,
            )

    def _handle_ui_ask(self, params: dict, msg: ComponentMessage):
        """处理人工干预对话框请求"""
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        response_file = params.get("response_file")
        schema = params.get("schema")

        # 获取环境数据
        env_data = getattr(self.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if is_ssh:
                # --- SSH 模式 ---
                # 1. 创建本地临时文件
                temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
                try:
                    with open(temp_path, 'wb') as f:
                        pickle.dump(result_data, f)

                    # 2. 调用公用函数发送
                    success = ssh_send_file(env_data, temp_path, response_file)

                    if not success:
                        logger.error("远程回传人工干预结果失败")
                finally:
                    # 3. 清理临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            else:
                # --- 本地模式 ---
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        self.parent_window.show_intervention_dialog(title, message, schema, on_confirmed)

    def _handle_unknown_method(self, params: dict, msg: ComponentMessage):
        logger.warning(f"收到未知指令: {msg.method}")