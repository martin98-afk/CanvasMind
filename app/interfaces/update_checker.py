import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QApplication, QProgressDialog
from qfluentwidgets import InfoBar, InfoBarPosition, InfoBarIcon, PrimaryPushButton, MessageBox

from app.utils.config import Settings
from app.utils.threading_utils import AsyncUpdateChecker, DownloadThread


class UpdateChecker(QWidget):
    """优化后的更新检查器：保留 InfoBar 交互，适配 Inno Setup EXE"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.cfg = Settings.get_instance()

        # --- 修复报错：初始化 AsyncUpdateChecker 依赖的属性 ---
        self.platform = self.cfg.patch_platform.value
        self.repo = self.cfg.github_repo.value
        self.token = self.cfg.github_token.value
        self.current_version = self.cfg.current_version
        # -----------------------------------------------

        self.progress_dialog = None
        self.download_thread = None
        self.installer_path = None

    def check_update(self):
        """检查更新入口"""
        self.async_checker = AsyncUpdateChecker(self)
        self.async_checker.finished.connect(self._on_check_finished)
        self.async_checker.error.connect(lambda msg: self.create_errorbar("检查更新失败", msg))
        self.async_checker.start()

    def _on_check_finished(self, latest_release):
        """异步请求完成回调"""
        if latest_release:
            latest_version = latest_release.get("tag_name", "").lstrip('v')
            if self._compare_versions(latest_version, self.current_version) > 0:
                self._show_update_infobar(latest_release)
            else:
                # 仅在手动触发时提示“已是最新”
                pass

    def _show_update_infobar(self, latest_release):
        """保持原有的 InfoBar 交互方式"""
        latest_version = latest_release.get("tag_name", "未知")
        update_notes = latest_release.get("body", "无更新说明")

        info_bar = InfoBar(
            icon=InfoBarIcon.INFORMATION,
            title=f"发现新版本 {latest_version}",
            content=f"更新内容：\n{update_notes[:100]}...",
            orient=Qt.Vertical,  # 垂直布局适合显示较多文字
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=-1,  # 不自动消失
            parent=self.parent or self
        )

        # 添加“立即更新”按钮到 InfoBar
        update_button = PrimaryPushButton("立即更新")
        update_button.setFixedWidth(80)
        update_button.clicked.connect(lambda: self._on_update_confirmed(latest_release, info_bar))
        info_bar.widgetLayout.addWidget(update_button, 0, Qt.AlignRight)

        info_bar.show()

    def _on_update_confirmed(self, latest_release, info_bar):
        """用户点击 InfoBar 上的按钮后触发"""
        info_bar.close()
        self._start_download(latest_release)

    def _start_download(self, latest_release):
        """寻找 EXE 并下载"""
        update_url = None
        exe_name = f"Update_{latest_release['tag_name']}.exe"

        # 遍历 Release 资产定位 EXE
        for asset in latest_release.get("assets", []):
            if asset["name"].endswith(".exe"):
                update_url = asset["browser_download_url"]
                exe_name = asset["name"]
                break

        if not update_url:
            self.create_errorbar("未找到安装程序", "请前往 GitHub Release 手动下载")
            return

        # 下载到临时目录
        self.installer_path = os.path.join(tempfile.gettempdir(), exe_name)

        # 显示下载进度对话框（由于即将重启安装，此处使用模态对话框是标准做法）
        self.progress_dialog = QProgressDialog("正在下载新版本...", "取消", 0, 100, self.parent or self)
        self.progress_dialog.setWindowTitle("软件更新")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(self._cancel_download)

        self.download_thread = DownloadThread(update_url, self.installer_path, self.token)
        self.download_thread.progress_signal.connect(self.progress_dialog.setValue)
        self.download_thread.finished_signal.connect(self._handle_download_finished)
        self.download_thread.error_signal.connect(self._handle_download_error)
        self.download_thread.start()

    def _handle_download_finished(self):
        """下载完成：不再执行解压和 BAT，直接运行 EXE"""
        if self.progress_dialog:
            self.progress_dialog.close()

        # 专业软件的最后确认：询问是否关闭程序并安装
        title = "下载完成"
        content = "安装包已准备就绪，是否立即关闭程序并升级？"
        msg_box = MessageBox(title, content, self.parent or self)
        msg_box.yesButton.setText("现在安装")
        msg_box.cancelButton.setText("稍后手动安装")

        if msg_box.exec():
            self._run_installer()

    def _run_installer(self):
        """启动 Inno Setup 安装包"""
        try:
            # /SILENT: 显示安装进度但不需要点击
            # /SP-: 屏蔽“你确定要安装吗”提示
            # 使用 shell=True 和 DETACHED_PROCESS 确保安装进程在主程序退出后依然运行
            subprocess.Popen(
                [self.installer_path, "/SILENT", "/SP-"],
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )

            # 立即关闭主程序
            QApplication.quit()
            os._exit(0)
        except Exception as e:
            self.create_errorbar("启动失败", str(e))

    def _cancel_download(self):
        if self.download_thread:
            self.download_thread.is_canceled = True
            self.download_thread = None

    def _handle_download_error(self, error_msg):
        if self.progress_dialog:
            self.progress_dialog.close()
        self.create_errorbar("下载失败", error_msg)

    def create_errorbar(self, title, content):
        InfoBar.error(title, content, position=InfoBarPosition.TOP_RIGHT, duration=5000, parent=self.parent or self)

    def _compare_versions(self, v1, v2):
        """
        改进的版本比对：支持 v0.3.5 > v0.3.5-beta
        规则：如果数字部分相同，有后缀的（预发布版）小于无后缀的（正式版）
        """
        import re

        def split_version(v):
            # 提取前面的数字部分和后面的后缀部分
            # 如 "0.3.5-beta" -> ([0, 3, 5], "-beta")
            match = re.match(r'^v?([\d.]+)(.*)', v.strip().lower())
            if not match:
                return [], ""
            nums = [int(x) for x in match.group(1).split('.') if x]
            suffix = match.group(2)
            return nums, suffix

        try:
            p1_nums, p1_suffix = split_version(v1)
            p2_nums, p2_suffix = split_version(v2)

            # 1. 首先比较数字部分 [0, 3, 5]
            if p1_nums != p2_nums:
                return (p1_nums > p2_nums) - (p1_nums < p2_nums)

            # 2. 如果数字相同，检查后缀
            # 原则：无后缀 > 有后缀 (正式版 > 预览版)
            if not p1_suffix and p2_suffix:
                return 1
            if p1_suffix and not p2_suffix:
                return -1

            # 3. 如果都有后缀，按字母序比较 (如 beta < rc)
            return (p1_suffix > p2_suffix) - (p1_suffix < p2_suffix)

        except Exception:
            # 后备方案：纯字符串比较
            return (v1 > v2) - (v1 < v2)