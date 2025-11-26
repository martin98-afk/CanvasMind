import os
import subprocess
import sys
import time
import shutil
import zipfile
import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QApplication, QProgressDialog
from qfluentwidgets import InfoBar, InfoBarPosition, InfoBarIcon, PushButton, qconfig, PrimaryPushButton

from app.utils.config import Settings
from app.utils.threading_utils import AsyncUpdateChecker, DownloadThread
from app.utils.utils import resource_path


class UpdateChecker(QWidget):
    """支持 GitHub 和 Gitee 的独立更新类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.cfg = Settings.get_instance()
        self.platform = self.cfg.patch_platform.value
        self.repo = self.cfg.github_repo.value
        self.token = self.cfg.github_token.value
        self.current_version = self.cfg.current_version
        self.progress_dialog = None
        self.download_thread = None
        self.update_zip_path = None  # 记录 ZIP 路径
        self.update_info = None      # 记录待更新信息 (latest_release)

    def _show_update_infobar(self, latest_release):
        """使用 InfoBar 显示更新提示"""
        latest_version = latest_release.get("tag_name", "未知")
        update_notes = latest_release.get("body", "无更新说明")
        update_datetime = latest_release.get("created_at", "未知")

        # 创建一个 InfoBar，包含标题、内容和一个确认更新的按钮
        info_bar = InfoBar(
            icon=InfoBarIcon.INFORMATION,
            title=f"发现新版本 {latest_version} (当前: {self.current_version})",
            content=f"更新时间: {update_datetime}\n\n更新内容：\n{update_notes[:200]}...", # 限制内容长度
            orient=Qt.BottomRightCorner,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT, # 或者 InfoBarPosition.TOP, BOTTOM 等
            duration=-1,  # 持久显示，直到用户操作或程序处理
            parent=self.parent # InfoBar 的父窗口
        )

        # 添加一个确认更新的按钮
        update_button = PrimaryPushButton("立即更新")
        update_button.clicked.connect(lambda: self._on_update_confirmed(latest_release, info_bar))
        info_bar.widgetLayout.addWidget(update_button, 0, Qt.AlignRight)

        info_bar.show()

    def _on_update_confirmed(self, latest_release, info_bar):
        """用户点击“立即更新”按钮后的处理"""
        info_bar.close() # 关闭 InfoBar
        self._start_download(latest_release)

    def _start_download(self, latest_release):
        """开始下载 ZIP 更新包（适配 --onedir）"""
        update_url = None
        for asset in latest_release["assets"]:
            if asset["name"].endswith(".zip"):
                update_url = asset["browser_download_url"]
                break

        if not update_url:
            # 兼容 GitCode（如有需要）
            if self.platform == "gitcode":
                tag_name = latest_release["tag_name"]
                pass
            self.create_errorbar("未找到 ZIP 格式的更新包，请联系开发者")
            return
        qconfig.set(self.cfg.current_version, latest_release['tag_name'])
        self.cfg.save()
        self.update_zip_path = f"update_{latest_release['tag_name']}.zip"

        # 创建 QProgressDialog
        self.progress_dialog = QProgressDialog("正在下载更新...", "取消", 0, 100, self)
        self.progress_dialog.setWindowTitle("更新进度")
        self.progress_dialog.setWindowModality(Qt.WindowModal) # 模态
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self._cancel_download)

        # 启动下载线程
        self.download_thread = DownloadThread(update_url, self.update_zip_path, self.token)
        self.download_thread.progress_signal.connect(self._update_progress)
        self.download_thread.finished_signal.connect(self._handle_download_finished)
        self.download_thread.error_signal.connect(self._handle_download_error)
        self.download_thread.start()

    def _update_progress(self, value):
        """更新 QProgressDialog 的进度"""
        if self.progress_dialog:
            self.progress_dialog.setValue(value)

    def _cancel_download(self):
        """取消下载"""
        if self.download_thread:
            self.download_thread.is_canceled = True
            self.download_thread = None
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

    def _handle_download_finished(self, file_path):
        """处理 ZIP 下载完成（适配 PyInstaller --onedir，ZIP 内含 main/ 目录）"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        if self.download_thread:
            self.download_thread.deleteLater()
            self.download_thread = None

        app_dir = Path(sys.argv[0]).parent.resolve()
        exe_name = Path(sys.argv[0]).name  # e.g., "main.exe"
        temp_extract_dir = Path(tempfile.mkdtemp(prefix="cm_update_", dir=app_dir))

        try:
            # 1. 解压 ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # 2. 定位内容目录：ZIP 解压后应有一个子目录（如 "main"），其内含 main.exe 和 _internal
            extracted_items = [p for p in temp_extract_dir.iterdir()]
            content_dir = None

            # 情况1: 直接是有效根（罕见，但兼容）
            if (temp_extract_dir / exe_name).exists() and (temp_extract_dir / "_internal").is_dir():
                content_dir = temp_extract_dir
            # 情况2: 有一个子目录，且该子目录是有效根
            elif len(extracted_items) == 1 and extracted_items[0].is_dir():
                candidate = extracted_items[0]
                if (candidate / exe_name).exists() and (candidate / "_internal").is_dir():
                    content_dir = candidate

            if content_dir is None:
                raise RuntimeError(
                    f"更新包结构无效：未找到包含 {exe_name} 和 _internal 的目录。"
                    f" 解压内容: {[p.name for p in extracted_items]}"
                )

            # 3. 生成更新脚本（使用 pathlib 转 str 保证兼容）
            log_file = app_dir / "update.log"
            bat_content = f'''@echo off
    chcp 65001 >nul
    setlocal enabledelayedexpansion

    set "APP_EXE={exe_name}"
    set "SOURCE_DIR={content_dir.resolve()}"
    set "TARGET_DIR={app_dir.resolve()}"
    set "ZIP_FILE={Path(file_path).resolve()}"
    set "TEMP_DIR={temp_extract_dir.resolve()}"
    set "LOG_FILE={log_file.resolve()}"

    echo [%date% %time%] Update script started. >> "!LOG_FILE!"
    echo [%date% %time%] Source: !SOURCE_DIR! >> "!LOG_FILE!"
    echo [%date% %time%] Target: !TARGET_DIR! >> "!LOG_FILE!"
    echo [%date% %time%] Waiting for !APP_EXE! to exit... >> "!LOG_FILE!"

    :wait_loop
    tasklist /FI "IMAGENAME eq !APP_EXE!" 2>nul | find /I /N "!APP_EXE!" >nul
    if not errorlevel 1 (
        echo [%date% %time%] !APP_EXE! is still running, waiting... >> "!LOG_FILE!"
        timeout /t 2 /nobreak >nul
        goto wait_loop
    )

    echo [%date% %time%] Main process exited. Copying files... >> "!LOG_FILE!"

    xcopy "!SOURCE_DIR!" "!TARGET_DIR!" /E /Y /H /R /I >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] ERROR: xcopy failed. >> "!LOG_FILE!"
        echo [%date% %time%] Please check permissions and file locks. >> "!LOG_FILE!"
        pause
        exit /b 1
    )

    echo [%date% %time%] Copy succeeded. Cleaning up... >> "!LOG_FILE!"

    rd /s /q "!TEMP_DIR!" >nul 2>&1
    del /f /q "!ZIP_FILE!" >nul 2>&1

    echo [%date% %time%] Cleanup done. Restarting application... >> "!LOG_FILE!"
    start "" "!TARGET_DIR!\\!APP_EXE!"
    exit /b 0
    '''

            script_path = app_dir / "update.bat"
            script_path.write_text(bat_content, encoding="gbk")

            # 启动更新脚本
            subprocess.Popen([str(script_path)], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.create_successbar("更新已启动", "程序即将自动重启以应用更新！")
            QApplication.processEvents()
            time.sleep(1)
            os._exit(0)

        except Exception as e:
            import traceback
            error_msg = f"更新失败：{str(e)}\n{traceback.format_exc()}"
            self.create_errorbar("更新失败", str(e))
            # 清理
            try:
                if temp_extract_dir.exists():
                    shutil.rmtree(temp_extract_dir, ignore_errors=True)
                if Path(file_path).exists():
                    Path(file_path).unlink()
            except Exception:
                pass

    def _handle_download_error(self, error_msg):
        """处理下载错误"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        if self.download_thread:
            self.download_thread.deleteLater()
            self.download_thread = None

        self.create_errorbar("下载失败", error_msg)

        if self.update_zip_path and os.path.exists(self.update_zip_path):
            try:
                os.remove(self.update_zip_path)
            except:
                pass

    def check_update(self):
        """检查更新入口方法（支持 GitHub/Gitee）"""
        self.async_checker = AsyncUpdateChecker(self)
        self.async_checker.finished.connect(self._on_check_finished)
        self.async_checker.error.connect(lambda msg: self.create_errorbar("检查更新失败", msg))
        self.async_checker.start()

    def _on_check_finished(self, latest_release):
        """异步请求完成回调"""
        if latest_release:
            latest_version = latest_release.get("tag_name")
            print(f"当前版本：{self.current_version}，最新版本：{latest_version}")
            if (
                latest_version
                and self._compare_versions(latest_version, self.current_version) > 0
            ):
                self._show_update_infobar(latest_release)
            else:
                self.create_infobar("当前已是最新版本")
        else:
            self.create_errorbar("未获取到最新版本信息")

    def create_infobar(self, title: str, content: str = "", duration: int = 3000):
        """创建信息提示条"""
        info = InfoBar(
            icon=InfoBarIcon.INFORMATION,
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=duration,
            parent=self
        )
        info.show()

    def create_errorbar(self, title: str, content: str = ""):
        """创建错误提示条"""
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT, # 或 InfoBarPosition.BOTTOM
            duration=5000,  # 显示5秒
            parent=self
        )

    def _compare_versions(self, v1, v2):
        """版本号比较逻辑（适用于 GitHub/Gitee）"""
        try:
            # 移除可能的前缀（如 'v'）
            v1_clean = v1.lstrip('vV')
            v2_clean = v2.lstrip('vV')
            parts1 = list(map(int, v1_clean.split('.')))
            parts2 = list(map(int, v2_clean.split('.')))
            # 确保两个版本号的段数相同，用0补齐短的
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            return (parts1 > parts2) - (parts1 < parts2)
        except ValueError:
            # 如果无法转换为整数，则按字符串比较
            return (v1 > v2) - (v1 < v2)

    def create_successbar(self, title: str, content: str = ""):
        """创建成功提示条"""
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT, # 或 InfoBarPosition.BOTTOM
            duration=3000,  # 显示3秒
            parent=self
        )