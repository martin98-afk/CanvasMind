# 工具配置指南

## 依赖安装

```bash
# 安装所有分析工具
pip install flake8 pylint bandit radon

# 或使用 requirements.txt
pip install -r requirements-dev.txt
```

## flake8 配置 (.flake8)

```ini
[flake8]
max-line-length = 100
exclude = .git,__pycache__,build,dist,venv,.venv
ignore = E203,W503
per-file-ignores =
    __init__.py:F401
    tests/*:S101
```

## pylint 配置 (.pylintrc)

```ini
[MASTER]
jobs=0
persistent=yes

[MESSAGES CONTROL]
disable=C0114,C0115,C0116

[FORMAT]
max-line-length=100

[DESIGN]
max-args=10
max-locals=20
max-returns=6
max-branches=12
max-statements=50
max-attributes=7
max-public-methods=20
```

## 性能优化建议

### 大型项目扫描
```bash
# 并行检查
flake8 project/ --jobs=4

# 仅检查 Python 文件
bandit -r project/ --aggregate=file

# 排除测试和虚拟环境
pylint project/ --ignore=tests,venv
```

## 输出格式说明

| 工具 | 格式选项 | 用途 |
|------|----------|------|
| flake8 | --format=json | 机器可读 |
| pylint | --output-format=json | 结构化数据 |
| bandit | -f json | 安全报告 |
| radon | -j | JSON 输出 |
