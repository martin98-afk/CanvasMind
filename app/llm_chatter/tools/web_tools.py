import os
import re
import httpx
import html2text
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool, QRunnable
from bs4 import BeautifulSoup
from loguru import logger
from app.llm_chatter.tools.result import ToolResult
from app.utils.config import Settings


class WebFetchTask(QRunnable):
    """异步网页抓取任务"""

    class Signals(QObject):
        finished = pyqtSignal(object)  # ToolResult

    def __init__(self, url: str, format: str, max_chars: int, cancelled_ref: list):
        super().__init__()
        self.signals = self.Signals()
        self.url = url
        self.format = format
        self.max_chars = max_chars
        self.cancelled_ref = cancelled_ref

    def run(self):
        try:
            result = self._do_fetch()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit(
                ToolResult(False, error=f"Fetch error: {str(e)}")
            )

    def _do_fetch(self) -> ToolResult:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            with httpx.Client(
                timeout=30, follow_redirects=True, headers=headers
            ) as client:
                response = client.get(self.url)
                response.raise_for_status()
                html_content = response.text

            if self.format == "html":
                return ToolResult(True, content=html_content[: self.max_chars])

            soup = BeautifulSoup(html_content, "html.parser")
            for element in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "iframe",
                    "noscript",
                ]
            ):
                element.decompose()

            if self.format == "text":
                text = soup.get_text(separator="\n")
                clean_text = re.sub(r"\n+", "\n", text).strip()
                return ToolResult(True, content=clean_text[: self.max_chars])

            # markdown 格式
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            h.ignore_emphasis = False
            markdown_text = h.handle(str(soup))
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text)
            return ToolResult(True, content=markdown_text[: self.max_chars])

        except httpx.HTTPStatusError as e:
            return ToolResult(False, error=f"HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(False, error=f"Fetch error: {str(e)}")


class WebSearchTask(QRunnable):
    """异步网络搜索任务"""

    class Signals(QObject):
        finished = pyqtSignal(object)  # ToolResult

    def __init__(self, query: str, num_results: int, cancelled_ref: list):
        super().__init__()
        self.signals = self.Signals()
        self.query = query
        self.num_results = num_results
        self.cancelled_ref = cancelled_ref

    def run(self):
        try:
            result = self._do_search()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit(
                ToolResult(False, error=f"Search error: {str(e)}")
            )

    def _do_search(self) -> ToolResult:
        api_key = (
            os.environ.get("SERPAPI_KEY") or Settings.get_instance().SERPAPI_KEY.value
        )

        if api_key == "your-serpapi-key-here" or not api_key:
            # 回退到 DuckDuckGo 搜索
            return self._search_duckduckgo()

        try:
            proxies = None
            http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
            if http_proxy:
                proxies = {"http": http_proxy, "https": http_proxy}

            params = {
                "engine": "duckduckgo",
                "q": self.query,
                "kl": "us-en",
                "api_key": api_key,
            }

            response = httpx.get(
                "https://serpapi.com/search",
                params=params,
                proxies=proxies,
                timeout=30,
                follow_redirects=True,
            )

            if response.status_code == 401:
                logger.warning("SerpAPI key invalid, falling back to DuckDuckGo")
                return self._search_duckduckgo()
            if response.status_code == 403:
                logger.warning("SerpAPI quota exceeded, falling back to DuckDuckGo")
                return self._search_duckduckgo()

            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("organic_results", [])[: self.num_results]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                if title and link:
                    results.append(f"- {title}\n  {link}\n  {snippet}")

            return ToolResult(
                True, content="\n\n".join(results) if results else "No results found"
            )

        except httpx.TimeoutException:
            logger.warning("SerpAPI timeout, falling back to DuckDuckGo")
            return self._search_duckduckgo()
        except httpx.RequestError as e:
            logger.warning(f"SerpAPI request failed: {e}, falling back to DuckDuckGo")
            return self._search_duckduckgo()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"SerpAPI HTTP error: {e.response.status_code}, falling back to DuckDuckGo"
            )
            return self._search_duckduckgo()
        except Exception as e:
            logger.warning(f"SerpAPI error: {e}, falling back to DuckDuckGo")
            return self._search_duckduckgo()

    def _search_duckduckgo(self) -> ToolResult:
        try:
            url = "https://html.duckduckgo.com/html/"
            r = httpx.get(
                url,
                params={"q": self.query},
                headers={"User-Agent": "Mozilla/5.0 (compatible)"},
                timeout=30,
                follow_redirects=True,
            )
            titles = re.findall(
                r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                r.text,
                re.DOTALL,
            )
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</div>', r.text, re.DOTALL
            )
            results = []
            for i, (link, title) in enumerate(titles[: self.num_results]):
                t = re.sub(r"<[^>]+>", "", title).strip()
                s = (
                    re.sub(r"<[^>]+>", "", snippets[i]).strip()
                    if i < len(snippets)
                    else ""
                )
                results.append(f"**{t}**\n{link}\n{s}")
            return ToolResult(
                True, content="\n\n".join(results) if results else "No results found"
            )
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return ToolResult(False, error=f"DuckDuckGo search failed: {str(e)}")


class WebTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self._thread_pool: Optional[QThreadPool] = None
        self._current_fetch_task: Optional[WebFetchTask] = None
        self._current_search_task: Optional[WebSearchTask] = None

    def _get_thread_pool(self) -> QThreadPool:
        if self._thread_pool is None:
            self._thread_pool = QThreadPool.globalInstance()
        return self._thread_pool

    def fetch_web(
        self,
        url: str,
        format: str = "markdown",
        max_chars: int = 26000,
        callback: Callable[[ToolResult], None] = None,
        cancelled_ref: list = None,
    ) -> Optional[ToolResult]:
        """
        获取网页内容

        如果提供 callback，则异步执行并返回 None
        否则同步执行并返回 ToolResult
        """
        if callback is not None:
            self._run_fetch_async(url, format, max_chars, callback, cancelled_ref)
            return None
        else:
            return self._fetch_sync(url, format, max_chars)

    def _fetch_sync(self, url: str, format: str, max_chars: int) -> ToolResult:
        """同步获取网页"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            with httpx.Client(
                timeout=30, follow_redirects=True, headers=headers
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                html_content = response.text

            if format == "html":
                return ToolResult(True, content=html_content[:max_chars])

            soup = BeautifulSoup(html_content, "html.parser")
            for element in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "iframe",
                    "noscript",
                ]
            ):
                element.decompose()

            if format == "text":
                text = soup.get_text(separator="\n")
                clean_text = re.sub(r"\n+", "\n", text).strip()
                return ToolResult(True, content=clean_text[:max_chars])

            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            h.ignore_emphasis = False
            markdown_text = h.handle(str(soup))
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text)
            return ToolResult(True, content=markdown_text[:max_chars])

        except httpx.HTTPStatusError as e:
            return ToolResult(False, error=f"HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(False, error=f"Fetch error: {str(e)}")

    def _run_fetch_async(
        self,
        url: str,
        format: str,
        max_chars: int,
        callback: Callable[[ToolResult], None],
        cancelled_ref: list = None,
    ):
        """异步获取网页"""
        task = WebFetchTask(url, format, max_chars, cancelled_ref or [False])
        self._current_fetch_task = task

        def on_finished(result):
            self._current_fetch_task = None
            callback(result)

        task.signals.finished.connect(on_finished)
        self._get_thread_pool().start(task)
        logger.info(f"[WebTools] Started async fetch task, url={url[:50]}...")

    def search_web(
        self,
        query: str,
        num_results: int = 10,
        callback: Callable[[ToolResult], None] = None,
        cancelled_ref: list = None,
    ) -> Optional[ToolResult]:
        """
        搜索网络

        如果提供 callback，则异步执行并返回 None
        否则同步执行并返回 ToolResult
        """
        if callback is not None:
            self._run_search_async(query, num_results, callback, cancelled_ref)
            return None
        else:
            return self._search_sync(query, num_results)

    def _search_sync(self, query: str, num_results: int) -> ToolResult:
        """同步搜索（向后兼容）"""
        api_key = (
            os.environ.get("SERPAPI_KEY") or Settings.get_instance().SERPAPI_KEY.value
        )

        if api_key == "your-serpapi-key-here" or not api_key:
            return self._search_duckduckgo_sync(query, num_results)

        try:
            proxies = None
            http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
            if http_proxy:
                proxies = {"http": http_proxy, "https": http_proxy}

            params = {
                "engine": "duckduckgo",
                "q": query,
                "kl": "us-en",
                "api_key": api_key,
            }

            response = httpx.get(
                "https://serpapi.com/search",
                params=params,
                proxies=proxies,
                timeout=30,
                follow_redirects=True,
            )

            if response.status_code == 401:
                logger.warning("SerpAPI key invalid, falling back to DuckDuckGo")
                return self._search_duckduckgo_sync(query, num_results)
            if response.status_code == 403:
                logger.warning("SerpAPI quota exceeded, falling back to DuckDuckGo")
                return self._search_duckduckgo_sync(query, num_results)

            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("organic_results", [])[:num_results]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                if title and link:
                    results.append(f"- {title}\n  {link}\n  {snippet}")

            return ToolResult(
                True, content="\n\n".join(results) if results else "No results found"
            )

        except httpx.TimeoutException:
            logger.warning("SerpAPI timeout, falling back to DuckDuckGo")
            return self._search_duckduckgo_sync(query, num_results)
        except httpx.RequestError as e:
            logger.warning(f"SerpAPI request failed: {e}, falling back to DuckDuckGo")
            return self._search_duckduckgo_sync(query, num_results)
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"SerpAPI HTTP error: {e.response.status_code}, falling back to DuckDuckGo"
            )
            return self._search_duckduckgo_sync(query, num_results)
        except Exception as e:
            logger.warning(f"SerpAPI error: {e}, falling back to DuckDuckGo")
            return self._search_duckduckgo_sync(query, num_results)

    def _search_duckduckgo_sync(self, query: str, num_results: int) -> ToolResult:
        """DuckDuckGo 同步搜索"""
        try:
            url = "https://html.duckduckgo.com/html/"
            r = httpx.get(
                url,
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible)"},
                timeout=30,
                follow_redirects=True,
            )
            titles = re.findall(
                r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                r.text,
                re.DOTALL,
            )
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</div>', r.text, re.DOTALL
            )
            results = []
            for i, (link, title) in enumerate(titles[:num_results]):
                t = re.sub(r"<[^>]+>", "", title).strip()
                s = (
                    re.sub(r"<[^>]+>", "", snippets[i]).strip()
                    if i < len(snippets)
                    else ""
                )
                results.append(f"**{t}**\n{link}\n{s}")
            return ToolResult(
                True, content="\n\n".join(results) if results else "No results found"
            )
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return ToolResult(False, error=f"DuckDuckGo search failed: {str(e)}")

    def _run_search_async(
        self,
        query: str,
        num_results: int,
        callback: Callable[[ToolResult], None],
        cancelled_ref: list = None,
    ):
        """异步搜索"""
        task = WebSearchTask(query, num_results, cancelled_ref or [False])
        self._current_search_task = task

        def on_finished(result):
            self._current_search_task = None
            callback(result)

        task.signals.finished.connect(on_finished)
        self._get_thread_pool().start(task)
        logger.info(f"[WebTools] Started async search task, query={query[:50]}...")
