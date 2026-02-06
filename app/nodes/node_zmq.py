# -*- coding: utf-8 -*-
import traceback
import zmq
from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from loguru import logger

try:
    import orjson as json
except ImportError:
    import json


class NodeZmqTransceiver(QThread):
    stream_data_received = pyqtSignal(dict)
    intervention_requested = pyqtSignal(dict)
    connection_lost = pyqtSignal(str)

    def __init__(self, ip, pub_port, svc_port):
        super().__init__()
        self.ip = ip
        self.pub_port = pub_port
        self.svc_port = svc_port
        self._running = True  # 使用内部私有变量
        self._response_queue = []
        self._mutex = QMutex()

        self._context = None
        self._sub_socket = None
        self._svc_socket = None

    def send_intervention_response(self, response_data: dict):
        self._mutex.lock()
        self._response_queue.append(response_data)
        self._mutex.unlock()

    def run(self):
        # 初始化 Context 和 Sockets
        self._context = zmq.Context()

        # 核心设置：LINGER 设为 0，防止关闭时挂起
        self._sub_socket = self._context.socket(zmq.SUB)
        self._sub_socket.setsockopt(zmq.LINGER, 0)
        self._sub_socket.setsockopt(zmq.SUBSCRIBE, b"")
        self._sub_socket.connect(f"tcp://{self.ip}:{self.pub_port}")

        self._svc_socket = self._context.socket(zmq.PAIR)
        self._svc_socket.setsockopt(zmq.LINGER, 0)
        self._svc_socket.connect(f"tcp://{self.ip}:{self.svc_port}")

        # ==========================================
        # 发送握手信号
        # ==========================================
        try:
            # 稍微 sleep 极短时间确保物理连接建立（可选，zmq connect 通常是非阻塞的）
            self.msleep(10)
            handshake_msg = {"type": "handshake"}
            # 发送握手信号
            self._svc_socket.send_json(handshake_msg)
        except Exception as e:
            logger.exception(f"Failed to send handshake: {e}")

        # 使用 Poller 同时监听两个 socket
        poller = zmq.Poller()
        poller.register(self._sub_socket, zmq.POLLIN)
        poller.register(self._svc_socket, zmq.POLLIN)
        # 使用更严谨的循环判断
        while self._running and not self.isInterruptionRequested():
            try:
                # 1. 检查发送队列
                self._check_and_send_responses()

                # 2. 轮询接收 (超时 100ms)
                socks = dict(poller.poll(0))

                if not self._running: break

                if self._sub_socket in socks:
                    msg = self._sub_socket.recv_json(flags=zmq.NOBLOCK)
                    if msg.get("type") == "stream_data":
                        self.stream_data_received.emit(msg.get("payload"))

                if self._svc_socket in socks:
                    msg = self._svc_socket.recv_json(flags=zmq.NOBLOCK)
                    if msg.get("type") == "intervention_request":
                        self.intervention_requested.emit(msg.get("payload"))

            except zmq.ContextTerminated:
                break
            except zmq.Again:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"ZMQ Loop Error: {e}")
                break

        self._cleanup()

    def _check_and_send_responses(self):
        self._mutex.lock()
        if not self._response_queue:
            self._mutex.unlock()
            return

        data = self._response_queue.pop(0)
        self._mutex.unlock()

        msg = {"type": "intervention_response", "payload": data}
        try:
            # 使用 NOBLOCK 确保在关闭瞬间不会卡死
            self._svc_socket.send_json(msg, flags=zmq.NOBLOCK)
        except Exception as e:
            logger.exception(f"Send failed: {e}")

    def stop(self):
        """安全停止线程"""
        self._running = False
        self.requestInterruption()

        if not self.wait(500):
            logger.warning("Thread wait timeout, forcing socket closure.")
            self._cleanup()

        self.wait()

    def _cleanup(self):
        """清理资源，注意顺序：Socket -> Context"""
        try:
            if self._sub_socket:
                self._sub_socket.close(linger=0)
                self._sub_socket = None
            if self._svc_socket:
                self._svc_socket.close(linger=0)
                self._svc_socket = None
            if self._context:
                self._context.term()  # term 比 destroy 更温和
                self._context = None
        except Exception as e:
            logger.exception(f"Cleanup info: {e}")