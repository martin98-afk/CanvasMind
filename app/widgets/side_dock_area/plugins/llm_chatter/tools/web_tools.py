import re
from pathlib import Path
from typing import Optional

from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult
from app.utils.config import Settings


class WebTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def fetch_web(self, url: str, format: str = "markdown") -> ToolResult:
        try:
            import requests

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            if format == "text":
                return ToolResult(True, content=response.text[:50000])
            elif format == "html":
                return ToolResult(True, content=response.text[:50000])
            else:
                text = response.text
                text = re.sub(
                    r"<script[^>]*>.*?</script>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(
                    r"<style[^>]*>.*?</style>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s+", " ", text)
                return ToolResult(True, content=text[:50000])
        except ImportError:
            return ToolResult(False, error="requests library not installed")
        except Exception as e:
            return ToolResult(False, error=f"Fetch error: {str(e)}")

    def search_web(self, query: str, num_results: int = 10) -> ToolResult:
        try:
            import requests
            import os

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

            response = requests.get(
                "https://serpapi.com/search", params=params, proxies=proxies, timeout=30
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

        except ImportError:
            return ToolResult(False, error="requests library not installed")
        except requests.exceptions.Timeout:
            return ToolResult(False, error="Search timeout, please try again")
        except requests.exceptions.RequestException as e:
            return ToolResult(False, error=f"Search request failed: {str(e)}")
        except Exception as e:
            return ToolResult(False, error=f"Search error: {str(e)}")
