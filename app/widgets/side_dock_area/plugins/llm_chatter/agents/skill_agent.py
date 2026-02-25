# -*- coding: utf-8 -*-
"""
智能体技能代理模块
负责加载和执行 skill.md 中定义的技能
"""

import json
import re
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
from loguru import logger


class SkillDefinition:
    """技能定义"""

    def __init__(
        self,
        name: str,
        description: str,
        method: str,
        params_schema: dict = None,
        examples: List[str] = None,
    ):
        self.name = name
        self.description = description
        self.method = method
        self.params_schema = params_schema or {}
        self.examples = examples or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "method": self.method,
            "params_schema": self.params_schema,
            "examples": self.examples,
        }


class SkillAgent:
    """技能执行代理"""

    def __init__(self, homepage=None):
        self.homepage = homepage
        self.skills: Dict[str, SkillDefinition] = {}
        self.skill_executors: Dict[str, Callable] = {}

    def load_skill_document(self, content: str) -> List[SkillDefinition]:
        """解析 skill.md 文档并加载技能定义"""
        self.skills.clear()

        sections = self._parse_skill_document(content)

        for section in sections:
            skill = self._parse_skill_section(section)
            if skill:
                self.skills[skill.name] = skill
                logger.info(f"[SkillAgent] Loaded skill: {skill.name}")

        return list(self.skills.values())

    def _parse_skill_document(self, content: str) -> List[str]:
        """解析文档为技能章节"""
        sections = []
        lines = content.split("\n")
        current_section = []
        in_skill_block = False

        for line in lines:
            if line.strip().startswith("## "):
                if current_section:
                    sections.append("\n".join(current_section))
                    current_section = []
                in_skill_block = True
            current_section.append(line)

        if current_section:
            sections.append("\n".join(current_section))

        return sections

    def _parse_skill_section(self, section: str) -> Optional[SkillDefinition]:
        """解析单个技能章节"""
        lines = section.strip().split("\n")
        if not lines:
            return None

        title = lines[0].strip().lstrip("#").strip()

        name = title
        description = ""
        method = ""
        params_schema = {}
        examples = []

        desc_pattern = re.compile(r"^-\s*功能(?:说明)?[：:]\s*(.+)$", re.IGNORECASE)
        method_pattern = re.compile(r"^-\s*调用方法[：:]\s*(.+)$", re.IGNORECASE)
        param_pattern = re.compile(r"^-\s*参数[：:]\s*(.+)$", re.IGNORECASE)

        for line in lines[1:]:
            line = line.strip()

            desc_match = desc_pattern.match(line)
            if desc_match:
                description = desc_match.group(1).strip()
                continue

            method_match = method_pattern.match(line)
            if method_match:
                method = method_match.group(1).strip()
                continue

            if line.startswith("```") and "plugin_call" in line:
                continue
            if line.startswith("```"):
                continue

        if not method:
            method = name

        return SkillDefinition(name, description, method, params_schema, examples)

    def register_executor(self, skill_name: str, executor: Callable):
        """注册技能执行器"""
        self.skill_executors[skill_name] = executor

    def execute_skill(self, method: str, params: dict, context: dict = None) -> Any:
        """执行技能"""
        skill = self.skills.get(method)
        if not skill:
            logger.warning(f"[SkillAgent] Skill not found: {method}")
            return {"error": f"Skill not found: {method}"}

        executor = self.skill_executors.get(method)
        if not executor:
            if hasattr(self.homepage, "execute_skill"):
                try:
                    return self.homepage.execute_skill(method, params, context or {})
                except Exception as e:
                    logger.error(f"[SkillAgent] Execute skill failed: {e}")
                    return {"error": str(e)}
            logger.warning(f"[SkillAgent] No executor for skill: {method}")
            return {"error": f"No executor for skill: {method}"}

        try:
            return executor(params, context or {})
        except Exception as e:
            logger.error(f"[SkillAgent] Execution error: {e}")
            return {"error": str(e)}

    def get_skill_context_prompt(self) -> str:
        """生成技能上下文提示"""
        if not self.skills:
            return ""

        prompt = "\n\n## 可用技能\n"
        prompt += "你可以使用以下技能来帮助完成任务：\n\n"

        for name, skill in self.skills.items():
            prompt += f"### {skill.name}\n"
            prompt += f"- 功能: {skill.description}\n"
            prompt += f"- 调用方法: `{skill.method}`\n"
            if skill.params_schema:
                prompt += (
                    f"- 参数: {json.dumps(skill.params_schema, ensure_ascii=False)}\n"
                )
            prompt += "\n"

        prompt += "\n技能调用格式：\n"
        prompt += "```plugin_call\n"
        prompt += '{"method": "技能名", "params": {...}}\n'
        prompt += "```\n"

        return prompt

    def get_all_skills(self) -> List[SkillDefinition]:
        """获取所有技能"""
        return list(self.skills.values())


def create_skill_agent(homepage=None) -> SkillAgent:
    """创建技能代理实例"""
    return SkillAgent(homepage)
