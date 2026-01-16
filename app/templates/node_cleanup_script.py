# -*- coding: utf-8 -*-
CLEANUP_CODE = """
import sys
import gc
_target_key = "{unique_key}"
if _target_key in sys.modules:
    # 移除模块引用
    del sys.modules[_target_key]
    # 清理全局命名空间中可能存在的残余（如果有的话）
    # 强制进行垃圾回收
    gc.collect()
"""