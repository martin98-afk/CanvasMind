from collections import defaultdict
from typing import Dict, Set, List, Tuple
from app.components.base import ArgumentType, BaseComponent
from PyQt5.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from typing import Optional


class RecommendationSignals(QObject):
    finished = pyqtSignal(list)  # [(name, full_path), ...]
    error = pyqtSignal(str)


class RecommendationTask(QRunnable):
    def __init__(self, engine, node_full_path: Optional[str]):
        super().__init__()
        self.engine = engine
        self.node_full_path = node_full_path
        self.signals = RecommendationSignals()

    @pyqtSlot()
    def run(self):
        try:
            if not self.node_full_path:
                self.signals.finished.emit([])
                return
            result = self.engine.get_recommendations_sync(self.node_full_path)
            self.signals.finished.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))


class NodeRecommendationEngine:
    def __init__(self, component_map: Dict[str, BaseComponent]):
        self.component_map = component_map
        # 预构建：output_type → [full_path]
        self._output_to_components: Dict[ArgumentType, List[str]] = defaultdict(list)
        # 预构建：input_type → [full_path]
        self._input_to_components: Dict[ArgumentType, List[str]] = defaultdict(list)
        # 缓存：full_path → 推荐列表（避免重复计算）
        self._recommendation_cache: Dict[str, List[Tuple[str, str]]] = {}

        self._build_index()

    def _build_index(self):
        """离线构建类型索引，O(N) 一次完成"""
        for full_path, comp_cls in self.component_map.items():
            # 输入类型索引
            for port in comp_cls.inputs:
                self._input_to_components[port.type].append(full_path)

            # 输出类型索引（用于反向查找）
            for port in comp_cls.outputs:
                self._output_to_components[port.type].append(full_path)

    def get_recommendations_sync(self, node_full_path: str) -> List[Tuple[str, str]]:
        """
        同步版本（供异步任务调用）
        """
        if node_full_path in self._recommendation_cache:
            return self._recommendation_cache[node_full_path]

        comp_cls = self.component_map.get(node_full_path)
        if not comp_cls:
            return []

        # 获取当前节点的输出类型
        output_types: Set[ArgumentType] = {port.type for port in comp_cls.outputs}

        candidate_full_paths = set()
        for out_type in output_types:
            # 找出所有输入端口包含该类型的组件
            candidates = self._input_to_components.get(out_type, [])
            candidate_full_paths.update(candidates)

        # 排除自己
        candidate_full_paths.discard(node_full_path)

        # 构建 (name, full_path) 列表
        result = []
        for fp in list(candidate_full_paths)[:10]:  # 限制数量
            cls = self.component_map[fp]
            name = getattr(cls, 'name', cls.__name__)
            result.append((name, fp))

        self._recommendation_cache[node_full_path] = result
        return result