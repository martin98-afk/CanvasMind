# -*- coding: utf-8 -*-
import traceback

import zmq
from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from loguru import logger

try:
    import orjson as json
except ImportError:
    import json


# =========================================================================
# UI 端 ZMQ 通信线程 (负责接收流数据 + 处理人工干预双向通信)
# =========================================================================
class NodeZmqTransceiver(QThread):
    """
    负责在后台线程与节点进行 ZMQ 通信
    1. SUB 端口: 接收流式数据
    2. PAIR 端口: 处理人工干预的双向同步通信
    """
    stream_data_received = pyqtSignal(dict)  # 收到流数据 -> 刷新 UI
    intervention_requested = pyqtSignal(dict)  # 收到干预请求 -> 弹窗
    connection_lost = pyqtSignal(str)

    def __init__(self, ip, pub_port, svc_port):
        super().__init__()
        self.ip = ip
        self.pub_port = pub_port
        self.svc_port = svc_port
        self.running = True

        # 线程安全队列，用于主线程向子线程发送“人工确认后的回复数据”
        self._response_queue = []
        self._mutex = QMutex()

        self._context = None
        self._sub_socket = None
        self._svc_socket = None

    def send_intervention_response(self, response_data: dict):
        """供主线程调用：发送用户确认后的数据回给节点"""
        self._mutex.lock()
        self._response_queue.append(response_data)
        self._mutex.unlock()

    def run(self):
        self._context = zmq.Context()
        # 1. 数据流通道 (SUB)
        self._sub_socket = self._context.socket(zmq.SUB)
        self._sub_socket.setsockopt(zmq.SUBSCRIBE, b"")
        self._sub_socket.set_hwm(1000)
        self._sub_socket.connect(f"tcp://{self.ip}:{self.pub_port}")

        # 2. 交互通道 (PAIR)
        self._svc_socket = self._context.socket(zmq.PAIR)
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
            logger.info(f"UI sent handshake to {self.pub_port}/{self.svc_port}")
        except Exception as e:
            logger.error(f"Failed to send handshake: {e}")

        # 使用 Poller 同时监听两个 socket
        poller = zmq.Poller()
        poller.register(self._sub_socket, zmq.POLLIN)
        poller.register(self._svc_socket, zmq.POLLIN)

        while self.running:
            try:
                # A. 检查是否有待发送的回复 (主线程 UI -> 节点)
                self._check_and_send_responses()

                # B. 轮询网络事件 (超时 50ms，保证能及时处理发送队列和退出信号)
                socks = dict(poller.poll(50))
                # --- Case 1: 收到流数据 ---
                if self._sub_socket in socks and socks[self._sub_socket] == zmq.POLLIN:
                    # 使用 recv_string 避免 bytes 解码问题，或者直接 recv_json
                    try:
                        msg = self._sub_socket.recv_json()
                        if msg.get("type") == "stream_data":
                            self.stream_data_received.emit(msg.get("payload"))
                    except Exception:
                        traceback.print_exc()

                # --- Case 2: 收到干预请求 ---
                if self._svc_socket in socks and socks[self._svc_socket] == zmq.POLLIN:
                    try:
                        msg = self._svc_socket.recv_json()
                        if msg.get("type") == "intervention_request":
                            self.intervention_requested.emit(msg.get("payload"))
                    except Exception:
                        pass

                if self.isInterruptionRequested():
                    break

            except zmq.ZMQError as e:
                self.connection_lost.emit(str(e))
                break
            except Exception as e:
                logger.exception(f"ZMQ Thread Error: {e}")

        self._cleanup()

    def _check_and_send_responses(self):
        """检查是否有用户回复需要发回节点"""
        self._mutex.lock()
        if self._response_queue:
            # 取出最早的一条回复
            data = self._response_queue.pop(0)
            msg = {
                "type": "intervention_response",
                "payload": data
            }
            try:
                self._svc_socket.send(json.dumps(msg))
            except Exception as e:
                logger.exception(f"Failed to send response back to node: {e}")
        self._mutex.unlock()

    def stop(self):
        self.running = False
        self.requestInterruption()
        self.wait()

    def _cleanup(self):
        if self._sub_socket: self._sub_socket.close()
        if self._svc_socket: self._svc_socket.close()
        if self._context: self._context.term()
