# -*- coding: utf-8 -*-
"""
Scrapling 网页抓取组件

基于 Scrapling 框架的网页抓取组件，支持：
- 基础 HTTP 请求 (Fetcher)
- 隐形模式 (StealthyFetcher) - 绕过 Cloudflare 等反爬虫
- 动态网站抓取 (DynamicFetcher) - 使用 Playwright 浏览器自动化
- CSS/XPath 选择器解析
- 自适应元素查找 - 网站结构变化时自动重新定位元素
- 代理轮换
- 会话管理

参考文档: https://github.com/D4Vinci/Scrapling
"""

import warnings
warnings.filterwarnings("ignore")

# 项目组件导入 - 动态加载 base.py
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

# Scrapling 框架导入
from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
from scrapling.fetchers import FetcherSession, StealthySession, DynamicSession
from scrapling.parser import Selector
from loguru import logger

# 尝试导入可选的异步支持
try:
    from scrapling.fetchers import AsyncFetcher, AsyncStealthyFetcher, AsyncDynamicFetcher
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False

import base64
from typing import Any, Dict, List, Optional


class ScraplingComponent(BaseComponent):
    """Scrapling 网页抓取组件"""
    
    name = "Scrapling 网页抓取"
    category = "网络请求"
    description = (
        "基于 Scrapling 框架的智能网页抓取组件，支持基础请求、隐形模式和浏览器自动化，"
        "内置 CSS/XPath 选择器和自适应元素查找功能"
    )
    requirements = "scrapling[fetchers]>=0.4.0"
    
    inputs = [
        PortDefinition(
            name="html_content",
            label="HTML 内容",
            type=ArgumentType.TEXT,
            connection=ConnectionType.SINGLE,
            description="可选：直接输入 HTML 内容进行解析，无需抓取 URL"
        ),
    ]
    
    outputs = [
        PortDefinition(
            name="result",
            label="抓取结果",
            type=ArgumentType.JSON,
            description="返回抓取到的数据，格式为列表或字典"
        ),
        PortDefinition(
            name="raw_html",
            label="原始 HTML",
            type=ArgumentType.TEXT,
            description="返回原始 HTML 内容"
        ),
        PortDefinition(
            name="url",
            label="当前 URL",
            type=ArgumentType.TEXT,
            description="返回当前页面的 URL"
        ),
        PortDefinition(
            name="status",
            label="状态信息",
            type=ArgumentType.JSON,
            description="返回状态信息，包含状态码、响应头等"
        ),
    ]
    
    properties = {
        # 抓取模式配置
        "fetch_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="basic",
            label="抓取模式",
            choices=["basic", "stealth", "dynamic"],
            description="basic: 基础HTTP请求; stealth: 隐形模式(绕过反爬); dynamic: 浏览器自动化(JavaScript渲染)"
        ),
        
        # URL 配置
        "url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="https://httpbin.org/html",
            label="目标 URL",
            description="要抓取的网页地址"
        ),
        
        "method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="GET",
            label="请求方法",
            choices=["GET", "POST"]
        ),
        
        # 选择器配置
        "selector": PropertyDefinition(
            type=PropertyType.TEXT,
            default=".quote",
            label="CSS/XPath 选择器",
            description="CSS 选择器或 XPath，用于提取数据。例如：.product, //div[@class='item']"
        ),
        
        "selector_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="css",
            label="选择器类型",
            choices=["css", "xpath", "text", "regex"],
            description="选择器的解析方式"
        ),
        
        # 提取模式
        "extract_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="getall",
            label="提取模式",
            choices=["getall", "get", "getall_text", "get_text", "getall_attrs", "get_attr"],
            description="getall: 获取所有匹配元素; get: 获取第一个; getall_text: 获取所有文本; get_text: 获取第一个文本"
        ),
        
        "attribute": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="提取属性",
            description="当提取模式为 get_attr 时，指定要提取的属性名，如 href, src, text 等"
        ),
        
        # 自适应配置
        "adaptive": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="自适应模式",
            description="启用自适应元素查找，当网站结构变化时可自动重新定位元素"
        ),
        
        # 隐形模式配置
        "headless": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="无头模式",
            description="浏览器是否以无头模式运行（仅 dynamic 模式有效）"
        ),
        
        "solve_cloudflare": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="解决 Cloudflare",
            description="尝试自动解决 Cloudflare 验证（仅 stealth 模式有效）"
        ),
        
        "network_idle": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="等待网络空闲",
            description="等待网络请求完成后在进行抓取（适用于动态加载的页面）"
        ),
        
        # 浏览器配置
        "load_dom": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="加载 DOM",
            description="是否等待 DOM 加载完成（仅 dynamic 模式有效）"
        ),
        
        "disable_resources": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="禁用资源加载",
            description="禁用图片等资源加载以提升速度（仅 dynamic 模式有效）"
        ),
        
        # 伪装配置
        "impersonate": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="chrome",
            label="浏览器伪装",
            choices=["chrome", "firefox", "edge", "safari", "none"],
            description="模拟的浏览器类型"
        ),
        
        # 代理配置
        "use_proxy": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="使用代理",
            description="是否启用代理"
        ),
        
        "proxy_url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="代理地址",
            description="代理服务器地址，如 http://127.0.0.1:7890"
        ),
        
        # 请求配置
        "timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="超时时间（秒）",
        ),
        
        "verify_ssl": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="验证 SSL",
            description="是否验证 SSL 证书"
        ),
        
        # 请求头配置
        "headers": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="请求头",
            schema={
                "key": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="键",
                ),
                "value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="值",
                ),
            }
        ),
        
        # 请求参数配置
        "params": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="URL 参数",
            schema={
                "key": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="键",
                ),
                "value": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="值",
                ),
            }
        ),
        
        # 请求体配置
        "request_body": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="",
            label="请求体 (JSON)",
            description="POST 请求的请求体，支持 JSON 格式"
        ),
        
        # Stealthy 专用配置
        "stealthy_headers": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="伪装请求头",
            description="使用 stealthy 模式的伪装请求头"
        ),
        
        # 高级配置
        "follow_redirects": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="跟随重定向",
            description="是否自动跟随重定向"
        ),
        
        "http3": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="使用 HTTP/3",
            description="是否使用 HTTP/3 协议（仅 basic 模式有效）"
        ),
    }

    def run(self, params, inputs=None):
        """执行网页抓取"""
        
        # 获取输入的 HTML 内容（可选）
        html_content = inputs.html_content if inputs else None
        
        # 获取参数
        fetch_mode = params.fetch_mode
        url = params.url
        method = params.method
        selector = params.selector
        selector_type = params.selector_type
        extract_mode = params.extract_mode
        attribute = params.attribute
        adaptive = params.adaptive
        
        # 构建请求头
        headers = {}
        if params.headers:
            headers = {header.key: header.value for header in params.headers if header.key}
        
        # 构建 URL 参数
        url_params = {}
        if params.params:
            url_params = {param.key: param.value for param in params.params if param.key}
        
        # 解析请求体
        request_body = None
        if params.request_body and params.request_body.strip():
            import json
            try:
                request_body = json.loads(params.request_body)
            except json.JSONDecodeError:
                request_body = params.request_body
        
        # 代理配置
        proxy = None
        if params.use_proxy and params.proxy_url:
            proxy = params.proxy_url
        
        # 超时配置
        timeout = int(params.timeout) if params.timeout else 30
        
        # 结果存储
        result_data = {}
        raw_html = ""
        final_url = url
        status_info = {}
        
        try:
            # 模式1: 直接解析 HTML 内容
            if html_content and str(html_content).strip():
                self.logger.info(f"使用输入的 HTML 内容进行解析")
                page = Selector(html_content)
                raw_html = html_content
                final_url = url if url else "direct_html_input"
                
            # 模式2: 基础 HTTP 请求 (Fetcher)
            elif fetch_mode == "basic":
                self.logger.info(f"使用基础模式抓取: {url}")
                
                # 创建 Fetcher 实例并发送请求
                fetcher = Fetcher()
                
                # 构建请求参数
                request_kwargs = {
                    "url": url,
                    "timeout": timeout,
                    "verify": params.verify_ssl,
                    "follow_redirects": params.follow_redirects,
                }
                
                if headers:
                    request_kwargs["headers"] = headers
                if url_params:
                    request_kwargs["params"] = url_params
                if request_body:
                    request_kwargs["json"] = request_body
                if proxy:
                    request_kwargs["proxies"] = {"all://": proxy}
                if params.http3:
                    request_kwargs["http3"] = True
                
                # 设置浏览器伪装
                if params.impersonate and params.impersonate != "none":
                    request_kwargs["impersonate"] = params.impersonate
                
                # 根据请求方法调用不同的方法
                if method == "GET":
                    page = fetcher.get(**request_kwargs)
                elif method == "POST":
                    page = fetcher.post(**request_kwargs)
                elif method == "PUT":
                    page = fetcher.put(**request_kwargs)
                elif method == "DELETE":
                    page = fetcher.delete(**request_kwargs)
                else:
                    page = fetcher.get(**request_kwargs)
                
                raw_html = str(page.html_content) if hasattr(page, 'html_content') else str(page.text)
                final_url = str(page.url)
                status_info = {
                    "status_code": page.status,
                    "headers": dict(page.headers) if hasattr(page, 'headers') else {}
                }
            
            # 模式3: 隐形模式 (StealthyFetcher)
            elif fetch_mode == "stealth":
                self.logger.info(f"使用隐形模式抓取: {url}")
                
                # 检查是否安装了浏览器
                try:
                    fetch_kwargs = {
                        "url": url,
                        "timeout": timeout,
                        "headless": params.headless,
                    }
                    
                    if headers:
                        fetch_kwargs["headers"] = headers
                    if url_params:
                        fetch_kwargs["params"] = url_params
                    if request_body:
                        fetch_kwargs["data"] = request_body
                    if proxy:
                        fetch_kwargs["proxy"] = proxy
                    if params.solve_cloudflare:
                        fetch_kwargs["solve_cloudflare"] = True
                    if params.stealthy_headers:
                        fetch_kwargs["stealthy_headers"] = True
                    if params.network_idle:
                        fetch_kwargs["network_idle"] = True
                    
                    page = StealthyFetcher.fetch(**fetch_kwargs)
                    raw_html = str(page.html_content) if hasattr(page, 'html_content') else str(page.text)
                    final_url = str(page.url)
                    status_info = {
                        "mode": "stealth",
                        "headless": params.headless,
                        "solve_cloudflare": params.solve_cloudflare,
                    }
                except Exception as e:
                    if "Executable doesn't exist" in str(e) or "playwright" in str(e).lower():
                        raise RuntimeError(
                            "StealthyFetcher 需要安装浏览器。请运行: pip install scrapling[all] && scrapling install"
                        ) from e
                    raise
            
            # 模式4: 动态网站抓取 (DynamicFetcher)
            elif fetch_mode == "dynamic":
                self.logger.info(f"使用动态模式抓取: {url}")
                
                try:
                    fetch_kwargs = {
                        "url": url,
                        "timeout": timeout,
                        "headless": params.headless,
                        "load_dom": params.load_dom,
                    }
                    
                    if headers:
                        fetch_kwargs["headers"] = headers
                    if url_params:
                        fetch_kwargs["params"] = url_params
                    if request_body:
                        fetch_kwargs["data"] = request_body
                    if proxy:
                        fetch_kwargs["proxy"] = proxy
                    if params.disable_resources:
                        fetch_kwargs["disable_resources"] = True
                    if params.network_idle:
                        fetch_kwargs["network_idle"] = True
                    
                    page = DynamicFetcher.fetch(**fetch_kwargs)
                    raw_html = str(page.html_content) if hasattr(page, 'html_content') else str(page.text)
                    final_url = str(page.url)
                    status_info = {
                        "mode": "dynamic",
                        "headless": params.headless,
                        "load_dom": params.load_dom,
                    }
                except Exception as e:
                    if "Executable doesn't exist" in str(e) or "playwright" in str(e).lower():
                        raise RuntimeError(
                            "DynamicFetcher 需要安装浏览器。请运行: pip install scrapling[all] && scrapling install"
                        ) from e
                    raise
            
            else:
                raise ValueError(f"不支持的抓取模式: {fetch_mode}")
            
            # 执行选择器提取
            extracted_data = None
            if selector and selector.strip():
                self.logger.info(f"执行选择器: {selector} (类型: {selector_type}, 模式: {extract_mode})")
                
                # 根据选择器类型选择提取方法
                if selector_type == "css":
                    if extract_mode == "getall":
                        extracted_data = page.css(selector, adaptive=adaptive).getall()
                    elif extract_mode == "get":
                        extracted_data = page.css(selector, adaptive=adaptive).get()
                    elif extract_mode == "getall_text":
                        extracted_data = page.css(selector, adaptive=adaptive).getall_text()
                    elif extract_mode == "get_text":
                        extracted_data = page.css(selector, adaptive=adaptive).get_text()
                    elif extract_mode == "getall_attrs":
                        extracted_data = page.css(selector, adaptive=adaptive).getall_attrs(attribute or None)
                    elif extract_mode == "get_attr":
                        extracted_data = page.css(selector, adaptive=adaptive).get_attr(attribute or None)
                        
                elif selector_type == "xpath":
                    if extract_mode == "getall":
                        extracted_data = page.xpath(selector, adaptive=adaptive).getall()
                    elif extract_mode == "get":
                        extracted_data = page.xpath(selector, adaptive=adaptive).get()
                    elif extract_mode == "getall_text":
                        extracted_data = page.xpath(selector, adaptive=adaptive).getall_text()
                    elif extract_mode == "get_text":
                        extracted_data = page.xpath(selector, adaptive=adaptive).get_text()
                    elif extract_mode == "getall_attrs":
                        extracted_data = page.xpath(selector, adaptive=adaptive).getall_attrs(attribute or None)
                    elif extract_mode == "get_attr":
                        extracted_data = page.xpath(selector, adaptive=adaptive).get_attr(attribute or None)
                        
                elif selector_type == "text":
                    # 根据文本内容查找元素
                    if extract_mode == "getall":
                        extracted_data = page.find_by_text(selector)
                    elif extract_mode == "get":
                        result = page.find_by_text(selector)
                        extracted_data = result[0] if result else None
                        
                elif selector_type == "regex":
                    # 使用正则表达式提取
                    if extract_mode == "getall":
                        extracted_data = page.re(selector).getall()
                    elif extract_mode == "get":
                        extracted_data = page.re(selector).get()
                
                # 处理提取结果
                if extracted_data:
                    # 如果是单个元素或文本，转换为字典格式
                    if extract_mode in ["get", "get_text", "get_attr"]:
                        result_data = {"data": extracted_data}
                    else:
                        result_data = {"data": extracted_data, "count": len(extracted_data)}
                else:
                    result_data = {"data": None, "message": "未找到匹配元素"}
            else:
                # 没有选择器，返回整个页面
                result_data = {"message": "未配置选择器，返回整页内容"}
            
            # 更新状态信息
            if "status_code" not in status_info:
                status_info["status_code"] = page.status if hasattr(page, 'status') else 200
            status_info["fetch_mode"] = fetch_mode
            status_info["selector"] = selector if selector else "none"
            
            return {
                "result": result_data,
                "raw_html": raw_html,
                "url": final_url,
                "status": status_info
            }
            
        except Exception as e:
            self.logger.error(f"网页抓取失败: {str(e)}")
            raise


