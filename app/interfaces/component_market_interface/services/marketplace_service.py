# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Dict, List, Optional

from pypinyin import lazy_pinyin


@dataclass(frozen=True)
class SortOption:
    key: str
    label: str


class MarketplaceService:
    SORT_OPTIONS = [
        SortOption("newest", "最新发布"),
        SortOption("updated", "最近更新"),
        SortOption("name", "名称 A-Z"),
    ]

    def option_label_to_key(self, label: str) -> str:
        for option in self.SORT_OPTIONS:
            if option.label == label:
                return option.key
        return "newest"

    def normalize_item(self, item: dict, data_type: str) -> dict:
        item = item or {}
        plugin_id = str(item.get("plugin_id") or item.get("unique_id") or item.get("组件id") or item.get("uuid") or "")
        name = str(item.get("name") or item.get("组件名称") or item.get("canvas_name") or "未命名插件")
        author = str(item.get("author") or item.get("创建人") or item.get("creator") or "未知")
        category = str(item.get("category") or item.get("组件类别") or ("画布" if data_type == "canvas" else "常规"))
        description = str(item.get("description") or item.get("组件描述") or "暂无描述")
        version = str(item.get("version") or item.get("版本号") or "1.0.0")
        created_at = str(item.get("created_at") or item.get("创建时间") or "")
        updated_at = str(item.get("updated_at") or item.get("最后修改时间") or created_at)

        normalized = dict(item)
        normalized.update(
            {
                "plugin_id": plugin_id,
                "unique_id": plugin_id,
                "name": name,
                "author": author,
                "category": category,
                "description": description,
                "version": version,
                "created_at": created_at,
                "updated_at": updated_at,
                "data_type": data_type,
            }
        )
        return normalized

    def normalize_items(self, items: List[dict], data_type: str) -> List[dict]:
        return [self.normalize_item(item, data_type) for item in (items or [])]

    def compare_status(self, cloud_item: dict, local_items: List[dict]) -> str:
        local_map = {str(i.get("plugin_id") or i.get("unique_id")): i for i in local_items}
        plugin_id = str(cloud_item.get("plugin_id") or cloud_item.get("unique_id"))
        local_item = local_map.get(plugin_id)
        if not local_item:
            return "new"

        cloud_version = str(cloud_item.get("version") or "0.0.0")
        local_version = str(local_item.get("version") or "0.0.0")

        cv = self._parse_version(cloud_version)
        lv = self._parse_version(local_version)
        if cv == lv:
            return "match"
        if cv < lv:
            return "old"
        return "diff"

    def sort_items(self, items: List[dict], sort_key: str) -> List[dict]:
        sorted_items = list(items or [])

        if sort_key == "updated":
            sorted_items.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
        elif sort_key == "name":
            sorted_items.sort(key=lambda x: str(x.get("name") or "").lower())
        else:
            sorted_items.sort(key=lambda x: str(x.get("created_at") or x.get("updated_at") or ""), reverse=True)

        return sorted_items

    def filter_items(
        self,
        items: List[dict],
        query: str,
        selected_author: str,
        selected_category: str,
        all_author_label: str = "所有作者",
        all_category_label: str = "全部分类",
    ) -> List[dict]:
        query = (query or "").strip().lower()
        result = []

        for item in items or []:
            name = str(item.get("name") or "")
            name_lower = name.lower()
            pinyin = "".join(lazy_pinyin(name)).lower()
            if query and query not in name_lower and query not in pinyin:
                continue

            author = str(item.get("author") or "未知")
            if selected_author and selected_author != all_author_label and author != selected_author:
                continue

            category = str(item.get("category") or "常规")
            if selected_category and selected_category != all_category_label and category != selected_category:
                continue

            result.append(item)

        return result

    def extract_filter_options(self, items: List[dict]) -> Dict[str, List[str]]:
        authors = sorted({str(i.get("author") or "未知") for i in items or []})
        categories = sorted({str(i.get("category") or "常规") for i in items or []})
        return {"authors": authors, "categories": categories}

    def group_by_category(self, items: List[dict]) -> Dict[str, List[dict]]:
        grouped: Dict[str, List[dict]] = {}
        for item in items or []:
            category = str(item.get("category") or "常规")
            grouped.setdefault(category, []).append(item)
        return grouped

    def summary_stats(self, market_items: List[dict], local_items: List[dict]) -> dict:
        market_total = len(market_items or [])
        local_total = len(local_items or [])
        updatable = 0
        local_map = {str(i.get("plugin_id") or i.get("unique_id")): i for i in (local_items or [])}
        for item in market_items or []:
            local_item = local_map.get(str(item.get("plugin_id") or item.get("unique_id")))
            if not local_item:
                continue
            if self._parse_version(str(item.get("version") or "0.0.0")) > self._parse_version(str(local_item.get("version") or "0.0.0")):
                updatable += 1

        return {
            "market_total": market_total,
            "local_total": local_total,
            "updatable": updatable,
        }

    @staticmethod
    def _parse_version(version: str):
        parts = []
        for part in str(version).replace("-", ".").split("."):
            try:
                parts.append(int(part))
            except ValueError:
                continue
        return tuple(parts) if parts else (0,)

