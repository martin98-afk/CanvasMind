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
    name = "时序数据读取"
    category = "数据集成"
    description = "获取TrendDB时序库数据"
    requirements = "loguru,numpy,openpyxl,pandas,pyyaml,requests,schedule,trenddb,trenddb_client"
    inputs = [
        PortDefinition(name="start_time", label="开始时间", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="end_time", label="结束时间", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="tags", label="测点列表", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="data", label="时序数据", type=ArgumentType.CSV),
        PortDefinition(name="tags_info", label="测点信息", type=ArgumentType.JSON),
    ]
    properties = {
        "version": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="v5",
            label="版本",
            description="TrendDB版本",
            choices=["v4", "v5"]
        ),
        "host": PropertyDefinition(
            type=PropertyType.TEXT,
            default="172.17.253.107",
            label="主机地址",
            description="TrendDB服务器地址",
        ),
        "port": PropertyDefinition(
            type=PropertyType.INT,
            default=20010,
            label="端口",
            description="TrendDB服务端口",
        ),
        "dbname": PropertyDefinition(
            type=PropertyType.TEXT,
            default="db101",
            label="数据库名",
            description="时序数据库名称",
        ),
        "username": PropertyDefinition(
            type=PropertyType.TEXT,
            default="system",
            label="用户名",
            description="连接用户名",
        ),
        "password": PropertyDefinition(
            type=PropertyType.TEXT,
            default="luculent123@",
            label="密码",
            description="连接密码",
        ),
        "query_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="realtime",
            label="查询类型",
            description="查询类型：实时值/历史数据",
            choices=["realtime", "history"]
        ),
        "start_time": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="开始时间",
            description="历史数据查询开始时间，格式: YYYY-MM-DD HH:MM:SS",
        ),
        "end_time": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="结束时间",
            description="历史数据查询结束时间，格式: YYYY-MM-DD HH:MM:SS",
        ),
        "interval": PropertyDefinition(
            type=PropertyType.INT,
            default=1000,
            label="采样间隔(ms)",
            description="历史数据采样间隔(毫秒)",
        ),
        "tags": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="测点列表",
            description="添加要查询的测点",
            schema={
                "tag_name": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="测点名称",
                    description="时序数据库中的测点名",
                ),
            }
        ),
    }

    def _get_trenddb_manager(self, params):
        """获取TrendDB管理器实例"""
        # 动态导入扩展资源中的trenddb模块
        from trenddb import TrendDBManager

        version = params.get("version", "v5")
        
        if version == "v5":
            v5_config = {
                "host": params.get("host", "172.17.253.107"),
                "port": str(params.get("port", 20010)),
                "dbname": params.get("dbname", "db101"),
                "username": params.get("username", "system"),
                "password": params.get("password", "luculent123@"),
            }
            return TrendDBManager(version="v5", v5_config=v5_config)
        else:
            return TrendDBManager(
                version="v4",
                ip=params.get("host", "168.168.10.101"),
                port=params.get("port", 6688),
                dbname=params.get("dbname", "db112"),
                username=params.get("username", ""),
                password=params.get("password", ""),
            )

    def _parse_tags(self, tags_param, tags_input):
        """解析测点列表"""
        tags = []
        if tags_param is not None:
            tags += [tag.tag_name for tag in tags_param]
        if tags_input is not None:
            tags += [tag.tag_name for tag in tags_input]
        return tags

    def _parse_time_range(self, params, inputs):
        """解析时间范围"""
        import datetime
        
        # 优先使用输入端口的时间
        start_time = inputs.get("start_time") if inputs else None
        end_time = inputs.get("end_time") if inputs else None
        
        # 其次使用属性配置
        if not start_time:
            start_time = params.get("start_time", "")
        if not end_time:
            end_time = params.get("end_time", "")
        
        # 如果都没有设置，默认查询最近1小时
        if not start_time or not end_time:
            now = datetime.datetime.now()
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")
            start_time = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        return start_time, end_time

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        import pandas as pd
        import datetime

        inputs = inputs or {}
        
        # 获取TrendDB管理器
        db_manager = self._get_trenddb_manager(params)
        if db_manager is None:
            return {
                "data": None,
                "tags_info": [],
                "error": "无法连接TrendDB，请检查配置"
            }

        query_type = params.get("query_type", "realtime")
        tags_param = params.get("tags", [])
        tags_input = inputs.get("tags")
        tags = self._parse_tags(tags_param, tags_input)
        
        result_data = None
        tags_info = []

        try:
            if query_type == "realtime":
                # 获取实时值
                if not tags:
                    self.logger.warning("未配置测点列表，无法查询实时值")
                    return {"data": None, "tags_info": [], "error": "请配置测点列表"}
                
                self.logger.info(f"查询实时值，测点: {tags}")
                realtime_values = db_manager.get_realtime_values(tags)
                result_data = realtime_values
                self.logger.info(f"获取到 {len(realtime_values)} 个测点的实时值")

            elif query_type == "history":
                # 获取历史数据
                if not tags:
                    self.logger.warning("未配置测点列表，无法查询历史数据")
                    return {"data": None, "tags_info": [], "error": "请配置测点列表"}
                
                start_time, end_time = self._parse_time_range(params, inputs)
                interval = params.get("interval", 1000)
                
                self.logger.info(f"查询历史数据，时间范围: {start_time} ~ {end_time}, 测点: {tags}")
                
                # 转换时间戳
                start_utc = int(datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp())
                end_utc = int(datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp())
                
                # 查询历史数据
                history_data = db_manager.get_history_values(
                    tags, start_utc, end_utc, interval
                )
                
                # 转换为DataFrame
                if history_data and history_data.get("timestamp"):
                    df = pd.DataFrame(history_data)
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                    df.set_index("timestamp", inplace=True)
                    df = df[~df.index.duplicated(keep="first")]
                    result_data = df
                    self.logger.info(f"历史数据查询成功，共 {len(df)} 条记录")
                else:
                    result_data = pd.DataFrame()
                    self.logger.warning("未获取到历史数据")

        except Exception as e:
            self.logger.error(f"查询数据失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {
                "data": result_data,
                "tags_info": tags_info,
                "error": str(e)
            }
        finally:
            # 关闭数据库连接
            if db_manager:
                db_manager.close()

        return {
            "data": result_data,
            "tags_info": tags_info
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    # 测试代码
    model = Component()
    
    # 测试查询实时值
    result = model.debug(
        params={
            "version": "v5",
            "host": "172.17.253.107",
            "port": 20010,
            "dbname": "db101",
            "username": "system",
            "password": "luculent123@",
            "query_type": "realtime",
            "tags": [
                {"tag_name": "tag1"},
                {"tag_name": "tag2"},
            ],
        },
        inputs={},
        node_id="测试模型",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
