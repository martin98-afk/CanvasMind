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


class Component(BaseComponent):
    name = "建表组件"
    category = "sqlite套件"
    description = "生成SQL建表语句，支持动态字段配置"
    requirements = ""
    inputs = []
    outputs = [
        PortDefinition(name="status", label="操作状态", type=ArgumentType.TEXT),
    ]
    properties = {
        "database_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="数据库文件",
        ),
        "table_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="my_table",
            label="表名",
        ),
        "fields": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="表结构",
            schema={
                "field_name": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="字段名",
                ),
                "field_type": PropertyDefinition(
                    type=PropertyType.CHOICE,
                    default="TEXT",
                    label="字段类型",
                    choices=["TEXT", "INTEGER", "REAL", "BLOB", "BOOLEAN"]
                ),
                "filed_desc": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="字段描述",
                ),
                "is_primary": PropertyDefinition(
                    type=PropertyType.BOOL,
                    default=False,
                    label="是否为主键",
                ),
            }
        ),
    }

    def run(self, params, inputs=None):
        """
        生成SQL建表语句
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import sqlite3
        # 获取输入参数
        db_path = params.get("database_path")
        table_name = params.table_name
        fields = params.fields  # 从属性中获取字段配置

        # 验证字段数据
        if not fields:
            return {
                "sql_statement": "",
                "status": "错误：必须配置至少一个字段"
            }

        # 生成建表语句
        try:
            # 类型映射表
            valid_types = {
                "TEXT": ["string", "text", "str"],
                "INTEGER": ["int", "integer", "number"],
                "REAL": ["float", "real"],
                "BLOB": ["blob", "binary"],
                "BOOLEAN": ["bool", "boolean"]
            }

            # 处理字段定义
            field_definitions = []
            primary_key = None

            for field in fields:
                field_name = field.get("field_name", "").strip()
                field_type = field.get("field_type", "").upper()
                description = field.get("filed_desc", "")
                is_primary = field.get("is_primary", False)

                # 类型转换
                if field_type not in valid_types:
                    for k, v in valid_types.items():
                        if field_type in v:
                            field_type = k
                            break


                # 处理主键
                if is_primary:
                    if primary_key:
                        raise ValueError(f"多个主键定义: {primary_key} 和 {field_name}")
                    primary_key = field_name

                # 添加字段定义
                field_definitions.append(f"    {field_name} {field_type}")
                if description:
                    field_definitions[-1] += f"  -- {description}"

            # 构建SQL语句
            fiile_info = ',\n'.join(field_definitions)
            sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n{fiile_info}\n);"
            print(sql)            
            conn = sqlite3.connect(db_path, check_same_thread=params.check_same_thread)
            cursor = conn.cursor()
            cursor.executescript(sql)
            
            # 提交事务
            conn.commit()
            return {
                "sql_statement": sql,
                "status": "成功生成建表语句"
            }
        except Exception as e:
            self.logger.error(f"建表失败: {str(e)}")
            return {
                "status": f"错误: {str(e)}"
            }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "table_name": "users",
            "fields": [
                {"name": "id", "type": "INTEGER", "description": "用户ID", "is_primary": True},
                {"name": "name", "type": "TEXT", "description": "用户名", "is_primary": False},
                {"name": "is_active", "type": "BOOLEAN", "description": "是否激活", "is_primary": False}
            ],
            "database_type": "sqlite"
        },
        inputs={"database_path": "test.db"},
        global_vars={},
        node_id="table_create",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
