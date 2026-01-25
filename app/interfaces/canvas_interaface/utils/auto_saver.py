# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer
from .logger import get_logger

logger = get_logger("AutoSaver")


class AutoSaver:
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config

        # 内部状态
        self._is_saving = False  # 防止重入

        # 主计时器：负责定期自动保存
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._auto_save)

        # 防抖计时器：负责在用户修改设置后，延迟应用新设置，防止滑块拖动导致的卡死
        self._debounce_timer = QTimer(parent)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._apply_settings)

        # 绑定配置信号
        self.config.canvas_auto_save.valueChanged.connect(self._on_config_changed)
        self.config.canvas_auto_save_interval.valueChanged.connect(self._on_config_changed)

        # 初始化启动
        self._apply_settings()

    def _on_config_changed(self, _=None):
        """配置变动时，不立即操作，而是启动防抖计时器"""
        # 停止主计时器，防止在调整过程中突然触发保存
        if self._timer.isActive():
            self._timer.stop()
        # 300ms 后再应用新设置（等待用户停止拖动滑块）
        self._debounce_timer.start(300)

    def _apply_settings(self):
        """真正应用设置逻辑"""
        enabled = self.config.canvas_auto_save.value
        interval_secs = self.config.canvas_auto_save_interval.value

        if enabled and interval_secs > 0:
            interval_ms = interval_secs * 1000
            self._timer.start(interval_ms)
            logger.debug(f"自动保存已开启，间隔: {interval_secs}s")
        else:
            self._timer.stop()
            logger.debug("自动保存已关闭")

    def start(self):
        """外部调用接口"""
        self._apply_settings()

    def stop(self):
        """外部调用接口：仅停止计时器，不再强制执行保存"""
        if self._timer.isActive():
            self._timer.stop()
            logger.debug("自动保存计时器已停止")

    def _auto_save(self):
        """触发保存"""
        if self._is_saving:
            return

        # 检查父窗口是否处于可以保存的状态（比如没有正在关闭）
        if not self.parent or not self.parent.isVisible():
            return

        try:
            self._is_saving = True
            logger.debug("开始执行定期自动保存...")

            # 注意：如果 save_full_workflow 极其耗时，
            # 考虑在 parent 内部将其部分逻辑（如写文件）放到线程中。
            self.parent.save_full_workflow(show_info=False)

            logger.debug("定期自动保存完成")
        except Exception as e:
            logger.error(f"自动保存失败: {e}")
        finally:
            self._is_saving = False