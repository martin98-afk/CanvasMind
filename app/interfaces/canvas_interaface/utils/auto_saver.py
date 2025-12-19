# -*- coding: utf-8 -*-
from pathlib import Path
from PyQt5.QtCore import QTimer
from .logger import get_logger

logger = get_logger("AutoSaver")

class AutoSaver:
    def __init__(self, parent, config):
        self.parent = parent
        self.config = config
        self._auto_save_enabled = config.canvas_auto_save.value
        self._auto_save_interval = config.canvas_auto_save_interval.value * 1000
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._auto_save)
        self.config.canvas_auto_save.valueChanged.connect(self._on_auto_save_changed)
        self.config.canvas_auto_save_interval.valueChanged.connect(self._on_auto_save_interval_changed)
        if self._auto_save_enabled:
            self.start()

    def _on_auto_save_changed(self, enabled):
        self._auto_save_enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()

    def _on_auto_save_interval_changed(self, interval):
        self._auto_save_interval = interval * 1000
        if self._auto_save_enabled:
            self.stop()
            self.start()

    def start(self):
        if self._auto_save_enabled:
            self._timer.start(self._auto_save_interval)
            logger.debug(f"AutoSave started, interval: {self._auto_save_interval/1000}s")
        else:
            logger.debug("AutoSave disabled")

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
            self.parent.save_full_workflow(show_info=False)

    def _auto_save(self):
        logger.debug("AutoSave triggered")
        self.parent.save_full_workflow(show_info=False)