# ==================== 组件2: Scrapling 爬虫组件 ====================
class ScraplingSpiderComponent(BaseComponent):
    """Scrapling 爬虫组件 - 支持并发爬取和多页面导航"""
    
    name = "Scrapling 爬虫"
    category = "网络请求"
    description = (
        "基于 Scrapling Spider 框架的完整爬虫，支持并发爬取、多页面导航、"
        "暂停/恢复、代理轮换等高级功能"
    )
    requirements = "scrapling[fetchers]>=0.4.0"
    
    inputs = []
    
    outputs = [
        PortDefinition(
            name="items",
            label="抓取结果",
            type=ArgumentType.JSON,
            description="返回所有抓取到的数据项"
        ),
        PortDefinition(
            name="count",
            label="抓取数量",
            type=ArgumentType.INT,
            description="返回抓取的数据项数量"
        ),
    ]
    
    properties = {
        "start_urls": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="https://example.com",
            label="起始 URL",
            description="爬虫起始 URL，多个 URL 用换行分隔"
        ),
        
        "爬取规则": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="",
            label="爬取规则 (JSON)",
            description="""JSON 格式的爬取规则:
{
    "selectors": [
        {"name": "title", "selector": "h1::text"},
        {"name": "links", "selector": "a::attr(href)", "many": true}
    ],
    "next_page": {
        "selector": ".next a::attr(href)",
        "follow": true
    }
}"""
        ),
        
        "concurrent_requests": PropertyDefinition(
            type=PropertyType.INT,
            default=4,
            label="并发请求数",
            description="同时进行的请求数量"
        ),
        
        "download_delay": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.5,
            label="下载延迟（秒）",
            description="请求之间的延迟时间"
        ),
        
        "max_pages": PropertyDefinition(
            type=PropertyType.INT,
            default=10,
            label="最大页面数",
            description="爬虫最多爬取的页面数量"
        ),
        
        "爬取模式": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="basic",
            label="爬取模式",
            choices=["basic", "stealth", "dynamic"],
            description="爬取使用的浏览器模式"
        ),
        
        "impersonate": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="chrome",
            label="浏览器伪装",
            choices=["chrome", "firefox", "edge", "safari"]
        ),
        
        "headless": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="无头模式",
            description="浏览器是否以无头模式运行"
        ),
        
        "使用代理": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="使用代理",
            description="是否启用代理轮换"
        ),
        
        "代理列表": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="",
            label="代理列表",
            description="代理服务器地址，多个代理用换行分隔"
        ),
        
        "爬取深度": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="爬取深度",
            description="0 表示无限制，1 表示只爬取起始页面，2 表示跟进一层链接，以此类推"
        ),
        
        "输出文件": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="输出文件",
            description="可选：保存结果到文件，如 items.json"
        ),
    }

    def run(self, params, inputs=None):
        """执行爬虫"""
        import json
        from scrapling.spiders import Spider, Request, Response
        from scrapling.fetchers import ProxyRotator
        
        # 解析起始 URL
        start_urls = [url.strip() for url in params.start_urls.split("\n") if url.strip()]
        
        # 解析爬取规则
        爬取规则 = {}
        if params.爬取规则 and params.爬取规则.strip():
            try:
                爬取规则 = json.loads(params.爬取规则)
            except json.JSONDecodeError as e:
                self.logger.warning(f"爬取规则 JSON 解析失败: {e}")
        
        selectors = 爬取规则.get("selectors", [])
        next_page_rule = 爬取规则.get("next_page", {})
        
        # 创建自定义爬虫类
        class CustomSpider(Spider):
            name = "custom_spider"
            
            # 配置
            concurrent_requests = params.concurrent_requests
            download_delay = params.download_delay
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.items_collected = []
                self.pages_crawled = 0
                self.max_pages = params.max_pages
                self.selectors = selectors
                self.next_page_rule = next_page_rule
                self.crawl_depth = params.爬取深度
                self.fetch_mode = params.爬取模式
                self.impersonate = params.impersonate
                self.headless = params.headless
                
                # 代理配置
                self.use_proxy = params.使用代理
                self.proxies = []
                if params.代理列表 and params.代理列表.strip():
                    self.proxies = [p.strip() for p in params.代理列表.split("\n") if p.strip()]
                
                # 配置代理轮换
                if self.use_proxy and self.proxies:
                    self.proxy_rotator = ProxyRotator(self.proxies)
            
            def start_requests(self):
                """生成初始请求"""
                for url in start_urls:
                    yield Request(url, callback=self.parse)
            
            async def parse(self, response: Response):
                """解析页面"""
                self.pages_crawled += 1
                
                # 检查是否达到最大页面数
                if self.pages_crawled >= self.max_pages:
                    return
                
                # 提取数据
                item = {}
                for sel in self.selectors:
                    name = sel.get("name")
                    selector = sel.get("selector")
                    many = sel.get("many", False)
                    
                    if many:
                        item[name] = response.css(selector).getall()
                    else:
                        item[name] = response.css(selector).get()
                
                if item:
                    self.items_collected.append(item)
                
                # 跟进下一页
                if self.next_page_rule:
                    next_selector = self.next_page_rule.get("selector")
                    follow = self.next_page_rule.get("follow", True)
                    
                    if next_selector:
                        next_links = response.css(next_selector).getall()
                        for link in next_links:
                            if follow and self.pages_crawled < self.max_pages:
                                yield response.follow(link, callback=self.parse)
        
        # 运行爬虫
        try:
            spider = CustomSpider()
            result = spider.start()
            
            items = result.items if hasattr(result, 'items') else spider.items_collected
            
            # 保存到文件
            if params.输出文件 and params.输出文件.strip():
                output_file = params.输出文件
                if output_file.endswith(".json"):
                    import json
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(items, f, ensure_ascii=False, indent=2)
                elif output_file.endswith(".jsonl"):
                    import json
                    with open(output_file, "w", encoding="utf-8") as f:
                        for item in items:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
            return {
                "items": items,
                "count": len(items)
            }
            
        except Exception as e:
            self.logger.error(f"爬虫执行失败: {str(e)}")
            raise


