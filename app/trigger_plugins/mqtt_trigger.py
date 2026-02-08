# -*- coding: utf-8 -*-
import threading
import paho.mqtt.client as mqtt
from loguru import logger

from app.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin
from app.components.base import PropertyType


class MqttManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()
    _client = None
    _topic_map = {}  # 格式: {topic: {node_id: callback}}

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MqttManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        super().__init__("MQTT")

        # 实际使用中，Host和Port通常配置在全局设置里，这里为了演示简化处理
        # 你可以根据需要修改初始化逻辑，或者支持动态连接
        self.broker_host = "127.0.0.1"
        self.broker_port = 1883

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        try:
            # 尝试连接（建议做成异步或放在单独线程，防止阻塞启动）
            # self._client.connect(self.broker_host, self.broker_port, 60)
            # self._client.loop_start()
            logger.info("MQTT Manager 已初始化 (需配置连接)")
        except Exception as e:
            logger.error(f"MQTT 初始化失败: {e}")

        self._initialized = True

    def _ensure_connection(self, host, port):
        # 简易的单例连接管理
        if not self._client.is_connected():
            try:
                self._client.connect(host, int(port), 60)
                self._client.loop_start()
                logger.info(f"MQTT 已连接到 {host}:{port}")
            except Exception as e:
                logger.error(f"MQTT 连接失败: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        logger.info(f"MQTT Connected with result code {rc}")
        # 重连后重新订阅所有 topic
        for topic in self._topic_map.keys():
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        logger.debug(f"[MQTT] 收到消息 {topic}: {payload}")

        if topic in self._topic_map:
            # 广播给该 Topic 下所有的节点
            for node_id, callback in self._topic_map[topic].items():
                try:
                    # 将 payload 传回给回调
                    threading.Thread(target=callback, kwargs={"payload": payload}).start()
                except Exception as e:
                    logger.error(f"[MQTT] 回调执行失败 {node_id}: {e}")

    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        topic = kwargs.get("topic")
        host = kwargs.get("host", "127.0.0.1")
        port = kwargs.get("port", 1883)

        if not topic:
            return

        self._ensure_connection(host, port)

        if topic not in self._topic_map:
            self._topic_map[topic] = {}
            self._client.subscribe(topic)

        self._topic_map[topic][node_id] = callback

        self._register_in_mapping(canvas_name, node_id)
        logger.info(f"[MQTT] 节点 {node_id} 监听 Topic: {topic}")

    def remove_trigger(self, node_id: str):
        # 需要遍历查找该 node_id 属于哪个 topic
        target_topic = None
        for topic, nodes in self._topic_map.items():
            if node_id in nodes:
                del nodes[node_id]
                target_topic = topic
                self._unregister_from_mapping(node_id)
                logger.info(f"[MQTT] 节点 {node_id} 已移除")
                break

        # 如果该 topic 没有节点监听了，可以取消订阅
        if target_topic and not self._topic_map[target_topic]:
            del self._topic_map[target_topic]
            self._client.unsubscribe(target_topic)

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()


class MqttTriggerPlugin(BaseTriggerPlugin):
    NAME = "MQTT 消息"
    manager = MqttManager()

    def get_properties(self, parent_node=None):
        return {
            "mqtt_host": {
                "type": PropertyType.TEXT,
                "label": "Broker 地址",
                "default": "127.0.0.1"
            },
            "mqtt_port": {
                "type": PropertyType.INT,
                "label": "端口",
                "default": 1883
            },
            "mqtt_topic": {
                "type": PropertyType.TEXT,
                "label": "订阅 Topic",
                "default": "home/sensor/#"
            }
        }

    def activate(self, canvas_name, node_id, callback, properties):
        host = properties.get("mqtt_host")
        port = properties.get("mqtt_port")
        topic = properties.get("mqtt_topic")

        if topic:
            self.manager.add_trigger(
                canvas_name=canvas_name,
                node_id=node_id,
                callback=callback,
                host=host,
                port=port,
                topic=topic
            )