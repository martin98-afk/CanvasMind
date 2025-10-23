import os
import subprocess
import sys
import time
import shutil
import zipfile
import tempfile

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QApplication, QProgressDialog
from qfluentwidgets import InfoBar, InfoBarPosition, InfoBarIcon, PushButton

from app.utils.config import Settings
from app.utils.threading_utils import AsyncUpdateChecker, DownloadThread
from app.utils.utils import resource_path


class UpdateChecker(QWidget):
    """支持 GitHub 和 Gitee 的独立更新类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        cfg = Settings.get_instance()
        self.platform = cfg.patch_platform.value
        self.repo = cfg.github_repo.value
        self.token = cfg.github_token.value
        self.current_version = cfg.current_version.value
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
        update_button = PushButton("立即更新")
        update_button.clicked.connect(lambda: self._on_update_confirmed(latest_release, info_bar))
        info_bar.addWidget(update_button)

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
                # 注意：GitCode 的 attach_files 链接需根据实际 API 调整
                # 此处假设你已上传 .zip 到 Release
                pass
            self.create_errorbar("未找到 ZIP 格式的更新包，请联系开发者")
            return

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
        """处理 ZIP 下载完成（--onedir 模式）"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        if self.download_thread:
            self.download_thread.deleteLater()
            self.download_thread = None

        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        # 使用临时目录，避免与现有文件冲突
        temp_extract_dir = tempfile.mkdtemp(prefix="cm_update_", dir=app_dir)

        try:
            # 1. 解压 ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # 2. 确定源目录（处理 ZIP 内嵌套文件夹的情况）
            # 遍历解压后的目录，找到真正的应用根目录
            # 假设根目录包含 main.py 或可执行文件同名的 .exe 文件
            exe_name = os.path.basename(sys.argv[0])
            source_dir = temp_extract_dir
            # 寻找可能的两层目录
            for _ in range(2): # 最多查找两层
                subdirs = [d for d in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, d))]
                if len(subdirs) == 1:
                    candidate = os.path.join(source_dir, subdirs[0])
                    # 检查候选目录是否包含预期的根文件
                    if exe_name in os.listdir(candidate) or 'main.py' in os.listdir(candidate):
                         source_dir = candidate
                         break
                    else:
                        # 如果第一层不是根目录，继续检查它内部
                        source_dir = candidate
                else:
                    # 如果有多个子目录或没有子目录，则当前 source_dir 可能就是目标
                    break

            # 3. 生成更新脚本（覆盖文件 + 重启）
            # Windows Batch Script
            bat_content = f'''@echo off
echo Waiting for main process to exit...
timeout /t 3 /nobreak >nul
echo Starting update process...
echo Source: "{source_dir}"
echo Target: "{app_dir}"

if not exist "{source_dir}" (
    echo Error: Source directory does not exist: "{source_dir}"
    pause
    exit /b 1
)

if not exist "{app_dir}" (
    echo Error: Target directory does not exist: "{app_dir}"
    pause
    exit /b 1
)

echo Attempting to copy files...
xcopy "{source_dir}" "{app_dir}" /E /Y /H /R /I
if errorlevel 1 (
    echo Error during xcopy. Check permissions and files.
    pause
    exit /b 1
)

echo Copy completed. Cleaning up...
rd /s /q "{temp_extract_dir}"
del /f /q "{os.path.abspath(file_path)}"
echo Cleanup done.
echo Restarting application...
start "" "{os.path.abspath(sys.argv[0])}"
exit
'''

            script_path = os.path.join(app_dir, "update.bat")
            # 使用 gbk 编码确保中文路径兼容
            with open(script_path, "w", encoding="gbk") as f:
                f.write(bat_content)

            subprocess.Popen([script_path], shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE) # 创建新控制台窗口便于查看日志
            self.create_successbar("更新已启动", "程序即将自动重启以应用更新！")
            time.sleep(2)
            QApplication.quit() # 或者 sys.exit()，取决于你的应用结构
            # os._exit(0) # 强制退出，不执行清理代码

        except Exception as e:
            import traceback
            error_msg = f"更新失败：{str(e)}\n{traceback.format_exc()}"
            self.create_errorbar("更新失败", str(e))
            # 清理临时文件
            for path in [temp_extract_dir]:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                except:
                    pass
            # 删除下载的 ZIP 文件
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except:
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