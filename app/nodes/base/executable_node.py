# -*- coding: utf-8 -*-
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from loguru import logger

from app.components.base import (
    GlobalVariableContext,
    PropertyType,
)
from app.nodes.base.status_node import StatusNode
from app.nodes.executors import ExecutorRegistry, ExecutionContext
from app.scheduler.expression_engine import ExpressionEngine
from app.utils.config import Settings
from app.utils.utils import get_free_port, serialize_for_json


class ExecutableNodeMixin:
    """可执行节点 Mixin - 封装节点执行的核心逻辑"""

    def create_execution_context(
        self,
        comp_obj: Any,
        kernel_manager: Any = None,
        check_cancel: Optional[Callable[[], bool]] = None,
        global_variable: Optional[Dict[str, Any]] = None,
        python_executable: Optional[str] = None,
        **kwargs,
    ) -> ExecutionContext:
        """创建执行上下文"""
        ctx = ExecutionContext(
            node=self,
            comp_obj=comp_obj,
            kernel_manager=kernel_manager,
            check_cancel=check_cancel,
            global_variable=global_variable or {},
            cache_path=getattr(self, "CACHE_PATH", Path.cwd()),
            python_executable=python_executable or "",
        )

        ctx.env_data = getattr(self.parent_window, "env_data", {})
        if not ctx.env_data:
            raise Exception("未检测到有效的执行环境，请先在环境管理器中选择。")

        config = getattr(self.parent_window, "config", None)
        if config:
            ctx.timeout_enabled = config.node_run_timeout_toggle.value
            ctx.timeout_seconds = config.node_run_timeout.value
        else:
            ctx.timeout_enabled = False
            ctx.timeout_seconds = 60

        ctx.last_log_pos = 0
        if hasattr(self, "log_capture") and self.log_capture:
            log_path = self.log_capture.get_log_file_path()
            import os

            if os.path.exists(log_path):
                ctx.last_log_pos = os.path.getsize(log_path)

        return ctx

    def prepare_params_and_inputs(
        self,
        ctx: ExecutionContext,
        properties: Dict[str, Any],
        reserved_properties: set,
    ) -> None:
        """准备参数和输入"""
        params = serialize_for_json(self.model._custom_prop)

        for prop_name, prop_def in properties.items():
            prop_ori_name = prop_name
            if prop_name in reserved_properties:
                prop_name = f"_{prop_name}"
                params.pop(prop_name, None)

            prop_type = prop_def.get("type", PropertyType.TEXT)
            default = prop_def.get("default", "")

            if prop_type == PropertyType.DYNAMICFORM:
                widget = self.get_widget(prop_name)
                params[prop_ori_name] = (
                    widget.get_value() if widget else (default or [])
                )
            else:
                params[prop_ori_name] = (
                    self.get_property(prop_name)
                    if self.has_property(prop_name)
                    else default
                )

        gv = GlobalVariableContext()
        gv.deserialize(ctx.global_variable)

        inputs_raw = {}
        input_vars = {}
        ctx.global_variable["inputs"] = {}

        for input_port in self.input_ports():
            port_name = input_port.name()
            connected = input_port.connected_ports()

            if connected:
                if input_port.model.multi_connection:
                    inputs_raw[port_name] = [
                        up.node()._output_values.get(up.name()) for up in connected
                    ]
                    input_vars[f"input_{port_name}"] = inputs_raw[port_name]

                    for idx, up in enumerate(connected):
                        safe_name = up.node().name().replace(" ", "_")
                        input_vars[f"input_{safe_name}__{up.name()}"] = (
                            up.node()._output_values.get(up.name())
                        )
                        ctx.global_variable["inputs"][
                            f"input.{safe_name}__{up.name()}"
                        ] = idx
                else:
                    inputs_raw[port_name] = (
                        connected[0].node()._output_values.get(connected[0].name())
                    )
                    input_vars[f"input_{port_name}"] = inputs_raw[port_name]
                    safe_name = connected[0].node().name().replace(" ", "_")
                    input_vars[f"input_{safe_name}__{connected[0].name()}"] = (
                        inputs_raw[port_name]
                    )

                if port_name in self.get_property("_data_select"):
                    inputs_raw[f"{port_name}_data_select"] = self.get_property(
                        "_data_select"
                    ).get(port_name)
                    inputs_raw[f"{port_name}_data_select_visible"] = (
                        self.get_property("_data_selector_visible") or {}
                    ).get(port_name, False)

        expr_engine = ExpressionEngine(global_vars_context=gv)

        def _evaluate(value):
            if isinstance(value, str):
                return expr_engine.evaluate_template(value, local_vars=input_vars)
            if isinstance(value, list):
                return [_evaluate(v) for v in value]
            if isinstance(value, dict):
                return {k: _evaluate(v) for k, v in value.items()}
            return value

        ctx.params = {k: _evaluate(v) for k, v in params.items()}
        ctx.inputs = {k: _evaluate(v) for k, v in inputs_raw.items()}

    def setup_zmq_environment(self, ctx: ExecutionContext) -> None:
        """设置 ZMQ 环境"""
        if Settings.get_instance().communication_method.value == "ZMQ通信":
            remote_ip = (
                ctx.env_data.get("host") if ctx.env_data.get("type") == "ssh" else None
            )
            ctx.zmq_env_vars = self.setup_zmq_env(
                get_free_port(), get_free_port(), remote_ip
            )

    def prepare_execution_files(self, ctx: ExecutionContext) -> None:
        """准备执行所需的文件"""
        ctx.run_dir.mkdir(parents=True, exist_ok=True)

        ctx.params_path = ctx.run_dir / "params.pkl"
        ctx.result_path = ctx.run_dir / "result.pkl"
        ctx.error_path = ctx.run_dir / "error.pkl"

        import pickle

        with open(ctx.params_path, "wb") as f:
            pickle.dump((ctx.params, ctx.inputs, ctx.global_variable), f)

    def get_component_code(self) -> str:
        """获取组件代码 - 子类实现"""
        raise NotImplementedError

    def get_class_name(self) -> str:
        """获取组件类名 - 子类实现"""
        raise NotImplementedError

    def execute_standard(
        self,
        comp_obj: Any,
        kernel_manager: Any = None,
        check_cancel: Optional[Callable[[], bool]] = None,
        global_variable: Optional[Dict[str, Any]] = None,
        python_executable: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        标准执行流程 - 所有可执行节点应该调用此方法
        """
        self.hide_inline_widgets()
        self.clear_output_value()

        ctx = self.create_execution_context(
            comp_obj,
            kernel_manager,
            check_cancel,
            global_variable,
            python_executable=python_executable,
            **kwargs,
        )

        if not hasattr(self, "log_capture"):
            self.init_logger()

        if hasattr(self, "log_capture") and self.log_capture:
            ctx.log_file_path = self.log_capture.get_log_file_path()

        reserved_properties = set(self.model.properties.keys())
        properties = comp_obj.get_properties()

        self.prepare_params_and_inputs(ctx, properties, reserved_properties)
        self.setup_zmq_environment(ctx)
        self.prepare_execution_files(ctx)

        ctx.component_code = self.get_component_code()
        ctx.class_name = self.get_class_name()

        executor_registry = ExecutorRegistry.get_instance()
        executor = executor_registry.select_executor(ctx)

        if not executor:
            raise Exception("无法选择合适的执行器")

        executor.prepare_environment(ctx)

        try:
            result = executor.execute(ctx)
            return result
        finally:
            self.stop_zmq()
            try:
                shutil.rmtree(ctx.run_dir, ignore_errors=True)
            except:
                pass


class ExecutableNode(ExecutableNodeMixin, StatusNode):
    """
    可执行节点基类 - 继承此类的节点具备完整的执行能力

    子类只需实现:
    - get_component_code(): 返回组件代码
    - get_class_name(): 返回组件类名
    """

    def __init__(self, qgraphics_item=None):
        super().__init__(qgraphics_item)
        self.object_io = False

    def get_component_code(self) -> str:
        """获取组件代码 - 子类必须实现"""
        raise NotImplementedError("子类必须实现 get_component_code 方法")

    def get_class_name(self) -> str:
        """获取组件类名 - 子类必须实现"""
        raise NotImplementedError("子类必须实现 get_class_name 方法")

    def execute_sync(
        self,
        comp_obj: Any,
        kernel_manager: Any = None,
        check_cancel: Optional[Callable[[], bool]] = None,
        global_variable: Optional[Dict[str, Any]] = None,
        python_executable: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        执行节点 - 标准入口
        """
        return self.execute_standard(
            comp_obj,
            kernel_manager,
            check_cancel,
            global_variable,
            python_executable=python_executable,
            **kwargs,
        )

    def _clear_ipython_memory_context(self, mode: str) -> None:
        """清理 IPython 内存上下文"""
        logger.info(f"节点 {self.name()} 模式切换至: {mode}，已尝试清理残留内存。")

        if not hasattr(self.parent_window, "ipython_kernel"):
            return

        km = self.parent_window.ipython_kernel.kernel_manager
        if km and mode == "subprocess":
            from app.templates.node_cleanup_script import CLEANUP_CODE

            unique_key = f"dynamic_mod_{self.persistent_id}"
            cleanup_code = CLEANUP_CODE.format(unique_key=unique_key)
            try:
                km.execute_code(cleanup_code, hidden=True)
            except Exception as e:
                logger.warning(f"清理节点 {self.persistent_id} 内存失败: {e}")


class SimpleExecutableNodeMixin:
    """
    简化版可执行节点 Mixin - 适用于不需要复杂参数处理的节点

    子类只需提供 component_code 和 class_name
    """

    component_code: str = ""
    class_name: str = ""

    def get_component_code(self) -> str:
        return self.component_code

    def get_class_name(self) -> str:
        return self.class_name
