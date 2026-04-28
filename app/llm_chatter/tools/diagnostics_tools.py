import json
import subprocess
from pathlib import Path
from typing import Optional

from app.llm_chatter.tools.result import ToolResult


class DiagnosticsTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def _detect_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".sh": "shellscript",
            ".bash": "shellscript",
            ".zsh": "shellscript",
        }.get(ext, "unknown")

    def _run_quietly(self, cmd: list, cwd: Optional[str] = None, timeout: int = 30):
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or str(self.workdir),
            )
            out = (r.stdout + ("\n" + r.stderr if r.stderr else "")).strip()
            return r.returncode, out
        except FileNotFoundError:
            return -1, f"(command not found: {cmd[0]})"
        except subprocess.TimeoutExpired:
            return -1, f"(timed out after {timeout}s)"
        except Exception as e:
            return -1, f"(error: {e})"

    def get_diagnostics(self, file_path: str, language: str = None) -> ToolResult:
        p = Path(file_path)
        if not p.exists():
            return ToolResult(False, error=f"File not found: {file_path}")

        lang = language or self._detect_language(file_path)
        abs_path = str(p.resolve())
        results = []

        if lang == "python":
            rc, out = self._run_quietly(["pyright", "--outputjson", abs_path])
            if rc != -1:
                try:
                    data = json.loads(out)
                    diags = data.get("generalDiagnostics", [])
                    if not diags:
                        results.append("pyright: no diagnostics")
                    else:
                        lines = [f"pyright ({len(diags)} issue(s)):"]
                        for d in diags[:50]:
                            rng = d.get("range", {}).get("start", {})
                            ln = rng.get("line", 0) + 1
                            ch = rng.get("character", 0) + 1
                            sev = d.get("severity", "error")
                            msg = d.get("message", "")
                            rule = d.get("rule", "")
                            lines.append(
                                f"  {ln}:{ch} [{sev}] {msg}"
                                + (f" ({rule})" if rule else "")
                            )
                        results.append("\n".join(lines))
                except json.JSONDecodeError:
                    if out:
                        results.append(f"pyright:\n{out[:3000]}")
            else:
                rc2, out2 = self._run_quietly(["mypy", "--no-error-summary", abs_path])
                if rc2 != -1:
                    results.append(
                        f"mypy:\n{out2[:3000]}" if out2 else "mypy: no diagnostics"
                    )
                else:
                    rc3, out3 = self._run_quietly(["flake8", abs_path])
                    if rc3 != -1:
                        results.append(
                            f"flake8:\n{out3[:3000]}"
                            if out3
                            else "flake8: no diagnostics"
                        )
                    else:
                        rc4, out4 = self._run_quietly(
                            ["python3", "-m", "py_compile", abs_path]
                        )
                        if out4:
                            results.append(f"py_compile (syntax check):\n{out4}")
                        else:
                            results.append(
                                "py_compile: syntax OK (no further tools available)"
                            )

        elif lang in ("javascript", "typescript"):
            rc, out = self._run_quietly(["tsc", "--noEmit", "--strict", abs_path])
            if rc != -1:
                results.append(f"tsc:\n{out[:3000]}" if out else "tsc: no errors")
            else:
                rc2, out2 = self._run_quietly(["eslint", abs_path])
                if rc2 != -1:
                    results.append(
                        f"eslint:\n{out2[:3000]}" if out2 else "eslint: no issues"
                    )
                else:
                    results.append(
                        "No TypeScript/JavaScript checker found (install tsc or eslint)"
                    )

        elif lang == "shellscript":
            rc, out = self._run_quietly(["shellcheck", abs_path])
            if rc != -1:
                results.append(
                    f"shellcheck:\n{out[:3000]}" if out else "shellcheck: no issues"
                )
            else:
                rc2, out2 = self._run_quietly(["bash", "-n", abs_path])
                results.append(
                    f"bash -n (syntax check):\n{out2}" if out2 else "bash -n: syntax OK"
                )

        else:
            results.append(
                f"No diagnostic tool available for language: {lang or 'unknown'} (ext: {Path(file_path).suffix})"
            )

        return ToolResult(
            True, content="\n\n".join(results) if results else "(no diagnostics output)"
        )
