# 组件扩展说明信息
Agent 技能执行智能体

功能：
- 接收 SkillRouter 输出的 selected_skills_detail（仅选中技能的完整文档）
- 将选中技能文档注入 system_prompt，LLM 阅读后自主决策是否调用技能
- 解析 LLM 返回的技能执行请求，在沙箱中执行命令
- 执行结果反馈给 LLM，生成最终回复