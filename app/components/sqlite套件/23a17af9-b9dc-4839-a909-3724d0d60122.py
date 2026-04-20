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


class SQLiteInsert(BaseComponent):
    name = "插入数据"
    category = "sqlite套件"
    description = "将数据（字典或列表）写入指定表"
    
    inputs = [
        PortDefinition(name="data", label="待插入数据", type=ArgumentType.JSON), # 支持Dict或List[Dict]
    ]
    outputs = [
        PortDefinition(name="status", label="操作状态", type=ArgumentType.TEXT),
        PortDefinition(name="row_count", label="影响行数", type=ArgumentType.INT),
    ]
    properties = {
        "database_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="数据库文件",
        ),
        "table_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="表名",
        ),
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="INSERT",
            label="插入模式",
            choices=["INSERT", "REPLACE", "INSERT OR IGNORE"]
        ),
    }

    def run(self, params, inputs=None):
        import sqlite3
        db_path = params.get("database_path")
        data = inputs.get("data")
        if not data: return {"status": "跳过: 无数据内容"}

        records = [data] if isinstance(data, dict) else data
        if not records: return {"status": "跳过: 列表为空"}

        columns = list(records[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        # 使用双引号包裹列名，支持数字列名
        col_names = ", ".join(['"' + str(col) + '"' for col in columns])
        sql = f"{params.mode} INTO {params.table_name} ({col_names}) VALUES ({placeholders})"
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                values = [tuple(r.values()) for r in records]
                cursor.executemany(sql, values)
                conn.commit()
                return {"status": "成功", "row_count": cursor.rowcount}
        except Exception as e:
            return {"status": f"失败: {str(e)}", "row_count": 0}