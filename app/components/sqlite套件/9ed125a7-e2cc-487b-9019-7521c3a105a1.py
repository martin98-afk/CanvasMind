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
    name = "新建数据库"
    category = "sqlite套件"
    description = "创建新的SQLite数据库文件（不执行SQL脚本）"
    requirements = ""
    inputs = [
    ]
    outputs = [
        PortDefinition(name="status", label="操作状态", type=ArgumentType.TEXT),
        PortDefinition(name="database_path", label="数据库路径", type=ArgumentType.TEXT),
    ]
    properties = {
        "database_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="数据库名",
        ),
        "overwrite": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="覆盖已存在文件",
        ),
        "check_same_thread": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用多线程支持",
        ),
    }

    def run(self, params, inputs=None):
        """
        创建SQLite数据库文件（仅初始化，不执行SQL脚本）
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import sqlite3
        import os
        from pathlib import Path

        # 获取输入参数
        db_path = params.get("database_name", "example.db")
        if not db_path.endswith(".db"):
            db_path = f"{db_path}.db"

        # 处理文件存在情况
        if os.path.exists(db_path) and not params.overwrite:
            return {
                "status": f"错误：文件 {db_path} 已存在，设置 overwrite=True 可覆盖",
                "database_path": ""
            }

        try:
            # 创建数据库文件
            conn = sqlite3.connect(db_path, check_same_thread=params.check_same_thread)
            cursor = conn.cursor()

            # 仅创建数据库文件，不执行任何SQL脚本
            return {
                "status": f"成功创建数据库: {db_path}",
                "database_path": str(Path(db_path).resolve())
            }
        except Exception as e:
            self.logger.error(f"数据库创建失败: {str(e)}")
            return {
                "status": f"错误: {str(e)}",
                "database_path": ""
            }
        finally:
            if 'conn' in locals():
                conn.close()


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"overwrite": "False", "check_same_thread": "True"},
        inputs={"database_path": "test.db"},
        global_vars={},
        node_id="sqlite_create",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
