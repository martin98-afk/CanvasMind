---
name: python-code-analyzer
description: 自动检测 Python 项目的代码质量和代码规范问题。当用户需要扫描 Python 代码项目、检查代码质量、发现安全漏洞、验证代码规范时使用此技能。支持 PEP8 规范检查、代码复杂度分析、安全漏洞扫描。
license: Complete terms in LICENSE.txt
---

# Python Code Analyzer

此技能用于自动检测 Python 项目的代码质量和代码规范问题。

## 触发条件

当用户请求涉及以下场景时触发此技能：
- 扫描 Python 项目代码质量
- 检查代码是否符合 PEP8 规范
- 发现代码中的安全漏洞
- 分析代码复杂度
- 生成代码质量报告

## 核心功能

### 1. 代码规范检查
使用 flake8 检查代码是否符合 PEP8 规范：
```bash
flake8 <project_path> --max-line-length=100
```

### 2. 代码质量分析
使用 pylint 进行代码质量评分：
```bash
pylint <project_path> --output-format=text
```

### 3. 安全漏洞扫描
使用 bandit 检测安全漏洞：
```bash
bandit -r <project_path> -f json -o report.json
```

### 4. 代码复杂度分析
使用 radon 计算圈复杂度：
```bash
radon cc <project_path> -a -s
```

## 工作流程

1. **确认项目路径** - 询问用户要分析的 Python 项目路径
2. **选择检测类型** - 确认用户需要检测的内容（规范/质量/安全/全部）
3. **执行分析脚本** - 运行 scripts/analyze.py 进行综合分析
4. **生成报告** - 输出结构化的检测报告
5. **提供修复建议** - 针对发现的问题给出具体修复方案

## 参考文档

- **代码规范**：详见 references/pep8_guide.md
- **安全最佳实践**：详见 references/security_best_practices.md
- **工具配置**：详见 references/tool_configs.md

## 输出格式

检测报告应包含：
- 问题总数和严重程度分布
- 按文件分类的问题列表
- 每个问题的具体位置和描述
- 修复建议和示例代码
