from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum

class VariableScope(str, Enum):
    GLOBAL = "global"
    CANVAS = "canvas"
    SESSION = "session"

class ExecutionEnvironment(BaseModel):
    user_id: Optional[str] = None
    canvas_id: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CustomVariable(BaseModel):
    value: Any = None
    description: Optional[str] = None
    scope: VariableScope = VariableScope.GLOBAL
    read_only: bool = False

class GlobalVariableContext(BaseModel):
    env: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    custom: Dict[str, CustomVariable] = Field(default_factory=dict)

    class Config:
        # 允许任意类型（因为 value 可能是 list/dict 等）
        arbitrary_types_allowed = True

    def get(self, key: str, default=None) -> Any:
        """兼容旧 dict 用法：global_vars.get('key')"""
        if key in self.custom:
            return self.custom[key].value
        return default

    def set(self, key: str, value: Any) -> None:
        """设置自定义变量（忽略只读检查，由业务层控制）"""
        if key not in self.custom:
            self.custom[key] = CustomVariable(value=value)
        else:
            self.custom[key].value = value

    def to_dict(self) -> Dict[str, Any]:
        """兼容旧逻辑：返回扁平字典（仅 custom 变量）"""
        return {k: v.value for k, v in self.custom.items()} | self.env.dict()