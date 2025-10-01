import asyncio
import os
import pickle
import subprocess
import traceback
from collections import defaultdict
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from urllib.request import urlopen

import aiohttp
import requests
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot, QThread


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)  # 保持兼容，可发送任意对象
    # 新增信号用于批量执行
    node_finished = pyqtSignal(str, object)  # (node_id, result)
    node_error = pyqtSignal(str)        # (node_id, error_message)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.signals = WorkerSignals()
        if fn is None:
            self.signals.error.emit("输入函数为空！")
            return

        self.args = args
        self.policy = kwargs.pop("policy", "extend")
        self.return_type = kwargs.pop("return_type", "Dict")
        self.kwargs = kwargs

        # ✅ 新增：是否启用进度回调模式
        self.use_progress_callback = kwargs.pop("use_progress_callback", False)

        try:
            if isinstance(fn, list):
                self.fn = [ft.call for ft in fn]
            elif "batch" in kwargs and kwargs["batch"]:
                self.fn = fn.call_batch
            else:
                self.fn = fn
        except:
            self.fn = fn

    @pyqtSlot()
    def run(self):
        try:
            if isinstance(self.fn, list):
                # ========== 旧逻辑：执行多个函数 ==========
                if self.return_type == "Dict":
                    result = defaultdict(list)
                    for fetcher in self.fn:
                        if fetcher is None:
                            continue
                        r = fetcher(*self.args, **self.kwargs)
                        if r and self.policy == "extend":
                            for t, pts in r.items():
                                result[t].extend(pts)
                        elif r and self.policy == "update":
                            for t, pts in r.items():
                                result[t] = pts
                        self.signals.progress.emit(r)  # 发射每个函数的结果
                elif self.return_type == "List":
                    result = [fetcher(*self.args, **self.kwargs) for fetcher in self.fn]
                self.signals.finished.emit(result)

            else:
                # ========== 新逻辑：执行单个函数，支持进度回调 ==========
                if self.use_progress_callback:
                    # 注入进度回调函数
                    def progress_callback(*args, **kwargs):
                        # 支持传入单个值或元组
                        if len(args) == 1:
                            self.signals.progress.emit(args[0])
                        else:
                            self.signals.progress.emit(args)  # 打包成元组

                    # 把回调函数传入 kwargs
                    self.kwargs['progress_callback'] = progress_callback

                # 执行函数
                result = self.fn(*self.args, **self.kwargs)
                self.signals.finished.emit(result)

        except Exception as e:
            err_msg = traceback.format_exc()
            self.signals.error.emit(err_msg)


# ----------------------------
# 节点列表执行器（用于批量异步执行）
# ----------------------------
class NodeListExecutor(QRunnable):
    def __init__(self, main_window, nodes, python_exe=None):
        super().__init__()
        self.signals = WorkerSignals()
        self.main_window = main_window
        self.nodes = nodes
        self.python_exe = python_exe

    @pyqtSlot()
    def run(self):
        try:
            node_outputs = {}
            for node in self.nodes:
                try:
                    # 执行单个节点
                    if self.python_exe is None:
                        output = node.execute_sync(
                            self.main_window.component_map.get(node.FULL_PATH),
                            use_separate_env=False
                        )
                    else:
                        output = node.execute_sync(
                            self.main_window.component_map.get(node.FULL_PATH),
                            python_executable=self.python_exe
                        )
                    node_outputs[node.id] = output
                    self.signals.node_finished.emit(node.id, output)
                except Exception as e:
                    # 捕获单个节点的错误
                    self.signals.node_error.emit(node.id)
                    # 可选择继续执行或停止
                    return
            self.signals.finished.emit(None)
        except Exception as e:
            self.signals.error.emit()


class PythonDownloadWorker(QThread):
    progress = pyqtSignal(str)    # 实时日志输出
    finished = pyqtSignal(bool, Path)  # 完成，是否成功 + 文件路径

    def __init__(self, url: str, save_path: Path):
        super().__init__()
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            self.progress.emit(f"开始下载 {self.url} ...")
            with urlopen(self.url) as resp, open(self.save_path, "wb") as f:
                total = resp.length or 0
                downloaded = 0
                chunk_size = 1024 * 32
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        self.progress.emit(f"下载进度: {pct:.1f}%")
            self.progress.emit("下载完成 ✅")
            self.finished.emit(True, self.save_path)
        except Exception as e:
            self.progress.emit(f"[错误] 下载失败: {e}")
            self.finished.emit(False, self.save_path)


class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)  # 进度信号
    finished_signal = pyqtSignal(str)  # 完成信号（返回文件路径）
    error_signal = pyqtSignal(str)  # 错误信号
    canceled_signal = pyqtSignal()  # 取消信号（新增）

    def __init__(self, url, file_path, token):
        super().__init__()
        self.url = url
        self.file_path = file_path
        self.headers = {"Authorization": token} if token else {}
        self.is_canceled = False  # 取消标志位
        self.session = requests.Session()  # 使用 Session 以便关闭连接

    def run(self):
        try:
            response = self.session.get(self.url, headers=self.headers, stream=True, timeout=10)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(self.file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if self.is_canceled:  # 每次读取前检查取消标志
                        f.close()
                        os.remove(self.file_path)  # 删除不完整文件
                        self.canceled_signal.emit()
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress_signal.emit(progress)

            self.finished_signal.emit(self.file_path)
        except Exception as e:
            if not self.is_canceled:  # 非取消情况才触发错误信号
                self.error_signal.emit(str(e))
        finally:
            self.session.close()  # 确保释放网络资源


class AsyncUpdateChecker(QThread):
    finished = pyqtSignal(object)  # 返回 latest_release 或 None
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo = parent.repo
        self.platform = parent.platform
        self.token = parent.token

    async def fetch_github(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        headers = headers | {"Authorization": f"token {self.token}"} if self.token else headers
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    self.error.emit(f"GitHub API 请求失败：{resp.status}")
                    return None

    async def fetch_gitee(self):
        headers = {"Authorization": self.token} if self.token else {}
        url = f"https://gitee.com/api/v5/repos/{self.repo}/releases/latest"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    self.error.emit(f"Gitee API 请求失败：{resp.status}")
                    return None

    async def fetch_gitcode(self):
        headers = {"Authorization": self.token} if self.token else {}
        url = f"https://gitcode.com/api/v5/repos/{self.repo}/releases/latest"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    self.error.emit(f"Gitee API 请求失败：{resp.status}")
                    return None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if self.platform == "github":
                result = loop.run_until_complete(self.fetch_github())
            elif self.platform == "gitee":
                result = loop.run_until_complete(self.fetch_gitee())
            elif self.platform == "gitcode":
                result = loop.run_until_complete(self.fetch_gitcode())
            else:
                result = None
                self.error.emit("不支持的平台")
        except Exception as e:
            self.error.emit(str(e))
            result = None
        finally:
            self.finished.emit(result)
