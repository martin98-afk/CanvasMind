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


class SQLiteGetTableSchema(BaseComponent):
    name = "查询表结构"
    category = "sqlite套件"
    description = "获取指定表的列信息、类型及约束"
    
    inputs = []
    outputs = [
        PortDefinition(name="fields", label="字段列表", type=ArgumentType.JSON),
        PortDefinition(name="column_names", label="纯列名列表", type=ArgumentType.JSON),
        PortDefinition(name="primary_key", label="主键字段", type=ArgumentType.TEXT),
        PortDefinition(name="status", label="状态", type=ArgumentType.TEXT),
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
        table_name = params.table_name

        if not table_name:
            return {"status": "错误: 未提供表名", "fields": []}

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # 执行 PRAGMA 命令获取表信息
                # 返回列: cid, name, type, notnull, dflt_value, pk
                cursor.execute(f"PRAGMA table_info('{table_name}')")
                rows = cursor.fetchall()
                
                if not rows:
                    return {"status": f"未找到表: {table_name}", "fields": []}

                fields_info = []
                column_names = []
                primary_key = None

                for row in rows:
                    field_data = {
                        "name": row["name"],
                        "type": row["type"],
                        "not_null": bool(row["notnull"]),
                        "default_value": row["dflt_value"],
                        "is_primary": bool(row["pk"])
                    }
                    fields_info.append(field_data)
                    column_names.append(row["name"])
                    if row["pk"]:
                        primary_key = row["name"]

                return {
                    "fields": fields_info,
                    "column_names": column_names,
                    "primary_key": primary_key,
                    "status": "查询成功"
                }
        except Exception as e:
            return {
                "status": f"查询失败: {str(e)}",
                "fields": [],
                "column_names": []
            }