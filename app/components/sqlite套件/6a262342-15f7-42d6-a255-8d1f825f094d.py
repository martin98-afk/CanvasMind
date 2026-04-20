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


class SQLiteExecute(BaseComponent):
    name = "执行SQL"
    category = "sqlite套件"
    description = "执行自定义SQL语句"
    
    inputs = [
        PortDefinition(name="sql", label="SQL语句", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="status", label="状态", type=ArgumentType.TEXT),
        PortDefinition(name="data", label="查询结果", type=ArgumentType.JSON),
    ]

    properties = {
        "database_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="数据库文件",
        ),
    }

    def run(self, params, inputs=None):
        import sqlite3
        db_path = params.get("database_path")
        sql = inputs.get("sql")
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                if sql.strip().upper().startswith("SELECT"):
                    conn.row_factory = sqlite3.Row
                    data = [dict(r) for r in cursor.fetchall()]
                    return {"status": "查询成功", "data": data}
                else:
                    conn.commit()
                    return {"status": "执行完成", "data": [{"affected_rows": cursor.rowcount}]}
        except Exception as e:
            return {"status": f"错误: {str(e)}", "data": []}