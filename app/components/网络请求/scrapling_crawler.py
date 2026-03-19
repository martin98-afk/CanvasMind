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



class ScraplingCrawlerComponent(BaseComponent):
    name = "Scrapling 网页抓取器"
    category = "网络请求"
    description = "基于 Scrapling 库的高性能网页内容抓取，支持 CSS/XPath 选择器、自动元素匹配、隐形抓取等功能"
    requirements = "scrapling>=0.2.9,curl_cffi>=0.14.0,click>=8.3.0,playwright==1.58.0,patchright==1.58.2,browserforge>=1.2.4,apify-fingerprint-datapoints>=0.11.0,msgspec>=0.20.0"
    inputs = [
        PortDefinition(name="input", label="INPUT", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="html_content", label="HTML 内容", type=ArgumentType.TEXT),
        PortDefinition(name="text_content", label="文本内容", type=ArgumentType.TEXT),
        PortDefinition(name="extracted_data", label="提取数据", type=ArgumentType.JSON),
        PortDefinition(name="status", label="状态", type=ArgumentType.TEXT),
    ]

    properties = {
        "url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="https://example.com",
            label="目标 URL",
        ),
        "fetcher_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Fetcher",
            label="抓取器类型",
            choices=["Fetcher", "StealthyFetcher", "DynamicFetcher"]
        ),
        "stealth_mode": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="隐形模式（自动设置请求头）",
        ),
        "timeout": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="超时时间（秒）",
        ),
        "selector_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="css",
            label="选择器类型",
            choices=["css", "xpath", "text"]
        ),
        "selector": PropertyDefinition(
            type=PropertyType.TEXT,
            default="body",
            label="选择器表达式",
        ),
        "extract_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="text",
            label="提取模式",
            choices=["text", "html", "attributes", "all"]
        ),
        "auto_match": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="自动元素匹配（抗网站结构变化）",
        ),
        "auto_save": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="自动保存选择器",
        ),
        "ignore_tags": PropertyDefinition(
            type=PropertyType.TEXT,
            default="script,style",
            label="忽略的标签（逗号分隔）",
        ),
        "follow_redirects": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="跟随重定向",
        ),
        "headers": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="自定义请求头",
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
    }

    def run(self, params, inputs=None):
        from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher
        import time
        import re

        # 获取输入 URL（优先使用输入端口）
        url = params.url

        # URL 验证：确保是有效的 URL 格式
        url_pattern = re.compile(
            r'^https?://'  # http:// 或 https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP 地址
            r'(?::\d+)?'  # 可选端口
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url or not url_pattern.match(url):
            error_msg = f"无效的 URL: '{url}' - 请输入以 http:// 或 https:// 开头的有效网址"
            self.logger.error(error_msg)
            return {
                "html_content": "",
                "text_content": "",
                "extracted_data": {},
                "status": f"error: {error_msg}"
            }

        # 解析属性
        fetcher_type = params.fetcher_type
        stealth_mode = params.stealth_mode
        timeout = int(float(params.timeout))  # 确保 timeout 是 int 类型
        selector_type = params.selector_type
        selector = params.selector
        extract_mode = params.extract_mode
        auto_match = params.auto_match
        auto_save = params.auto_save
        ignore_tags_str = params.ignore_tags
        follow_redirects = params.follow_redirects

        # 解析忽略的标签
        ignore_tags = tuple(tag.strip() for tag in ignore_tags_str.split(',') if tag.strip())

        # 构建请求头
        custom_headers = {header.key: header.value for header in params.headers if header.key}

        # 选择 fetcher 类型
        fetcher_map = {
            "Fetcher": Fetcher,
            "StealthyFetcher": StealthyFetcher,
            "DynamicFetcher": DynamicFetcher
        }
        FetcherClass = fetcher_map.get(fetcher_type, Fetcher)

        try:
            start_time = time.time()

            # 根据 fetcher 类型执行抓取
            if fetcher_type == "Fetcher":
                page = Fetcher.get(
                    url,
                    headers=custom_headers if custom_headers else None,
                    stealthy_headers=stealth_mode,
                    timeout=timeout,
                    allow_redirects=follow_redirects,
                    verify=False  # 跳过 SSL 证书验证
                )
            elif fetcher_type == "StealthyFetcher":
                page = StealthyFetcher.fetch(
                    url,
                    headless=True,
                    network_idle=True,
                    timeout=timeout
                )
            elif fetcher_type == "DynamicFetcher":
                page = DynamicFetcher.fetch(
                    url,
                    headless=True,
                    wait_until="network_idle",
                    timeout=timeout * 1000  # Playwright uses milliseconds
                )

            elapsed_time = time.time() - start_time

            # 获取完整的 HTML 内容
            html_content = page.html_content if hasattr(page, 'html_content') else page.text

            # 获取纯文本内容（排除指定标签）
            text_content = page.get_all_text(ignore_tags=ignore_tags) if ignore_tags else page.get_all_text()

            # 根据选择器提取数据
            extracted_data = {}

            if selector:
                # 执行选择器
                if selector_type == "css":
                    elements = page.css(selector)
                elif selector_type == "xpath":
                    elements = page.xpath(selector)
                elif selector_type == "text":
                    elements = page.find_all(text=selector)

                # 根据提取模式处理结果
                if extract_mode == "text":
                    # 安全提取文本，确保返回字符串
                    try:
                        if hasattr(elements, '__iter__') and not isinstance(elements, (str, bytes)):
                            extracted_data = []
                            for elem in elements:
                                try:
                                    text_val = elem.text if hasattr(elem, 'text') else str(elem) if elem else ""
                                    extracted_data.append(str(text_val))
                                except:
                                    extracted_data.append(str(elem) if elem else "")
                        else:
                            text_val = elements.text if hasattr(elements, 'text') else str(elements) if elements else ""
                            extracted_data = str(text_val)
                    except:
                        extracted_data = str(elements) if elements else ""
                elif extract_mode == "html":
                    # 安全提取HTML，确保返回字符串
                    try:
                        if hasattr(elements, '__iter__') and not isinstance(elements, (str, bytes)):
                            extracted_data = []
                            for elem in elements:
                                html_val = elem.html_content if hasattr(elem, 'html_content') else str(elem) if elem else ""
                                extracted_data.append(str(html_val))
                        else:
                            html_val = elements.html_content if hasattr(elements, 'html_content') else str(elements) if elements else ""
                            extracted_data = str(html_val)
                    except:
                        extracted_data = str(elements) if elements else ""
                elif extract_mode == "attributes":
                    # 安全提取属性，确保返回字典
                    try:
                        if hasattr(elements, '__iter__') and not isinstance(elements, (str, bytes)):
                            extracted_data = []
                            for elem in elements:
                                attrib_val = dict(elem.attrib) if hasattr(elem, 'attrib') else {}
                                extracted_data.append(attrib_val)
                        else:
                            extracted_data = dict(elements.attrib) if hasattr(elements, 'attrib') else {}
                    except:
                        extracted_data = []
                elif extract_mode == "all":
                    # 返回完整元素信息，确保所有值都是字符串
                    try:
                        if hasattr(elements, '__iter__') and not isinstance(elements, (str, bytes)):
                            extracted_data = []
                            for elem in elements:
                                item = {}
                                if hasattr(elem, 'text'):
                                    item['text'] = str(elem.text) if elem.text else ""
                                if hasattr(elem, 'html_content'):
                                    item['html'] = str(elem.html_content) if elem.html_content else ""
                                if hasattr(elem, 'attrib'):
                                    item['attributes'] = dict(elem.attrib)
                                if hasattr(elem, 'path'):
                                    item['path'] = str(elem.path) if elem.path else ""
                                extracted_data.append(item)
                        else:
                            extracted_data = {
                                'text': str(elements.text) if hasattr(elements, 'text') and elements.text else "",
                                'html': str(elements.html_content) if hasattr(elements, 'html_content') and elements.html_content else "",
                                'attributes': dict(elements.attrib) if hasattr(elements, 'attrib') else {},
                                'path': str(elements.path) if hasattr(elements, 'path') and elements.path else "",
                            }
                    except:
                        extracted_data = {}

            return {
                "html_content": html_content,
                "text_content": text_content,
                "extracted_data": extracted_data,
                "status": f"success - 耗时: {elapsed_time:.2f}秒"
            }

        except Exception as e:
            self.logger.error(f"网页抓取异常: {str(e)}")
            return {
                "html_content": "",
                "text_content": "",
                "extracted_data": {},
                "status": f"error: {str(e)}"
            }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    model = ScraplingCrawlerComponent()
    result = model.debug(
        params={
            "url": "https://example.com",
            "fetcher_type": "Fetcher",
            "stealth_mode": False,
            "timeout": 30,
            "selector_type": "css",
            "selector": "h1",
            "extract_mode": "text",
            "auto_match": False,
            "auto_save": False,
            "ignore_tags": "script,style",
            "follow_redirects": True,
            "headers": [],
        },
        inputs={"url": ""},
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
