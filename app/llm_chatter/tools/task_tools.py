import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from app.llm_chatter.tools.result import ToolResult


class TaskTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self._todo_list: List[Dict] = []
        self._loaded_skills: Dict[str, str] = {}
        self._skill_workspaces: Dict[str, str] = {}
        self._sub_agent_manager = None
        self._set_stage_callback = None

    def _normalize_todos(self, todos: List[Dict]) -> List[Dict]:
        normalized: List[Dict] = []
        for item in todos or []:
            if not isinstance(item, dict):
                continue
            # Normalize keys and values to match UI expectations.
            lower_item = {str(k).lower(): v for k, v in item.items()}
            status = str(lower_item.get("status", "")).lower()
            priority = str(lower_item.get("priority", "medium")).lower()
            normalized.append(
                {
                    "id": lower_item.get("id"),
                    "content": lower_item.get("content", ""),
                    "status": status or "pending",
                    "priority": priority or "medium",
                }
            )
        return normalized

    def todo_write(self, todos: List[Dict]) -> ToolResult:
        try:
            self._todo_list = self._normalize_todos(todos)
            return ToolResult(True, content=f"Todo list updated: {len(todos)} items")
        except Exception as e:
            return ToolResult(False, error=f"Todo write error: {str(e)}")

    def todo_clear(self) -> None:
        self._todo_list = []

    def todo_read(self) -> ToolResult:
        try:
            if not self._todo_list:
                return ToolResult(True, content="No todos")

            lines = []
            for i, todo in enumerate(self._todo_list, 1):
                status = todo.get("status", "")
                if status == "completed":
                    status_icon = "✓"
                elif status == "in_progress":
                    status_icon = "▶"
                else:
                    status_icon = "○"
                content = todo.get("content", "")
                priority = todo.get("priority", "medium")
                lines.append(f"{i}. [{priority}] {status_icon} {content}")

            return ToolResult(True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(False, error=f"Todo read error: {str(e)}")

    def task_execute(
        self, agent: str, description: str, context: str = ""
    ) -> ToolResult:
        try:
            if not hasattr(self, "_sub_agent_manager") or not self._sub_agent_manager:
                return ToolResult(False, error="子智能体管理器未初始化")

            import uuid

            task_id = str(uuid.uuid4())
            result_container = {"result": None, "error": None}
            executor_ref = {"executor": None}

            logger.info(f"[Task] Starting task {task_id}, agent={agent}")
            success = self._sub_agent_manager.execute_task(
                task_id=task_id,
                agent_name=agent,
                task_description=description,
                parent_context=context or "",
                on_finished=None,
                on_error=None,
                executor_ref=executor_ref,
            )

            if not success:
                return ToolResult(False, error="Failed to start sub-agent task")

            executor = executor_ref.get("executor")
            if not executor:
                return ToolResult(False, error="Failed to get executor")

            logger.info(f"[Task] Waiting for task {task_id} to complete...")
            timeout = 1800
            start_time = time.time()
            while not executor.isFinished():
                if time.time() - start_time > timeout:
                    logger.warning(f"[Task] Wait timeout after {timeout}s")
                    executor.cancel()
                    return ToolResult(False, error="Task execution timeout")
                time.sleep(0.1)

            result = executor._last_result if hasattr(executor, "_last_result") else ""
            if hasattr(executor, "_execution_error") and executor._execution_error:
                return ToolResult(False, error=executor._execution_error)

            return ToolResult(True, content=result)

        except Exception as e:
            logger.error(f"[Task] Exception: {e}")
            return ToolResult(False, error=f"Task execution error: {str(e)}")

    def load_skill(self, name: str) -> ToolResult:
        try:
            search_paths = [
                Path(__file__).parent.parent / "skills" / name / f"SKILL.md",
                Path("canvas_files") / "skills" / name / f"SKILL.md",
                Path.home() / ".agents" / "skills" / name / f"SKILL.md",
            ]
            found_path = None
            for path in search_paths:
                if path.exists():
                    found_path = path
                    break

            if not found_path:
                return ToolResult(False, error=f"Skill not found: {name}")

            with open(found_path, "r", encoding="utf-8") as f:
                content = f.read()
                content = content.split("---", 2)[-1].strip()

            self._loaded_skills[name] = content
            self._skill_workspaces[name] = str(found_path.parent.resolve())

            return ToolResult(
                True,
                content=f"Skill loaded: {name}\n\nSkill workspace: {str(found_path.parent.resolve())}\n\n{content}",
            )
        except Exception as e:
            return ToolResult(False, error=f"Load skill error: {str(e)}")

    def list_skills(self) -> ToolResult:
        try:
            import yaml

            skills_dirs = [
                Path(__file__).parent.parent / "skills",
                Path("canvas_files") / "skills",
                Path.home() / ".agents" / "skills",
            ]
            results = []

            skills_intro = ""
            main_skills_dir = Path(__file__).parent.parent / "skills"
            skills_readme = main_skills_dir / "SKILLS.md"
            if skills_readme.exists():
                content = skills_readme.read_text(encoding="utf-8")
                skills_intro = content + "\n\n"

            for skills_dir in skills_dirs:
                if not skills_dir.exists():
                    continue
                for skill_dir in skills_dir.iterdir():
                    if not skill_dir.is_dir():
                        continue
                    if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
                        continue

                    skill_file = skill_dir / "SKILL.md"
                    if not skill_file.exists():
                        skill_file = skill_dir / "skill.md"

                    if not skill_file.exists():
                        continue

                    content = skill_file.read_text(encoding="utf-8")
                    name = skill_dir.name
                    description = ""

                    if content.startswith("---"):
                        try:
                            frontmatter = content.split("---", 2)[1]
                            meta = yaml.safe_load(frontmatter)
                            if meta:
                                name = meta.get("name", skill_dir.name)
                                description = meta.get("description", "")
                        except Exception:
                            pass

                    results.append({"name": name, "description": description})

            skills_xml = "<available_skills>\n"
            for skill in results:
                skills_xml += f"  <skill>\n    <name>{skill['name']}</name>\n    <description>{skill['description']}</description>\n  </skill>\n"
            skills_xml += "</available_skills>"
            return ToolResult(True, content=skills_intro + skills_xml)
        except Exception as e:
            return ToolResult(False, error=f"List skills error: {str(e)}")

    def scan_repo(self, path: str = None, max_depth: int = 2) -> ToolResult:
        import os as _os

        try:
            target_path = self._resolve_path(path) if path else self.workdir
            if not target_path.exists():
                return ToolResult(False, error=f"Path not found: {target_path}")

            lines = [f"Repository scan: {target_path}"]
            root_depth = len(target_path.parts)

            for root, dirs, files in _os.walk(target_path):
                rel_depth = len(Path(root).parts) - root_depth
                if rel_depth > max_depth:
                    dirs[:] = []
                    continue

                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {'.mypy_cache', '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                           'dist', 'build', '.idea', '.vscode'}
                ]
                rel_root = Path(root).relative_to(target_path)
                display_root = "." if str(rel_root) == "." else str(rel_root)
                lines.append(f"\n[{display_root}]")

                sample_dirs = sorted(dirs)[:8]
                sample_files = sorted(files)[:12]
                if sample_dirs:
                    lines.append("dirs: " + ", ".join(sample_dirs))
                if sample_files:
                    lines.append("files: " + ", ".join(sample_files))

            return ToolResult(True, content="\n".join(lines[:200]))
        except Exception as e:
            return ToolResult(False, error=f"scan_repo error: {str(e)}")

    def stage_files(self, files: List[str]) -> ToolResult:
        try:
            staged = []
            for file_path in files or []:
                if not file_path:
                    continue
                resolved = self._resolve_path(file_path)
                staged.append(str(resolved))
            if not staged:
                return ToolResult(True, content="No files staged")
            return ToolResult(True, content="Staged files:\n" + "\n".join(staged))
        except Exception as e:
            return ToolResult(False, error=f"stage_files error: {str(e)}")

    def ask_question(
        self, question: str, options: List[str] = None, multiple: bool = False
    ) -> ToolResult:
        return ToolResult(
            True,
            content={
                "question": question,
                "options": options or [],
                "multiple": multiple,
                "type": "question",
            },
        )

    def _resolve_path(self, path: Optional[str]) -> Path:
        if not path:
            return self.workdir
        try:
            expanded = os.path.expandvars(path)
            if expanded != path:
                path = expanded
            p = Path(path)
            if p.is_absolute():
                return p.resolve()
            else:
                return (self.workdir / p).resolve()
        except (ValueError, OSError, RuntimeError) as e:
            logger.warning(f"[TaskTools] Failed to resolve path {path}: {e}")
            return self.workdir

    def reset_session_state(self):
        """Reset session-scoped state when switching sessions"""
        self._todo_list = []
        self._loaded_skills = {}
        self._skill_workspaces = {}
