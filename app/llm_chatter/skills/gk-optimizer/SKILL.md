---
name: gk-optimizer
description: 工况寻优范围调整专家规则脚本生成技能。当用户需要根据工业领域专家规则批量调整Excel中的工况寻优范围时使用此技能。触发场景包括：(1)用户提供工况Excel和专家规则，需要生成Python脚本；(2)用户需要将专家经验转化为可执行的脚本；(3)基于特定工况条件（如铁口状态、设备运行）动态计算寻优范围。
---

# 工况寻优专家规则脚本生成器

## 技能用途

将工业领域专家规则转换为Python脚本。

## 技能参考文件
以下文件可在技能workspace中找到，在使用技能中务必先读取以了解技能详情。
Excel分析脚本在 `references/excel_analyzer.py` 中，可以使用该文件分析目标xlsx表格。
工况结构样例在 `references/Excel结构说明.md` 中，可以读取该文件进行参考。
样例脚本在 `references/样例脚本.py` 中，可以了解脚本最终输出结构。

## 输入文件

用户需提供以下两个文件：
1. **工况Excel文件** - 包含工况数据的Excel文件，含寻优上限/下限列
2. **专家规则提示词** - 包含标签映射和专家规则定义

## 工作流程

读取相关文档，excel_analyzer.py, Excel结构说明.md, 用户提示词，目标excel

### 1. 解析专家规则

从专家规则提示词中提取：
- 标签映射表：原始测点名 → 简化标签
- 规则定义：条件判断、计算逻辑、阈值设置

### 2. 分析Excel结构

**使用Excel分析脚本快速了解结构：**

```bash
# 分析指定Excel文件
python references/excel_analyzer.py <excel文件路径>

# 分析并输出JSON格式（方便程序处理）
python references/excel_analyzer.py <excel文件路径> --json

# 分析并保存报告
python references/excel_analyzer.py <excel文件路径> -o report.txt
```

分析脚本会自动输出：
- 每个Sheet的行列数
- **寻优上限/下限列位置**（★标记）
- **工况参数列范围**
- 所有列名和样例值
- **脚本生成建议**（LABEL_MAPPING模板、列索引建议）

确定：
- 数据列索引（基于标签映射）
- 寻优上限/下限列位置
- 需要计算的数值列

### 3. 生成Python脚本

**⚠️ 重要提醒：生成的脚本必须输出到新文件，不得覆盖原文件！**

参考 `样例脚本.py` 的整体格式，生成必须包含以下部分的脚本：

```python
# -*- coding: utf-8 -*-
"""
[脚本功能描述]
专家规则:
    [规则1]
    [规则2]
    ...
"""

import openpyxl
import os
import argparse
from typing import List, Tuple, Optional

# 标签映射表
LABEL_MAPPING = {
    # 从专家规则提示词中提取
}

# [其他配置：列索引、基础值定义等]
# 从专家规则中提取

def safe_to_number(value) -> float:
    """安全地将值转换为数字类型"""
    # 实现...

def calculate_limits(row_data: List) -> Tuple[float, float]:
    """根据专家规则计算寻优上限和下限"""
    # 实现专家规则逻辑
    return upper, lower

def process_excel_file(input_filepath: str, output_filepath: Optional[str] = None) -> None:
    """处理Excel文件，根据专家规则更新寻优上限和下限"""
    # 默认输出到新文件，不覆盖原文件
    # 实现...

def main():
    """主函数"""
    # 命令行参数解析
    parser = argparse.ArgumentParser(description="[描述]")
    parser.add_argument("input_file", nargs="?", default=None, help="输入Excel文件路径")
    parser.add_argument("output_file", nargs="?", default=None, help="输出Excel文件路径(可选，默认生成新文件)")
    # 处理逻辑...
```

生成脚本文件名固定为 `工况范围调整_{设备名称}.py`，设备名称一般通过文件路径、工况数据来判断。
入文件路径中包含类似：`一号高炉/工况数据_2023-05-01.xlsx`， 脚本名为 `工况范围调整_一号高炉.py`, 如工况数据包含设备名称：2#高炉出铁场2#除尘风机，也可以用作判断。

### 4. 关键实现要点

#### 标签映射表

```python
LABEL_MAPPING = {
    "完整测点名": "简化标签",
    "设备|点位|描述": "标签名",
}
```

#### 条件判断逻辑

根据专家规则实现条件判断：
- 多条件组合判断
- 数值累加与阈值比较
- 状态映射与计数

#### 计算公式

根据专家规则定义计算公式：
- 基础值定义
- 增量计算
- 多目标综合计算

## 输出要求

生成的python脚本应满足：
1. 接收输入待处理excel路径以及输出处理完excel路径参数
2. 修改寻优上限和下限列
3. 包含详细的文档注释

### 5. 验证工况调整效果

脚本生成后，执行并验证结果：
- 运行生成的脚本处理Excel文件，处理用户提供的工况数据，输出到相同文件夹下，文件名后缀增加 `_processed`
- 检查输出文件的"寻优上限"和"寻优下限"列
- 对比调整前后的数值分布是否合理
- 确认修改仅限于输出文件，原文件未被改动
- 提供样例计算流程，供用户校验