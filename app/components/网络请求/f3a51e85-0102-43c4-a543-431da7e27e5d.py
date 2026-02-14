# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class APIPaginationComponent(BaseComponent):
    """API 分页查询组件 - 自动处理分页，聚合所有结果"""
    name = "API 分页查询器"
    category = "网络请求"
    description = "自动处理 API 分页，支持 offset/limit、page/size、cursor 等分页模式，聚合所有结果"
    requirements = "httpx>=0.23.0"
    inputs = [
        PortDefinition(name="base_url", label="基础 URL", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="initial_params", label="初始参数", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="headers", label="请求头", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="all_results", label="所有结果", type=ArgumentType.JSON),
        PortDefinition(name="total_count", label="总数量", type=ArgumentType.INT),
        PortDefinition(name="page_info", label="分页信息", type=ArgumentType.JSON),
    ]

    properties = {
        "pagination_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="page",
            label="分页模式",
            choices=["page", "offset", "cursor", "link_header"]
        ),
        "page_param": PropertyDefinition(
            type=PropertyType.TEXT,
            default="page",
            label="页码参数名",
        ),
        "size_param": PropertyDefinition(
            type=PropertyType.TEXT,
            default="size",
            label="每页大小参数名",
        ),
        "page_size": PropertyDefinition(
            type=PropertyType.INT,
            default=50,
            label="每页大小",
        ),
        "max_pages": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="最大页数",
        ),
        "result_path": PropertyDefinition(
            type=PropertyType.TEXT,
            default="data",
            label="结果路径（JSON 路径）",
        ),
        "total_path": PropertyDefinition(
            type=PropertyType.TEXT,
            default="total",
            label="总数路径（JSON 路径）",
        ),
        "rate_limit": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.5,
            label="请求间隔（秒）",
        ),
        "timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="超时时间（秒）",
        ),
    }

    def run(self, params, inputs=None):
        import httpx
        import time
        base_url = inputs.base_url.strip()
        initial_params = inputs.initial_params or {}
        headers = inputs.headers or {}
        
        pagination_mode = params.pagination_mode
        page_param = params.page_param
        size_param = params.size_param
        page_size = params.page_size
        max_pages = params.max_pages
        result_path = params.result_path
        total_path = params.total_path
        rate_limit = params.rate_limit
        timeout = params.timeout
        
        all_results = []
        total_count = 0
        current_page = 1
        
        try:
            while current_page <= max_pages:
                # 构建当前页的参数
                page_params = initial_params.copy()
                
                if pagination_mode == "page":
                    page_params[page_param] = current_page
                    page_params[size_param] = page_size
                elif pagination_mode == "offset":
                    page_params["offset"] = (current_page - 1) * page_size
                    page_params["limit"] = page_size
                elif pagination_mode == "cursor":
                    if current_page > 1:
                        # 需要从上一页响应中获取 cursor
                        page_params["cursor"] = self._extract_cursor(all_results[-1] if all_results else None)
                
                self.logger.info(f"🔍 查询第 {current_page} 页: {base_url}")
                
                response = httpx.get(
                    base_url,
                    params=page_params,
                    headers=headers,
                    timeout=timeout,
                    verify=True,
                    follow_redirects=True
                )
                
                response.raise_for_status()
                data = response.json()
                
                # 提取结果
                results = self._extract_by_path(data, result_path)
                if not results and current_page == 1:
                    # 如果第一页没有结果，尝试直接使用根对象
                    results = data if isinstance(data, list) else []
                
                if not results:
                    self.logger.info(f"⚠️ 第 {current_page} 页无数据，停止分页")
                    break
                
                all_results.extend(results)
                
                # 提取总数
                if current_page == 1:
                    total_count = self._extract_by_path(data, total_path) or len(results)
                
                self.logger.info(f"✓ 第 {current_page} 页: 获得 {len(results)} 项 (累计: {len(all_results)}/{total_count})")
                
                # 检查是否还有更多数据
                if len(results) < page_size or len(all_results) >= total_count:
                    break
                
                current_page += 1
                
                # 速率限制
                if current_page <= max_pages:
                    time.sleep(rate_limit)
            
            page_info = {
                "current_page": current_page,
                "total_pages": min(max_pages, (total_count + page_size - 1) // page_size) if total_count else 1,
                "items_per_page": page_size,
                "total_items": total_count,
                "actual_pages": current_page
            }
            
            self.logger.info(f"✅ 分页查询完成: 共获取 {len(all_results)} 项")
            
            return {
                "all_results": all_results,
                "total_count": total_count,
                "page_info": page_info
            }
            
        except Exception as e:
            self.logger.error(f"❌ 分页查询失败: {str(e)}")
            raise
    
    def _extract_by_path(self, data, path):
        """根据路径提取数据"""
        if not path or path == ".":
            return data
        
        keys = path.split('.')
        result = data
        for key in keys:
            if isinstance(result, dict) and key in result:
                result = result[key]
            elif isinstance(result, list) and key.isdigit():
                result = result[int(key)]
            else:
                return None
        return result
    
    def _extract_cursor(self, data):
        """从数据中提取 cursor（需要根据实际 API 调整）"""
        if isinstance(data, dict):
            return data.get('next_cursor') or data.get('cursor')
        return None
