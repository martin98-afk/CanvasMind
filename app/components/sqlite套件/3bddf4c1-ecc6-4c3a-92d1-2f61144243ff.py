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


class SQLiteUpdate(BaseComponent):
    name = "更新数据"
    category = "sqlite套件"
    description = "根据条件更新指定表中的数据"
    
    inputs = [
        PortDefinition(name="data", label="更新数据(Dict)", type=ArgumentType.JSON), # 例如 {"name": "新名称", "age": 30}
        PortDefinition(name="where_clause", label="条件语句(WHERE)", type=ArgumentType.TEXT), # 例如 "id = ?"
        PortDefinition(name="where_params", label="条件参数(List)", type=ArgumentType.JSON), # 例如 [1]
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
    }

    def run(self, params, inputs=None):
        import sqlite3
        db_path = params.get("database_path")
        data = inputs.get("data")
        where_clause = inputs.get("where_clause")
        where_params = inputs.get("where_params") or []

        if not data or not isinstance(data, dict):
            return {"status": "跳过: 更新数据必须为字典格式", "row_count": 0}
        if not where_clause:
            return {"status": "跳过: 必须提供 WHERE 条件以防止全表更新", "row_count": 0}

        # 构建 SET 部分: col1 = ?, col2 = ?
        cols = data.keys()
        set_stmt = ", ".join([f"{col} = ?" for col in cols])
        sql = f"UPDATE {params.table_name} SET {set_stmt} WHERE {where_clause}"
        
        # 合并参数: 先是 SET 的值，然后是 WHERE 的值
        values = list(data.values()) + list(where_params if isinstance(where_params, list) else [where_params])

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
                conn.commit()
                return {"status": "成功", "row_count": cursor.rowcount}
        except Exception as e:
            return {"status": f"失败: {str(e)}", "row_count": 0}