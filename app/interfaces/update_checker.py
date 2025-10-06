import os
import subprocess
import sys
import time
import shutil
import zipfile

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QProgressDialog, QWidget
from qfluentwidgets import Dialog, InfoBar, InfoBarPosition, InfoBarIcon

from app.utils.config import Settings
from app.utils.threading_utils import AsyncUpdateChecker, DownloadThread
from app.utils.utils import resource_path


class UpdateChecker(QWidget):
    """支持 GitHub 和 Gitee 的独立更新检查类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        cfg = Settings.get_instance()
        self.platform = cfg.patch_platform
        self.repo = cfg.github_repo
        self.token = cfg.github_token
        self.progress_dialog = None
        self.download_thread = None
        self.update_zip_path = None  # 新增：记录 ZIP 路径

    def _show_update_dialog(self, latest_release):
        update_notes = latest_release.get("body", "无更新说明")
        update_datetime = latest_release.get("created_at")
        msg_box = Dialog(
            "版本更新",
            f"发现新版本 {latest_release['tag_name']}，当前版本 {self.current_version}，是否更新？\n\n更新时间: {update_datetime}\n\n更新内容：\n{update_notes}",
            self
        )
        msg_box.yesButton.setText("更新")
        msg_box.cancelButton.setText("取消")

        if msg_box.exec():
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
                # 注意：GitCode 的 attach_files 链接需根据实际 API 调整
                # 此处假设你已上传 .zip 到 Release
                pass
            self.create_errorbar("未找到 ZIP 格式的更新包，请联系开发者")
            return

        self.update_zip_path = f"update_{latest_release['tag_name']}.zip"

        # 创建进度条
        self.progress_dialog = QProgressDialog("正在下载更新...", "取消", 0, 100, self)
        self.progress_dialog.setWindowTitle("更新进度")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self._cancel_download)

        # 启动下载线程
        self.download_thread = DownloadThread(update_url, self.update_zip_path, self.token)
        self.download_thread.progress_signal.connect(self.progress_dialog.setValue)
        self.download_thread.finished_signal.connect(self._handle_download_finished)
        self.download_thread.error_signal.connect(self._handle_download_error)
        self.download_thread.start()

    def _cancel_download(self):
        if self.download_thread:
            self.download_thread.is_canceled = True
            self.download_thread = None
        if self.progress_dialog:
            self.progress_dialog.close()

    def _handle_download_finished(self, file_path):
        """处理 ZIP 下载完成（--onedir 模式）"""
        self.progress_dialog.close()
        if self.download_thread:
            self.download_thread.deleteLater()
            self.download_thread = None

        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        temp_extract_dir = os.path.join(app_dir, "update_temp")

        try:
            # 1. 解压 ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # 2. 确定源目录（处理 ZIP 内嵌套文件夹的情况）
            extracted_items = os.listdir(temp_extract_dir)
            if len(extracted_items) == 1:
                candidate = os.path.join(temp_extract_dir, extracted_items[0])
                if os.path.isdir(candidate):
                    source_dir = candidate
                else:
                    source_dir = temp_extract_dir
            else:
                source_dir = temp_extract_dir

            # 3. 生成更新脚本（覆盖文件 + 重启）
            bat_content = f'''@echo off
timeout /t 3 >nul
echo 正在应用更新...
xcopy /E /Y /H /R "{source_dir}\\*" "{app_dir}\\"
rd /s /q "{temp_extract_dir}"
del /f /q "{os.path.abspath(file_path)}"
echo 更新完成，正在重启...
start "" "{os.path.abspath(sys.argv[0])}"
exit
'''

            script_path = os.path.join(app_dir, "update.bat")
            # 使用 gbk 编码确保中文路径兼容
            with open(script_path, "w", encoding="gbk") as f:
                f.write(bat_content)

            # 4. 执行更新脚本
            subprocess.Popen([script_path], shell=True)
            self.create_successbar("更新成功", "程序将在几秒后自动重启！")
            time.sleep(2)
            sys.exit()

        except Exception as e:
            import traceback
            error_msg = f"更新失败：{str(e)}\n{traceback.format_exc()}"
            self.create_errorbar("更新失败", str(e))
            # 清理临时文件
            for path in [temp_extract_dir, file_path]:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    elif os.path.isfile(path):
                        os.remove(path)
                except:
                    pass

    def _handle_download_error(self, error_msg):
        """处理下载错误"""
        self.progress_dialog.close()
        if self.download_thread:
            self.download_thread.deleteLater()
            self.download_thread = None

        self.create_errorbar(title="下载失败", content=error_msg)

        if self.update_zip_path and os.path.exists(self.update_zip_path):
            try:
                os.remove(self.update_zip_path)
            except:
                pass

    def _get_current_version(self):
        """获取当前版本号"""
        try:
            import json
            with open(resource_path("versions.json"), "r", encoding="utf-8") as f:
                release_list = json.load(f)
                release_list = sorted(release_list, key=lambda x: x['publishDate'], reverse=True)
                return release_list[0]['version']
        except Exception as e:
            print(f"获取版本失败：{e}")
            return "0.0.0"

    def check_update(self):
        """检查更新入口方法（支持 GitHub/Gitee）"""
        self.async_checker = AsyncUpdateChecker(self)
        self.async_checker.finished.connect(self._on_check_finished)
        self.async_checker.error.connect(self.create_errorbar)
        self.async_checker.start()

    def _on_check_finished(self, latest_release):
        """异步请求完成回调"""
        if latest_release:
            latest_version = latest_release.get("tag_name")
            if (
                latest_version
                and self._compare_versions(latest_version, self.current_version) > 0
            ):
                self._show_update_dialog(latest_release)
            else:
                self.create_infobar("当前已是最新版本")
        else:
            self.create_errorbar("未获取到最新版本号")

    def create_infobar(self, title: str, content: str = "", duration: int = 5000):
        info = InfoBar(
            icon=InfoBarIcon.INFORMATION,
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM,
            duration=duration,  # won't disappear automatically
            parent=self
        )
        info.show()

    def create_errorbar(self, title: str, content: str = "", duration: int = 5000):
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM,
            duration=duration,  # won't disappear automatically
            parent=self
        )

    def _compare_versions(self, v1, v2):
        """版本号比较逻辑（适用于 GitHub/Gitee）"""
        try:
            parts1 = list(map(int, v1.split('.')))
            parts2 = list(map(int, v2.split('.')))
            return (parts1 > parts2) - (parts1 < parts2)
        except ValueError:
            return (v1 > v2) - (v1 < v2)

    def _on_download_canceled(self):
        self.progress_dialog.close()

    def _show_error(self, title, message):
        """显示错误提示"""
        QMessageBox.critical(None, title, message)

    def create_successbar(self, title: str, content: str = "", duration: int = 5000):
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM,
            duration=duration,  # won't disappear automatically
            parent=self
        )
