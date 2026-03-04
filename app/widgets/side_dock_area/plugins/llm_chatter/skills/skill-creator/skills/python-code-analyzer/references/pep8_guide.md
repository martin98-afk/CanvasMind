# Python 代码规范指南 (PEP8)

## 核心规范

### 1. 代码缩进
- 使用 4 个空格进行缩进
- 不要使用制表符 (Tab)
- 续行使用悬挂缩进

### 2. 行长度
- 最大行长度：100 字符
- 注释和文档字符串可以例外

### 3. 空行
- 顶层函数和类定义之间：2 个空行
- 类内方法之间：1 个空行
- 函数内逻辑段落：1 个空行

### 4. 导入语句
```python
# 正确顺序
import os
import sys

import requests
import numpy as np

from . import module
from ..parent import module
```

### 5. 命名规范
- 函数/变量：snake_case (如：my_function)
- 类名：PascalCase (如：MyClass)
- 常量：UPPER_CASE (如：MAX_VALUE)
- 私有成员：_prefix (如：_internal_method)

### 6. 常见违规代码及修复

#### E302 - 顶部缺少空行
```python
# ❌ 错误
import os
def func():
    pass

# ✅ 正确
import os


def func():
    pass
```

#### E501 - 行过长
```python
# ❌ 错误
result = some_function_that_has_a_very_long_name(arg1, arg2, arg3, arg4, arg5)

# ✅ 正确
result = some_function_that_has_a_very_long_name(
    arg1, arg2, arg3, arg4, arg5
)
```

#### E711 - 与 None 比较
```python
# ❌ 错误
if value == None:
    pass

# ✅ 正确
if value is None:
    pass
```

## 检查命令

```bash
# 基础检查
flake8 project/

# 自定义行长度
flake8 project/ --max-line-length=100

# 忽略特定错误
flake8 project/ --ignore=E501,W503

# 生成报告
flake8 project/ --format=json --output-report=report.json
```
