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


class SkillRouterComponent(BaseComponent):
    name = "技能路由选择器"
    category = "大模型组件/智能体SKILLS"
    description = "根据用户输入筛选相关技能，输出选中技能的完整文档"
    requirements = "orjson,openai,PyYAML"

    inputs = [
        PortDefinition(name="user_input", label="用户输入", type=ArgumentType.TEXT),
        PortDefinition(name="skill_docs", label="技能文档集合", type=ArgumentType.JSON),
        PortDefinition(name="skills_list", label="技能列表", type=ArgumentType.JSON),
        PortDefinition(name="history", label="对话历史", type=ArgumentType.JSON, optional=True),
    ]

    outputs = [
        PortDefinition(name="selected_skill_ids", label="选中技能 ID", type=ArgumentType.JSON),
        PortDefinition(name="selected_skills_detail", label="选中技能详情", type=ArgumentType.JSON),
        PortDefinition(name="routing_reason", label="路由原因", type=ArgumentType.TEXT),
        PortDefinition(name="fallback_to_chat", label="降级纯聊天", type=ArgumentType.BOOL),
    ]

    properties = {
        "model_for_routing": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="路由用模型",
        ),
        "routing_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="keyword",
            label="路由模式",
            description="keyword:关键词匹配; llm:LLM 决策; hybrid: 混合",
            choices=["keyword", "llm", "hybrid"]
        ),
        "max_selected": PropertyDefinition(
            type=PropertyType.INT,
            default=2,
            label="最大选中数",
        ),
        "min_match_score": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.3",
            label="最小匹配分",
            min=0.0,
            max=1.0,
            step=0.1,
        ),
        "enable_fallback": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="无匹配时降级聊天",
        ),
    }

    def run(self, params, inputs):
        import re
        import json
        import time

        self.params = params
        user_input = (inputs.user_input or "").strip().lower()
        skill_docs = inputs.skill_docs or {}
        skills_list = inputs.skills_list or []

        if not user_input:
            return self._no_skill_output("用户输入为空")
        if not skills_list:
            return self._no_skill_output("技能列表为空")

        start = time.time()
        selected_ids = []
        reasons = []

        # === 1. 关键词匹配 ===
        if params.routing_mode in ["keyword", "hybrid"]:
            matched = self._keyword_match(user_input, skills_list, float(params.min_match_score))
            if matched:
                selected_ids.extend([m["id"] for m in matched[:params.max_selected]])
                reasons.append(f"keyword:[{','.join(m['id'] for m in matched[:2])}]")

        # === 2. LLM 决策（可选）===
        if params.routing_mode in ["llm", "hybrid"] and len(selected_ids) < params.max_selected and skills_list:
            llm_selected = self._llm_route(user_input, skills_list, params.max_selected - len(selected_ids), params.model_for_routing)
            new_ids = [s for s in llm_selected if s not in selected_ids]
            if new_ids:
                selected_ids.extend(new_ids)
                reasons.append(f"llm:[{','.join(new_ids)}]")

        # === 3. 去重 + 截断 ===
        selected_ids = list(dict.fromkeys(selected_ids))[:params.max_selected]

        if not selected_ids:
            if params.enable_fallback:
                return {
                    "selected_skill_ids": [],
                    "selected_skills_detail": {},
                    "routing_reason": "无匹配技能，降级纯聊天",
                    "fallback_to_chat": True,
                }
            return self._no_skill_output("未匹配到技能且 fallback 禁用")

        # === 4. 筛选完整文档 ===
        selected_details = {}
        for skill_id in selected_ids:
            if skill_id in skill_docs:
                selected_details[skill_id] = skill_docs[skill_id]

        duration = time.time() - start
        self.logger.info(f"✅ 路由完成 | 选中:{selected_ids} | 原因:{'; '.join(reasons)} | 耗时:{duration:.3f}s")

        return {
            "selected_skill_ids": selected_ids,
            "selected_skills_detail": selected_details,
            "routing_reason": "; ".join(reasons),
            "fallback_to_chat": False,
        }

    def _keyword_match(self, query, skills_list, min_score):
        import re
        query_words = set(re.findall(r'[\w\u4e00-\u9fa5]+', query))
        if not query_words:
            return []
        scored = []
        for skill in skills_list:
            score = 0.0
            if any(w in skill["name"].lower() for w in query_words):
                score += 0.5
            if any(w in skill["description"].lower() for w in query_words):
                score += 0.3
            for kw in skill.get("trigger_keywords", []):
                if any(w in kw.lower() for w in query_words):
                    score += 0.4
                    break
            for tag in skill.get("tags", []):
                if any(w in tag.lower() for w in query_words):
                    score += 0.2
                    break
            if score >= min_score:
                scored.append((skill, min(score, 1.0)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in scored]

    def _llm_route(self, query, skills_list, max_select, model_var):
        import re
        import json
        try:
            from openai import OpenAI
            index_summary = "\n".join([
                f"- {s['id']}: {s['name']} | {s['description'][:50]}... | 触发:[{','.join(s.get('trigger_keywords', [])[:3])}]"
                for s in skills_list[:20]
            ])
            prompt = f"""你是一个技能路由助手。用户输入："{query}"
可用技能列表：
{index_summary}
请选出最多 {max_select} 个最相关的技能 ID（仅返回 JSON 数组）：
```json
["skill_id_1", "skill_id_2"]
```"""
            model_cfg = model_var[1] if isinstance(model_var, (list, tuple)) and len(model_var) > 1 else {}
            client = OpenAI(
                api_key=model_cfg.get("API_KEY", ""),
                base_url=model_cfg.get("API_URL", "https://api.openai.com/v1").rstrip("/")
            )
            resp = client.chat.completions.create(
                model=model_cfg.get("模型名称", "gpt-3.5-turbo"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1
            )
            content = resp.choices[0].message.content or ""
            match = re.search(r'\[.*?\]', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            self.logger.debug(f"LLM 路由失败，降级关键词：{e}")
        return []

    def _no_skill_output(self, reason):
        return {
            "selected_skill_ids": [],
            "selected_skills_detail": {},
            "routing_reason": reason,
            "fallback_to_chat": True,
        }