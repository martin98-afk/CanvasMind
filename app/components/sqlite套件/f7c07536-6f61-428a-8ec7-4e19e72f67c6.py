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


class SQLiteDelete(BaseComponent):
    name = "删除数据"
    category = "sqlite套件"
    description = "根据条件从指定表中删除数据"
    
    inputs = [
        PortDefinition(name="where_clause", label="条件语句(WHERE)", type=ArgumentType.TEXT), # 例如 "status = ?"
        PortDefinition(name="where_params", label="条件参数(List)", type=ArgumentType.JSON), # 例如 ["已过期"]
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
        "allow_empty_where": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="允许清空全表",
            description="如果勾选，当WHERE条件为空时将删除所有数据，请谨慎使用"
        ),
    }

    def run(self, params, inputs=None):
        import sqlite3
        db_path = params.get("database_path")
        where_clause = inputs.get("where_clause")
        where_params = inputs.get("where_params") or []

        # 安全检查
        if not where_clause and not params.allow_empty_where:
            return {"status": "跳过: 未提供条件且未开启‘允许清空全表’", "row_count": 0}

        sql = f"DELETE FROM {params.table_name}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        
        # 确保 where_params 是列表
        params_list = where_params if isinstance(where_params, list) else [where_params]

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params_list)
                conn.commit()
                return {"status": "成功", "row_count": cursor.rowcount}
        except Exception as e:
            return {"status": f"失败: {str(e)}", "row_count": 0}