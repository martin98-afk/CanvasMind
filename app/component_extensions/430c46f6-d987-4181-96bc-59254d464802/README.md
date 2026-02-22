# 组件扩展说明信息
技能路由组件

功能：
- 接收 LocalSkillPackageLoader 输出的 skill_docs + skills_list
- 根据用户输入匹配 skills_list，筛选相关技能
- 输出 selected_skills_detail（仅包含选中技能的完整文档）
- 确保 AgentSkillsComponent 只接收相关技能，避免全量注入 prompt