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


class SQLiteQuery(BaseComponent):
    name = "查询数据"
    category = "sqlite套件"
    description = "从表中筛选数据"
    
    inputs = []
    outputs = [
        PortDefinition(name="result", label="结果列表", type=ArgumentType.JSON),
        PortDefinition(name="count", label="结果数量", type=ArgumentType.INT),
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
        "condition": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="WHERE条件",
        ),
        "limit": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="限制行数",
        ),
    }

    def run(self, params, inputs=None):
        import sqlite3
        db_path = params.get("database_path")
        sql = f"SELECT * FROM {params.table_name}"
        if params.condition:
            sql += f" WHERE {params.condition}"
        sql += f" LIMIT {params.limit}"
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row # 使结果可以通过列名访问
                cursor = conn.cursor()
                cursor.execute(sql)
                rows = [dict(row) for row in cursor.fetchall()]
                return {"result": rows, "count": len(rows)}
        except Exception as e:
            self.logger.error(f"查询失败: {e}")
            return {"result": [], "count": 0}