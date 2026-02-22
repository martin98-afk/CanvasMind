# -*- coding: utf-8 -*-
import threading
import time
import imaplib
import email
from email.header import decode_header
from loguru import logger

from app.plugins.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin
from app.components.base import PropertyType


class EmailTriggerManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EmailTriggerManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        super().__init__("EmailMonitor")
        self.running = True
        self.tasks = {}  # {node_id: {config: dict, callback: func}}

        # 启动轮询线程
        self.worker_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.worker_thread.start()

        self._initialized = True

    def _decode_str(self, s):
        value, charset = decode_header(s)[0]
        if charset:
            return value.decode(charset)
        return value if isinstance(value, str) else value.decode()

    def _check_email(self, node_id, config, callback):
        mail = None
        try:
            # 连接 IMAP
            server = config['email_server']
            port = int(config.get('email_port', 993))
            username = config['email_username']
            password = config['email_password']
            if not server or not username or not password:
                return
            mail = imaplib.IMAP4_SSL(server, port)
            mail.login(username, password)
            mail.select("inbox")

            # 搜索未读邮件
            status, messages = mail.search(None, 'UNSEEN')
            if status != "OK": return

            email_ids = messages[0].split()
            if not email_ids: return

            # 处理每一封未读邮件
            for e_id in email_ids:
                status, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = self._decode_str(msg.get("Subject"))
                        from_ = self._decode_str(msg.get("From"))

                        logger.info(f"[Email] 节点 {node_id} 收到邮件: {subject}")

                        # 触发回调
                        threading.Thread(target=callback, kwargs={
                            "subject": subject,
                            "from": from_,
                            "content_type": msg.get_content_type()
                        }).start()

                        # 标记为已读 (或根据需求保持未读)
                        # mail.store(e_id, '+FLAGS', '\\Seen')

        except Exception as e:
            logger.error(f"[Email] 检查失败 {node_id}: {e}")
        finally:
            if mail:
                try:
                    mail.logout()
                except:
                    pass

    def _polling_loop(self):
        while self.running:
            # 复制一份 keys 防止遍历时修改
            current_nodes = list(self.tasks.keys())

            for node_id in current_nodes:
                task = self.tasks.get(node_id)
                if task:
                    # 在线程中执行检查，防止阻塞主轮询循环
                    threading.Thread(
                        target=self._check_email,
                        args=(node_id, task['config'], task['callback'])
                    ).start()

            # 轮询间隔，建议不要太频繁
            time.sleep(30)

    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        self.tasks[node_id] = {
            "config": kwargs,
            "callback": callback
        }
        self._register_in_mapping(canvas_name, node_id)
        logger.info(f"[Email] 节点 {node_id} 开始监控邮箱: {kwargs.get('username')}")

    def remove_trigger(self, node_id: str):
        if node_id in self.tasks:
            del self.tasks[node_id]
            self._unregister_from_mapping(node_id)
            logger.info(f"[Email] 节点 {node_id} 监控已移除")

    def stop(self):
        self.running = False


class EmailTriggerPlugin(BaseTriggerPlugin):
    NAME = "收到邮件时"
    manager = EmailTriggerManager()

    def get_properties(self, parent_node=None):
        return {
            "email_server": {
                "type": PropertyType.TEXT,
                "label": "IMAP 服务器",
                "default": "imap.gmail.com"
            },
            "email_port": {
                "type": PropertyType.INT,
                "label": "端口",
                "default": 993
            },
            "email_username": {
                "type": PropertyType.TEXT,
                "label": "邮箱账号",
                "default": ""
            },
            "email_password": {
                "type": PropertyType.TEXT,
                "label": "密码/应用授权码",
                "default": ""
            }
        }

    def activate(self, canvas_name, node, callback, properties):
        self.manager.add_trigger(
            canvas_name=canvas_name,
            node_id=node.persistent_id,
            callback=callback,
            **properties
        )