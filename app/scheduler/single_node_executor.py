import datetime
import re

from app.nodes.backdrop_node import ControlFlowBackdrop
from app.nodes.status_node import NodeStatus


def execute_node(
    node, python_exe, kernel_manager, scheduler,
    global_variable, execution_context, log_start_func,
    log_message_func, log_error_func, log_finish_func,
    run_id_postfix="", semaphore=None, callback_func=None
):
    # 容器节点不占用信号量名额，直接返回
    if isinstance(node, ControlFlowBackdrop):
        return None
    if node.get_property("disabled"):
        return None
    if not hasattr(node, "execute_sync"):
        return None

    # 1. 信号量排队 (阻塞点)
    acquired = False
    if semaphore:
        semaphore.acquire()
        acquired = True

    # 2. 【关键】只有抢到位置后，才更新状态和发送开始信号
    scheduler.set_node_status(node, NodeStatus.NODE_STATUS_RUNNING)
    if callback_func: callback_func()
    # 3. 日志卡片开始记录
    # 日志准备逻辑...
    is_log_node = "StatusDynamicNode_" in node.model.type_ or "DYNAMIC_CODE" in node.model.type_
    run_id = ""
    if is_log_node:
        run_id_postfix_str = f'@{run_id_postfix}' if run_id_postfix else ''
        run_id = f"{node.name()}{run_id_postfix_str}@{datetime.datetime.now().strftime('%H:%M:%S')}"
        node._current_run_id = run_id
        node._log_message_emitter = log_message_func
        log_start_func(run_id)

    try:
        comp_cls = None
        if "StatusDynamicNode_" in node.model.type_:
            from app.scan_components import ComponentScanner
            comp_cls = ComponentScanner().get_component_by_uuid(node.uuid)

        run_mode = scheduler.parent.config.canvas_run_mode.value
        # 真正的业务执行
        results = node.execute_sync(
            comp_cls,
            python_executable=python_exe,
            check_cancel=execution_context.check_cancel,
            kernel_manager=kernel_manager if run_mode == "ipython运行" else None,
            global_variable=global_variable.serialize()
        )

        # 变量更新逻辑...
        if results is not None:
            for port_name, result in results.items():
                pattern = r'\s+'
                var_key = f"{re.sub(pattern, '_', node.name())}__{port_name}"
                var_obj = scheduler.global_variables.node_vars.get(var_key)
                if var_obj and var_obj.update_policy != "固定":
                    scheduler.update_node_variable(var_key, result, var_obj.update_policy)

        if is_log_node:
            log_finish_func(run_id)
        scheduler.set_node_status(node, NodeStatus.NODE_STATUS_SUCCESS)
        if callback_func: callback_func()
        return results

    except Exception as e:
        if is_log_node:
            log_error_func(run_id)
        scheduler.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        if callback_func: callback_func()
        raise e
    finally:
        if acquired:
            semaphore.release()