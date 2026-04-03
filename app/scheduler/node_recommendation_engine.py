import colorsys
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

from PyQt5.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal

from app.components.base import ArgumentType, BaseComponent
from app.scan_components import ComponentScanner
from app.utils.utils import resource_path


class RecommendationStatsManager:
    def __init__(self):
        self.stats_file = Path("./canvas_files/recommend_stats.json")
        self._load_stats()

    def _load_stats(self):
        if self.stats_file.exists():
            try:
                data = json.loads(self.stats_file.read_text(encoding='utf-8'))
                self.global_usage = data.get("global_usage", {})  # {full_path: count}
                self.pair_usage = data.get("pair_usage", {})     # {"src||dst": count}
            except:
                self.global_usage = {}
                self.pair_usage = {}
        else:
            self.global_usage = {}
            self.pair_usage = {}

    def save_stats(self):
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "global_usage": self.global_usage,
            "pair_usage": self.pair_usage
        }
        self.stats_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

    def record_connection(self, src_full_path: str, dst_full_path: str):
        # 全局使用
        self.global_usage[dst_full_path] = self.global_usage.get(dst_full_path, 0) + 1
        # 成对使用
        key = f"{src_full_path}||{dst_full_path}"
        self.pair_usage[key] = self.pair_usage.get(key, 0) + 1
        self.save_stats()

    def get_pair_score(self, src: str, dst: str) -> int:
        return self.pair_usage.get(f"{src}||{dst}", 0)

    def get_global_score(self, dst: str) -> int:
        return self.global_usage.get(dst, 0)


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
    def __init__(self):
        self._input_to_components: Dict[ArgumentType, List[str]] = defaultdict(list)
        self._recommendation_cache: Dict[str, List] = {}
        self._stats_manager = RecommendationStatsManager()  # ← 将由 GalleryPage 注入

    def _build_index(self, component_map: Dict[str, BaseComponent]):
        self._input_to_components.clear()
        self.component_map = component_map
        for full_path, comp_cls in self.component_map.items():
            for port in comp_cls.inputs:
                self._input_to_components[port.type].append(full_path)
        self._input_to_components = self._input_to_components | {k: list(set(v)) for k, v in self._input_to_components.items()}

    def get_recommendations_sync(self, node_full_path: str):
        comp_cls = ComponentScanner().get_component(node_full_path)
        if not comp_cls:
            return []

        grouped_recommendations = []
        output_ports = comp_cls.outputs

        for idx, out_port in enumerate(output_ports):
            out_type = out_port.type
            hue = (idx * 60) % 360
            r, g, b = colorsys.hls_to_rgb(hue / 360, 0.85, 0.7)
            color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            candidates = self._input_to_components.get(out_type, [])
            scored_list = []

            for fp in candidates:
                if fp == node_full_path:
                    continue
                cls = self.component_map[fp]
                name = getattr(cls, 'name', cls.__name__)

                # === 新增：计算智能得分 ===
                score = 1  # 基础分（类型兼容）
                if self._stats_manager:
                    # 成对连接频率（高权重）
                    pair_score = self._stats_manager.get_pair_score(node_full_path, fp)
                    # 全局使用频率（低权重）
                    global_score = min(self._stats_manager.get_global_score(fp), 5)
                    score += pair_score * 10 + global_score
                scored_list.append((score, name, fp))

            # === 按得分降序 + 名称升序排序 ===
            scored_list.sort(key=lambda x: (-x[0], x[1]))

            # 取 top 3~5
            rec_list = [(name, fp) for _, name, fp in scored_list[:10]]
            if rec_list:
                grouped_recommendations.append((
                    out_port.name,
                    out_port.label,
                    color_hex,
                    rec_list
                ))

        self._recommendation_cache[node_full_path] = grouped_recommendations
        return grouped_recommendations