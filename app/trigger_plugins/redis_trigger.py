# -*- coding: utf-8 -*-
import threading
import redis
from loguru import logger

from app.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin
from app.components.base import PropertyType


class RedisTriggerManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RedisTriggerManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        super().__init__("RedisPubSub")

        self.redis_client = None
        self.pubsub = None
        self.listen_thread = None
        self.running = False
        self.channel_map = {}  # {channel_name: {node_id: callback}}

        self._initialized = True

    def _connect_redis(self, host, port, password, db):
        # 简单处理：如果连接参数变了，这里逻辑需要更复杂（支持多连接池）
        # 这里假设系统连接同一个 Redis
        if self.redis_client is None:
            try:
                self.redis_client = redis.Redis(
                    host=host, port=int(port), password=password, db=int(db), decode_responses=True
                )
                self.pubsub = self.redis_client.pubsub()
                self.running = True
                self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
                self.listen_thread.start()
                logger.info(f"Redis 连接成功: {host}:{port}")
            except Exception as e:
                logger.error(f"Redis 连接失败: {e}")

    def _listen_loop(self):
        while self.running and self.pubsub:
            try:
                message = self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    channel = message['channel']
                    data = message['data']
                    self._dispatch(channel, data)
            except Exception as e:
                logger.error(f"[Redis] 监听循环错误: {e}")
                # 简单的重连机制可以加在这里

    def _dispatch(self, channel, data):
        if channel in self.channel_map:
            logger.debug(f"[Redis] 收到频道 {channel} 消息: {data}")
            for node_id, callback in self.channel_map[channel].items():
                try:
                    threading.Thread(target=callback, kwargs={"data": data}).start()
                except Exception as e:
                    logger.error(f"[Redis] 回调执行失败 {node_id}: {e}")

    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        host = kwargs.get("redis_host", "localhost")
        port = kwargs.get("redis_port", 6379)
        password = kwargs.get("redis_password", None)
        channel = kwargs.get("redis_channel")

        if not channel: return

        # 确保连接
        self._connect_redis(host, port, password, 0)

        if channel not in self.channel_map:
            self.channel_map[channel] = {}
            if self.pubsub:
                self.pubsub.subscribe(channel)

        self.channel_map[channel][node_id] = callback
        self._register_in_mapping(canvas_name, node_id)
        logger.info(f"[Redis] 节点 {node_id} 订阅频道: {channel}")

    def remove_trigger(self, node_id: str):
        target_channel = None
        for channel, nodes in self.channel_map.items():
            if node_id in nodes:
                del nodes[node_id]
                target_channel = channel
                self._unregister_from_mapping(node_id)
                break

        if target_channel and not self.channel_map[target_channel]:
            del self.channel_map[target_channel]
            if self.pubsub:
                self.pubsub.unsubscribe(target_channel)
            logger.info(f"[Redis] 频道 {target_channel} 无监听者，已取消订阅")

    def stop(self):
        self.running = False
        if self.pubsub:
            self.pubsub.close()
        if self.redis_client:
            self.redis_client.close()


class RedisTriggerPlugin(BaseTriggerPlugin):
    NAME = "Redis 订阅"
    manager = RedisTriggerManager()

    def get_properties(self, parent_node=None):
        return {
            "redis_host": {
                "type": PropertyType.TEXT,
                "label": "Redis 地址",
                "default": "127.0.0.1"
            },
            "redis_port": {
                "type": PropertyType.INT,
                "label": "端口",
                "default": 6379
            },
            "redis_password": {
                "type": PropertyType.TEXT,
                "label": "密码",
                "default": ""
            },
            "redis_channel": {
                "type": PropertyType.TEXT,
                "label": "频道 (Channel)",
                "default": "app_events"
            }
        }

    def activate(self, canvas_name, node, callback, properties):
        self.manager.add_trigger(
            canvas_name=canvas_name,
            node_id=node.persistent_id,
            callback=callback,
            redis_host=properties.get("redis_host"),
            redis_port=properties.get("redis_port"),
            redis_password=properties.get("redis_password"),
            redis_channel=properties.get("redis_channel")
        )