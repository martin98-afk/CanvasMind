# 组件扩展说明信息
本地技能包加载器组件

功能：
- 通过属性选择本地 skills 目录
- 验证目录结构（manifest.json + skills/）
- 解析所有 SKILL.md 文件
- 输出 skill_docs + skill_registry 供 AgentSkillsComponent 使用
- 支持缓存机制，避免重复解析