# ==================== 组件3: Scrapling 解析器组件 ====================
class ScraplingParserComponent(BaseComponent):
    """Scrapling HTML 解析器组件 - 专门用于解析 HTML 内容"""
    
    name = "Scrapling HTML 解析"
    category = "数据处理"
    description = (
        "专门用于解析 HTML/XML 内容的组件，支持 CSS 选择器、XPath、"
        "文本搜索、正则表达式等多种提取方式"
    )
    requirements = "scrapling[fetchers]>=0.4.0"
    
    inputs = [
        PortDefinition(
            name="html",
            label="HTML 内容",
            type=ArgumentType.TEXT,
            connection=ConnectionType.SINGLE,
            description="要解析的 HTML 或 XML 内容"
        ),
    ]
    
    outputs = [
        PortDefinition(
            name="result",
            label="解析结果",
            type=ArgumentType.JSON,
            description="返回解析后的数据"
        ),
        PortDefinition(
            name="text",
            label="提取文本",
            type=ArgumentType.TEXT,
            description="返回提取的文本内容"
        ),
    ]
    
    properties = {
        "selector": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="CSS 选择器",
            description="CSS 选择器，如 .product, #title, div.item"
        ),
        
        "xpath": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="XPath",
            description="XPath 表达式，如 //div[@class='item']"
        ),
        
        "text_search": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="文本搜索",
            description="根据文本内容查找元素"
        ),
        
        "regex": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="正则表达式",
            description="使用正则表达式提取内容"
        ),
        
        "提取方式": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="getall",
            label="提取方式",
            choices=["getall", "get", "re"]
        ),
        
        "属性名": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="属性名",
            description="当提取方式为 get_attr 时，指定要提取的属性"
        ),
        
        "自适应": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="自适应解析",
            description="启用自适应元素查找，网站结构变化时可自动重新定位"
        ),
        
        "many": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="提取多个",
            description="是否提取所有匹配的元素，否则只提取第一个"
        ),
    }

    def run(self, params, inputs=None):
        """执行 HTML 解析"""
        from scrapling.parser import Selector
        
        html_content = inputs.html if inputs else ""
        
        if not html_content:
            raise ValueError("请输入要解析的 HTML 内容")
        
        # 解析 HTML
        page = Selector(html_content)
        
        # 根据配置执行提取
        result = None
        extracted_text = ""
        
        # 优先使用 CSS 选择器
        if params.selector and params.selector.strip():
            selector = params.selector
            adaptive = params.自适应
            
            if params.提取方式 == "getall":
                result = page.css(selector, adaptive=adaptive).getall()
            elif params.提取方式 == "get":
                result = page.css(selector, adaptive=adaptive).get()
            elif params.提取方式 == "re":
                result = page.css(selector, adaptive=adaptive).re(params.regex if params.regex else ".*")
        
        # 其次使用 XPath
        elif params.xpath and params.xpath.strip():
            selector = params.xpath
            adaptive = params.自适应
            
            if params.提取方式 == "getall":
                result = page.xpath(selector, adaptive=adaptive).getall()
            elif params.提取方式 == "get":
                result = page.xpath(selector, adaptive=adaptive).get()
            elif params.提取方式 == "re":
                result = page.xpath(selector, adaptive=adaptive).re(params.regex if params.regex else ".*")
        
        # 文本搜索
        elif params.text_search and params.text_search.strip():
            result = page.find_by_text(params.text_search)
        
        # 正则表达式
        elif params.regex and params.regex.strip():
            if params.提取方式 == "re":
                result = page.re(params.regex).getall()
            else:
                result = page.re(params.regex).get()
        
        else:
            result = {"message": "未配置任何选择器"}
        
        # 处理结果
        if isinstance(result, list):
            extracted_text = "\n".join(str(r) for r in result if r)
        elif result:
            extracted_text = str(result)
        
        return {
            "result": {"data": result},
            "text": extracted_text
        }


