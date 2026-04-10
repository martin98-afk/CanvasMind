import os
import re
import httpx
import html2text
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult
from app.utils.config import Settings


class WebTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def fetch_web(self, url: str, format: str = "markdown", max_chars: int = 26000) -> ToolResult:
        # 1. 模拟真实浏览器请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            # 2. 使用 httpx 获取内容，增加超时和重定向处理
            with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()

                # 自动检测编码，防止中文乱码
                content_type = response.headers.get("content-type", "").lower()
                html_content = response.text

            if format == "html":
                return ToolResult(True, content=html_content[:max_chars])

            # 3. 使用 BeautifulSoup 进行精细化清理
            soup = BeautifulSoup(html_content, "html.parser")

            # 移除无用标签（噪音）
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
                element.decompose()

            if format == "text":
                # 获取纯文本并压缩空白字符
                text = soup.get_text(separator="\n")
                clean_text = re.sub(r'\n+', '\n', text).strip()
                return ToolResult(True, content=clean_text[:max_chars])

            else:  # 默认 markdown 格式
                # 4. 真正的 HTML 转 Markdown
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True  # LLM 通常不需要图片链接
                h.body_width = 0  # 不自动换行
                h.ignore_emphasis = False

                markdown_text = h.handle(str(soup))
                # 进一步清理多余的空格和换行
                markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

                return ToolResult(True, content=markdown_text[:max_chars])

        except httpx.HTTPStatusError as e:
            return ToolResult(False, error=f"HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(False, error=f"Fetch error: {str(e)}")

    def search_web_duckduckgo(self, query: str, num_results: int = 10) -> ToolResult:
        try:
            url = "https://html.duckduckgo.com/html/"
            r = httpx.get(url, params={"q": query},
                          headers={"User-Agent": "Mozilla/5.0 (compatible)"},
                          timeout=30, follow_redirects=True)
            titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                r.text, re.DOTALL)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</div>', r.text, re.DOTALL)
            results = []
            for i, (link, title) in enumerate(titles[:8]):
                t = re.sub(r"<[^>]+>", "", title).strip()
                s = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                results.append(f"**{t}**\n{link}\n{s}")
            return ToolResult(True, content="\n\n".join(results) if results else "No results found")
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")

    def serch_web_serpapi(self, query: str, num_results: int = 10) -> ToolResult:
        try:
            api_key = (
                    os.environ.get("SERPAPI_KEY")
                    or Settings.get_instance().SERPAPI_KEY.value
            )

            if api_key == "your-serpapi-key-here" or not api_key:
                return ToolResult(
                    False,
                    error="Please set SERPAPI_KEY environment variable or configure in settings",
                )

            proxies = None
            http_proxy = (
                    os.environ.get("HTTP_PROXY")
                    or os.environ.get("http_proxy")
                    or os.environ.get("HTTPS_PROXY")
                    or os.environ.get("https_proxy")
            )
            if http_proxy:
                proxies = {"http": http_proxy, "https": http_proxy}

            params = {
                "engine": "duckduckgo",
                "q": query,
                "kl": "us-en",
                "api_key": api_key,
            }

            response = httpx.get(
                "https://serpapi.com/search", params=params, proxies=proxies, timeout=30, follow_redirects=True
            )

            if response.status_code == 401:
                return ToolResult(False, error="Invalid SerpAPI key")
            if response.status_code == 403:
                return ToolResult(False, error="SerpAPI quota exceeded")

            response.raise_for_status()
            data = response.json()

            results = []
            organic = data.get("organic_results", [])

            for item in organic[:num_results]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                if title and link:
                    results.append(f"- {title}\n  {link}\n  {snippet}")

            if not results:
                return ToolResult(True, content="No results found")

            return ToolResult(True, content="\n\n".join(results))

        except httpx.Timeout:
            return ToolResult(False, error="Search timeout, please try again")
        except httpx.RequestError as e:
            return ToolResult(False, error=f"Search request failed: {str(e)}")
        except Exception as e:
            return ToolResult(False, error=f"Search error: {str(e)}")

    def search_web(self, query: str, num_results: int = 10) -> ToolResult:
        return self.serch_web_serpapi(query, num_results)