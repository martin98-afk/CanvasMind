# backdrop_executor.py 或放在 node_list_executor.py 中
import datetime
import re
import traceback

from loguru import logger

from app.nodes.status_node import NodeStatus
from app.scan_components import ComponentScanner


def register_global_variable(node, global_variable):
    if node.has_property("global_variable"):
        node.set_property("global_variable", global_variable.serialize())
    else:
        node.model.add_property("global_variable", global_variable.serialize())


def execute_node(
        node, component_map, python_exe, kernel_manager, scheduler,
        global_variable, execution_context, log_start_func,
        log_message_func, log_error_func, log_finish_func,
        run_id_postfix="", semaphore=None  # 新增信号量参数
):
    from app.nodes.backdrop_node import ControlFlowBackdrop
    if isinstance(node, ControlFlowBackdrop): return None
    if node.get_property("disabled"): return None
    if not hasattr(node, "execute_sync"): return None
    # 日志准备
    is_log_node = "StatusDynamicNode_" in node.model.type_ or "DYNAMIC_CODE" in node.model.type_
    if is_log_node:
        run_id_postfix = f'@{run_id_postfix}' if run_id_postfix else ''
        run_id = f"{node.name()}{run_id_postfix}@{datetime.datetime.now().strftime('%H:%M:%S')}"
        node._current_run_id = run_id
        node._log_message_emitter = log_message_func
        log_start_func(run_id)

    comp_cls = ComponentScanner().get_component_by_uuid(node.uuid) if "StatusDynamicNode_" in node.model.type_ else None

    try:
        # --- 信号量限流开始 ---
        if semaphore:
            semaphore.acquire()
        # ---------------------

        run_mode = scheduler.parent.config.canvas_run_mode.value
        results = node.execute_sync(
            comp_cls,
            python_executable=python_exe,
            check_cancel=execution_context.check_cancel,
            kernel_manager=kernel_manager if run_mode == "ipython运行" else None,
            global_variable=global_variable.serialize()
        )

        # 变量更新逻辑 (保持原样)
        if results is not None:
            for port_name, result in results.items():
                pattern = r'\s+'
                var_key = f"{re.sub(pattern, '_', node.name())}__{port_name}"
                var_obj = scheduler.global_variables.node_vars.get(var_key)
                if var_obj and var_obj.update_policy != "固定":
                    scheduler.update_node_variable(var_key, result, var_obj.update_policy)
        # 发送运行完成信号
        if is_log_node: log_finish_func(run_id)
        return results

    except Exception as e:
        if is_log_node: log_error_func(run_id)
        if scheduler: scheduler.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        raise e
    finally:
        # --- 信号量释放 ---
        if semaphore:
            semaphore.release()