# ==================== 调试代码 ====================
if __name__ == "__main__":
    # 测试基础抓取组件
    print("=" * 60)
    print("测试 Scrapling 网页抓取组件")
    print("=" * 60)
    
    model = ScraplingComponent()
    
    # 测试1: 基础模式抓取
    print("\n[测试1] 基础模式抓取")
    result = model.debug(
        params={
            "fetch_mode": "basic",
            "url": "https://quotes.toscrape.com/",
            "method": "GET",
            "selector": ".quote",
            "selector_type": "css",
            "extract_mode": "getall",
            "impersonate": "chrome",
            "timeout": 30,
            "verify_ssl": True,
            "headers": [],
            "params": [],
            "request_body": "",
            "adaptive": False,
            "headless": True,
            "solve_cloudflare": False,
            "network_idle": False,
            "load_dom": True,
            "disable_resources": False,
            "use_proxy": False,
            "proxy_url": "",
            "follow_redirects": True,
            "http3": False,
            "stealthy_headers": True,
            "attribute": "",
        },
        inputs={"html_content": ""},
        global_vars={},
        node_id="test_scrapling",
        show_input_types=False,
        show_output_types=True,
        show_execution_time=True
    )
    
    print("\n" + "=" * 60)
    
    # 测试2: 解析 HTML 内容
    print("\n[测试2] 解析 HTML 内容")
    parser = ScraplingParserComponent()
    
    test_html = """
    <html>
        <body>
            <div class="products">
                <div class="product">
                    <h2>Product 1</h2>
                    <span class="price">$100</span>
                </div>
                <div class="product">
                    <h2>Product 2</h2>
                    <span class="price">$200</span>
                </div>
            </div>
        </body>
    </html>
    """
    
    result2 = parser.debug(
        params={
            "selector": ".product h2",
            "xpath": "",
            "text_search": "",
            "regex": "",
            "提取方式": "getall",
            "属性名": "",
            "自适应": False,
            "many": True,
        },
        inputs={"html": test_html},
        global_vars={},
        node_id="test_parser",
        show_input_types=False,
        show_output_types=True,
        show_execution_time=True
    )
    
    print("\n测试完成!")
