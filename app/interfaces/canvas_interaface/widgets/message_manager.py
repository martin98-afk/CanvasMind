# -*- coding: utf-8 -*-
import datetime

from qfluentwidgets import InfoBar, InfoBarPosition


class MessageManager:

    @staticmethod
    def success(title: str, content: str, parent, duration=2000):
        InfoBar.success(title, content, parent=parent, duration=duration, position=InfoBarPosition.BOTTOM_RIGHT)

    @staticmethod
    def error(title: str, content: str, parent, duration=2000):
        InfoBar.error(title, content, parent=parent, duration=duration, position=InfoBarPosition.BOTTOM_RIGHT)
        parent.log_window.push_log(f"{title} @ {datetime.datetime.now().strftime('%H:%M:%S')}", content)

    @staticmethod
    def warning(title: str, content: str, parent, duration=2000):
        InfoBar.warning(title, content, parent=parent, duration=duration, position=InfoBarPosition.BOTTOM_RIGHT)
        parent.log_window.push_log(f"{title} @ {datetime.datetime.now().strftime('%H:%M:%S')}", content)

    @staticmethod
    def info(title: str, content: str, parent, duration=2000):
        InfoBar.info(title, content, parent=parent, duration=duration, position=InfoBarPosition.BOTTOM_RIGHT)
        parent.log_window.push_log(f"{title} @ {datetime.datetime.now().strftime('%H:%M:%S')}", content)