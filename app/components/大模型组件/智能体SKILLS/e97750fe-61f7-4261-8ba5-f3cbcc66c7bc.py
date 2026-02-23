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


class LocalSkillPackageLoader(BaseComponent):
    name = "本地技能包加载器"
    category = "大模型组件/智能体SKILLS"
    description = "加载本地 skills 目录，解析 SKILL.md 文档并输出技能集合"
    requirements = "orjson,#yaml,PyYAML"

    inputs = []

    outputs = [
        PortDefinition(
            name="skill_docs",
            label="技能文档集合",
            type=ArgumentType.JSON,
            description="{'skill_id': 'SKILL.md 完整内容'}"
        ),
        PortDefinition(
            name="skill_registry",
            label="技能注册表",
            type=ArgumentType.JSON,
            description="包含技能元数据、命令白名单、依赖等信息"
        ),
        PortDefinition(
            name="workspace_path",
            label="工作空间路径",
            type=ArgumentType.TEXT,
            description="技能脚本/资源的实际执行根路径"
        ),
    ]

    properties = {
        "skills_root": PropertyDefinition(
            type=PropertyType.FILE,
            default="folder",
            label="Skills 根目录",
            description="选择包含 manifest.json 和 skills/ 子目录的本地文件夹",
        ),
        "auto_scan": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="自动扫描子目录",
            description="当 manifest.json 不存在时，自动扫描 skills/ 下的所有 SKILL.md",
        ),
        "include_subskills": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="包含子技能",
            description="是否递归加载 skills/ 子目录中的嵌套技能",
        ),
        "max_file_size": PropertyDefinition(
            type=PropertyType.INT,
            default=5242880,
            label="单文件最大大小 (字节)",
            description="超过此大小的 SKILL.md 将被截断",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}
        self._last_load_time = 0

    def run(self, params, inputs):
        import os
        import sys
        import time
        import json
        import hashlib
        import re
        import orjson
        import yaml
        from pathlib import Path

        self.params = params
        self.inputs = inputs

        start_time = time.time()
        skills_root = params.skills_root

        if not skills_root or skills_root == "folder":
            return self._error_output("未选择 Skills 根目录")

        root_path = Path(skills_root).resolve()
        if not root_path.exists():
            return self._error_output(f"目录不存在：{root_path}")
        if not root_path.is_dir():
            return self._error_output(f"不是目录：{root_path}")

        self.logger.info(f"📁 加载本地技能包：{root_path}")

        manifest = None
        manifest_path = root_path / "manifest.json"

        if manifest_path.exists():
            manifest = self._parse_manifest(manifest_path)
            if not manifest:
                return self._error_output("manifest.json 解析失败")
            self.logger.info(f"📋 使用 manifest.json | 技能数：{len(manifest.get('skills', []))}")
        elif params.auto_scan:
            manifest = self._auto_scan_skills(root_path)
            self.logger.info(f"🔍 自动扫描完成 | 发现技能：{len(manifest.get('skills', []))}")
        else:
            return self._error_output("未找到 manifest.json 且 auto_scan 未启用")

        skill_docs = {}
        skill_registry = {
            "package": {k: v for k, v in manifest.items() if k != "skills"},
            "skills": {},
            "workspace": str(root_path),
            "root_path": str(root_path),
        }
        for skill_info in manifest.get("skills", []):
            skill_id = skill_info.get("id")
            if not skill_id:
                continue

            skill_path_str = skill_info.get("path", f"skills/{skill_id}")
            skill_path = root_path / skill_path_str if not Path(skill_path_str).is_absolute() else Path(skill_path_str)
            skill_md = skill_path / "SKILL.md"

            if not skill_md.exists():
                self.logger.warning(f"⚠️ 技能 {skill_id} 的 SKILL.md 不存在：{skill_md}")
                continue

            skill_content = self._load_skill_md(skill_md, params)
            if not skill_content:
                continue

            skill_docs[skill_id] = skill_content

            meta = self._parse_frontmatter(skill_content)
            skill_registry["skills"][skill_id] = {
                **skill_info,
                "frontmatter": meta,
                "file_path": str(skill_md),
                "script_dir": str(skill_path / "scripts") if (skill_path / "scripts").exists() else None,
                "resource_dir": str(skill_path / "resources") if (skill_path / "resources").exists() else None,
                "last_modified": skill_md.stat().st_mtime,
            }

        if skill_docs:
            self.emit_message(
                method="add_custom_to_global_variable",
                params={
                    "skills_root": str(root_path),
                    "skills_loaded": list(skill_docs.keys()),
                    "skills_workspace": str(root_path),
                }
            )

        total_duration = time.time() - start_time
        self._last_load_time = time.time()

        self.logger.info(f"✅ 本地技能包加载完成 | 技能数:{len(skill_docs)} | 耗时:{total_duration:.3f}s")

        return {
            "skill_docs": skill_docs,
            "skill_registry": skill_registry,
            "workspace_path": str(root_path)
        }

    def _parse_manifest(self, manifest_path):
        import json
        try:
            content = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(content)
            required_fields = ["name", "version"]
            for field in required_fields:
                if field not in manifest:
                    self.logger.error(f"manifest.json 缺少必需字段：{field}")
                    return None
            if "skills" not in manifest:
                manifest["skills"] = []
            return manifest
        except Exception as e:
            self.logger.error(f"manifest.json 解析失败：{e}")
            return None

    def _auto_scan_skills(self, root_path):
        import json
        from pathlib import Path

        manifest = {
            "name": root_path.name,
            "version": "1.0.0",
            "description": f"Auto-scanned skills from {root_path}",
            "skills": [],
        }

        skills_dir = root_path / "skills"
        if not skills_dir.exists():
            for item in root_path.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    skill_id = item.name
                    manifest["skills"].append({
                        "id": skill_id,
                        "name": skill_id.replace("-", " ").title(),
                        "path": str(item.relative_to(root_path)),
                    })
            return manifest

        def scan_dir(dir_path, base_path):
            skills = []
            for item in dir_path.iterdir():
                if item.is_dir():
                    if (item / "SKILL.md").exists():
                        skill_id = item.name
                        skills.append({
                            "id": skill_id,
                            "name": skill_id.replace("-", " ").title(),
                            "path": str(item.relative_to(base_path)),
                        })
                    if self.params.include_subskills:
                        skills.extend(scan_dir(item, base_path))
            return skills

        manifest["skills"] = scan_dir(skills_dir, root_path)
        return manifest

    def _load_skill_md(self, file_path, params):
        file_size = file_path.stat().st_size
        if file_size > params.max_file_size:
            self.logger.warning(f"⚠️ 文件过大，截断：{file_path.name} ({file_size / 1024:.1f}KB)")

        try:
            content = file_path.read_text(encoding="utf-8")
            if len(content) > params.max_file_size:
                content = content[:params.max_file_size] + "\n\n...（内容截断）..."
            return content
        except Exception as e:
            self.logger.error(f"读取 SKILL.md 失败 {file_path}: {e}")
            return None

    def _parse_frontmatter(self, content):
        import yaml
        import re
        if not content.strip().startswith("---"):
            return {}
        match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return {}
        try:
            meta = yaml.safe_load(match.group(1))
            return meta if isinstance(meta, dict) else {}
        except Exception as e:
            self.logger.warning(f"frontmatter 解析失败：{e}")
            return {}

    def _error_output(self, message):
        return {
            "skill_docs": {},
            "skill_registry": {},
            "workspace_path": ""
        }

    def teardown(self):
        self._cache.clear()
        self.logger.debug("🧹 LocalSkillPackageLoader 缓存已清理")