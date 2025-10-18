# -*- coding: utf-8 -*-
import asyncio
import json
import os
from pathlib import Path
from urllib.request import urlopen

import aiohttp
import requests
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QRectF, Qt
from PyQt5.QtGui import QPainter, QImage
from loguru import logger


class ThumbnailGenerator(QThread):
    """异步生成缩略图的线程类"""
    finished = pyqtSignal(str)  # 发送生成的文件路径

    def __init__(self, graph, workflow_path):
        super().__init__()
        self.graph = graph
        self.workflow_path = workflow_path

    def run(self):
        """在后台线程中生成缩略图"""
        try:
            # 构造预览图路径：xxx.workflow.json → xxx.png
            base_name = os.path.splitext(os.path.splitext(self.workflow_path)[0])[0]  # 去掉 .workflow.json
            png_path = base_name + ".png"

            # 获取场景和边界
            scene = self.graph.viewer().scene()
            rect = QRectF()
            for node in self.graph.all_nodes():
                item_rect = node.view.sceneBoundingRect()
                rect = rect.united(item_rect)

            if rect.isEmpty():
                # 如果没有节点，创建一个空白图
                image = QImage(800, 600, QImage.Format_ARGB32)
                image.fill(Qt.white)
            else:
                # 扩展一点边距，避免裁剪
                rect.adjust(-100, -100, 90, 90)
                image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
                image.fill(Qt.white)  # 背景设为白色（可选）

                painter = QPainter(image)
                # 将场景渲染到 QImage
                scene.render(painter, target=QRectF(image.rect()), source=rect)
                painter.end()

            # 保存图像
            image.save(png_path, "PNG")
            self.finished.emit(png_path)
        except Exception as e:
            logger.error(f"缩略图生成失败: {str(e)}")
            self.finished.emit("")


class WorkflowLoader(QThread):
    """异步加载工作流的线程类"""
    finished = pyqtSignal(dict, dict, dict, dict)  # graph_data, runtime_data, node_status_data
    progress = pyqtSignal(str)  # 添加进度信号

    def __init__(self, file_path, graph, node_type_map):
        super().__init__()
        self.file_path = file_path
        self.graph = graph
        self.node_type_map = node_type_map

    def run(self):
        """在后台线程中加载工作流"""
        try:
            self.progress.emit("正在读取工作流文件...")
            with open(self.file_path, 'r', encoding='utf-8') as f:
                full_data = json.load(f)

            graph_data = full_data.get("graph", {})
            runtime_data = full_data.get("runtime", {})
            global_variable = full_data.get("global_variable", {})
            # 准备节点状态数据
            node_status_data = {}
            nodes_data = graph_data.get("nodes", {})
            total_nodes = len(nodes_data)
            
            self.progress.emit(f"正在处理 {total_nodes} 个节点...")
            
            for index, (node_id, node_data) in enumerate(nodes_data.items()):
                # 发送进度更新
                if index % 10 == 0:  # 每10个节点更新一次进度
                    self.progress.emit(f"正在处理节点 {index}/{total_nodes}...")
                    
                node_type = node_data.get("type_", "")
                if node_type in self.node_type_map.values():
                    # 找到对应的 full_path
                    full_path = None
                    for path, node_type_name in self.node_type_map.items():
                        if node_type_name == node_type:
                            full_path = path
                            break

                    if full_path:
                        node_name = node_data.get("name", "Unknown")
                        stable_key = f"{full_path}||{node_name}"
                        node_status_data[stable_key] = {
                            key: value.get(stable_key)
                            for key, value in runtime_data.items() if key not in ("environment", "environment_exe", "node_id2stable_key")
                        }| {"custom_property": node_data.get("custom", {})}

            self.progress.emit("节点处理完成，准备加载...")
            self.finished.emit(graph_data, runtime_data, node_status_data, global_variable)
        except Exception as e:
            logger.error(f"工作流加载失败: {str(e)}")
            self.finished.emit({}, {}, {}, {})


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
                    print("GitHub API 响应:", await resp.json())
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


# === 后台扫描器（避免阻塞 UI）===
class WorkflowScanner(QObject):
    finished = pyqtSignal(list)  # List[Path]

    def __init__(self, workflow_dir: Path):
        super().__init__()
        self.workflow_dir = workflow_dir

    def scan(self):
        try:
            files = list(self.workflow_dir.glob("*.workflow.json"))
            # 按修改时间倒序（在后台线程中排序）
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            self.finished.emit(files)
        except Exception as e:
            logger.error(f"扫描 workflow 目录失败: {e}")
            self.finished.emit([])
