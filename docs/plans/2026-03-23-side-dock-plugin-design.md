# 侧边栏插件系统改进设计

日期: 2026-03-23

## 目标

向 PyCharm 风格的侧边栏工具窗口系统靠拢，提升社区扩展性和专业级别软件的可用性。

## 核心改进

### 1. 插件协议 (Plugin Protocol)

新增 `PluginManifest` 数据类和 `PluginProtocol` 抽象基类：

```python
@dataclass
class PluginManifest:
    name: str                          # 唯一标识
    display_name: str = ""             # 中文显示名
    icon: Optional[QIcon] = None
    position: DockPosition = HIDDEN
    shortcut: Optional[str] = None     # 如 "Alt+1"
    dependencies: List[str] = []        # 依赖的其他插件名
    singleton: bool = True
    auto_activate: bool = True

class PluginProtocol(ABC):
    @abstractmethod
    def get_manifest(self) -> PluginManifest
    
    def on_activate(self): pass
    def on_deactivate(self): pass
```

### 2. 装饰器注册

新增 `@side_dock_plugin` 装饰器简化注册：

```python
@side_dock_plugin(
    name="llm_chat",
    position=DockPosition.BOTTOM,
    shortcut="Alt+C",
    dependencies=["canvas_context"]
)
class OpenAIChatToolWindow(ToolWindow, PluginProtocol):
    ...
```

### 3. 按钮交互增强

- **双击关闭**: 双击按钮关闭对应工具窗口
- **右键菜单**: 移动到顶部组/底部组/隐藏工具
- **拖拽排序**: 按钮可在组内拖拽排序

### 4. Registry 生命周期管理

扩展 `SideDockRegistry`：
- `_plugin_classes`: 存储插件类
- `_active_plugins`: 存储已激活插件实例
- `activate_plugin()`: 激活插件并调用 `on_activate()`
- `deactivate_plugin()`: 停用插件并调用 `on_deactivate()`
- 依赖自动解析

### 5. 向后兼容

现有插件无需修改即可继续工作。迁移路径：旧插件 → 实现 `PluginProtocol` → 使用装饰器。

## 文件变更

| 文件 | 变更 |
|------|------|
| `tool_window.py` | 新增 `PluginManifest`、`PluginProtocol` |
| `registry.py` | 扩展生命周期管理、新增装饰器 |
| `button_bar.py` | 双击关闭、右键菜单、拖拽排序 |

## 实施计划

1. 新增 `PluginManifest` 和 `PluginProtocol`
2. 扩展 `SideDockRegistry` 支持生命周期
3. 添加 `@side_dock_plugin` 装饰器
4. 按钮双击关闭 + 右键菜单
5. 按钮拖拽排序优化
