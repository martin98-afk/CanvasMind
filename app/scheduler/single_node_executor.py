# backdrop_executor.py 或放在 node_list_executor.py 中
import datetime
import re
import traceback

from loguru import logger

from app.nodes.status_node import NodeStatus


def register_global_variable(node, global_variable):
    if node.has_property("global_variable"):
        node.set_property("global_variable", global_variable.serialize())
    else:
        node.model.add_property("global_variable", global_variable.serialize())


def execute_node(
    node,
    component_map,
    python_exe,
    kernel_manager,
    scheduler,
    global_variable,
    execution_context,  # ← 新增
    log_start_func,
    log_message_func,
    log_error_func,
    log_finish_func,
    run_id_postfix="",
):
    """
    执行单个节点（普通节点或 backdrop 内部节点）
    不依赖 QRunnable，纯逻辑执行
    """
    from app.nodes.backdrop_node import ControlFlowBackdrop

    if isinstance(node, ControlFlowBackdrop):
        raise ValueError("Backdrop 应由 BackdropExecutor 处理，不应在此执行")

    # 跳过 disabled 节点
    if node.get_property("disabled"):
        return None

    comp_cls = component_map.get(getattr(node, "FULL_PATH", None))
    run_id_postfix = f'@{run_id_postfix}'if run_id_postfix else ''
    # 生成 run_id
    run_id = f"{node.name()}@{datetime.datetime.now().strftime('%H:%M:%S')}{run_id_postfix}"
    node._current_run_id = run_id
    node._log_message_emitter = log_message_func
    # 发送运行开始信号
    log_start_func(run_id)

    try:
        # 根据运行模式选择执行方式
        run_mode = scheduler.parent.config.canvas_run_mode.value
        register_global_variable(node, global_variable)
        results = node.execute_sync(
            comp_cls,
            python_executable=python_exe,
            check_cancel=execution_context.check_cancel,
            kernel_manager=kernel_manager if run_mode == "ipython运行" else None
        )

        # 变量自动更新
        if results is not None:
            for port_name, result in results.items():
                node_name = re.sub(r"\s+", "_", node.name())
                var_key = f"{node_name}__{port_name}"
                var_obj = scheduler.global_variables.node_vars.get(var_key)
                if var_obj and var_obj.update_policy != "固定":
                    scheduler.update_node_variable(var_key, result, var_obj.update_policy)
        # 发送运行完成信号
        log_finish_func(run_id)

        return results

    except Exception as e:
        logger.error(f"节点 {node.name()} 执行失败: {e}")
        logger.error(traceback.format_exc())
        log_error_func(run_id)
        if scheduler:
            scheduler.set_node_status(node, NodeStatus.NODE_STATUS_FAILED)
        raise