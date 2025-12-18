# -*- coding: utf-8 -*-
from app.widgets.side_dock_area.plugins.component_history.main_widget import ComponentHistoryToolWindow
from app.widgets.side_dock_area.plugins.component_info.main_widget import ComponentInfoWindow
from app.widgets.side_dock_area.plugins.llm_chatter.main_widget import OpenAIChatToolWindow
from app.widgets.side_dock_area.plugins.multi_console_with_variable_explorer.main_widget import MultiConsoleToolWindow
from app.widgets.side_dock_area.registry import SideDockRegistry
from app.widgets.side_dock_area.tool_window import DockPosition

SideDockRegistry.register("组件开发", ComponentInfoWindow.name, ComponentInfoWindow, DockPosition.TOP)
SideDockRegistry.register("组件开发", MultiConsoleToolWindow.name, MultiConsoleToolWindow, DockPosition.TOP)
SideDockRegistry.register("组件开发", ComponentHistoryToolWindow.name, ComponentHistoryToolWindow, DockPosition.TOP)
SideDockRegistry.register("组件开发", OpenAIChatToolWindow.name, OpenAIChatToolWindow, DockPosition.TOP)


class EditingSource:
    NONE = 0
    CODE = 1
    UI = 2


MODULE_TO_PACKAGE_MAP = {
    # 机器学习 / 计算机视觉
    'sklearn': 'scikit-learn',
    'skimage': 'scikit-image',
    'cv2': 'opencv-python',
    # 图像处理
    'PIL': 'Pillow',  # from PIL import Image
    # Web 解析
    'bs4': 'beautifulsoup4',
    # 配置与序列化
    'yaml': 'PyYAML',
    'dateutil': 'python-dateutil',  # from dateutil.parser import ...
    'jwt': 'PyJWT',  # import jwt
    # 加密
    'Crypto': 'pycryptodome',  # 注意：不是 pycrypto
    # 'Cryptodome': 'pycryptodomex',  # 如果用这个变体才需要
    # 串口通信
    'serial': 'pyserial',
    # Markdown 渲染
    'markdown': 'Markdown',  # 包名首字母大写
    # 文档解析
    'docx': 'python-docx',
    # Faker 数据生成
    'faker': 'Faker',  # 包名大写
    # 类型提示（可选）
    'typing_extensions': 'typing-extensions',  # 模块名下划线，包名中划线
    # TOML（第三方库）
    'tomli': 'tomli',
    'tomli_w': 'tomli-w',
}

BUILTIN_MODULES = set(
    ['__future__', 'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore', 'atexit',
     'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins', 'bz2', 'cProfile', 'calendar',
     'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop', 'collections', 'colorsys',
     'compileall', 'concurrent', 'configparser', 'contextlib', 'contextvars', 'copy', 'copyreg', 'crypt', 'csv',
     'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest',
     'email', 'encodings', 'ensurepip', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
     'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass', 'gettext', 'glob',
     'graphlib', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr',
     'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache',
     'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder',
     'msilib', 'msvcrt', 'multiprocessing', 'netrc', 'nis', 'nntplib', 'ntpath', 'numbers', 'operator',
     'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil',
     'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd',
     'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource',
     'rlcompleter', 'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal',
     'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'sre', 'sre_compile',
     'sre_constants', 'sre_parse', 'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess',
     'sunau', 'symbol', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib',
     'tempfile', 'termios', 'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize',
     'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata',
     'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser', 'winreg',
     'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib', 'zoneinfo']
)

LLM_CODE_CONTEXT = '''你是一个 CanvasMind 组件开发专家，以下是canvasmind组件开发代码规范：

#### 一、类结构要求
- 类名必须为英文名
- 继承自 `BaseComponent`:
- 不要在文件顶部写 `import`， 所有以下 BaseComponent、PortDefinition等预制定义会在执行时作为前缀动态加到前面，生成时不需要加。
- 参考以下样例，其中类属性都不能省略：
```python
class Component(BaseComponent):
    name = "组件显示名称"
    category = "所属分类"
    description = "简明功能描述"
    requirements = "依赖说明（如 '无'、'openai>=1.0'、'pandas, pillow' 等）"
    inputs = [
        PortDefinition(name="query", label="查询问题", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="context", label="检索结果", type=ArgumentType.TEXT),
        PortDefinition(name="documents", label="原始文档列表", type=ArgumentType.JSON),
    ]

    properties = {
        "top_k": PropertyDefinition(
            type=PropertyType.INT,
            label="返回结果数",
            default="3",
        ),
        "knowledge_base_id": PropertyDefinition(
            type=PropertyType.TEXT,
            label="知识库ID",
            default="default_kb",
        ),
    }
```

#### 二、元信息字段生成规范
1. `name`：用户友好的中文名称（如 `"大模型对话"`、`"CSV 列筛选器"`），不可与已有组件重名:
2. `category`：从合理分类中选择，如 `"大模型组件"`、`"数据处理"`、`"文件操作"`、`"可视化"`、`"逻辑控制"`、`"机器学习"` 等:
3. `description`：一句话说明组件功能，面向最终用户:
4. `requirements`：列出所需第三方包（如 `"pandas, openpyxl"`），若无则写 `""`:
5. `inputs`：列表，每个元素为 `PortDefinition(...)`，字段：
   - `name`：英文 snake_case（如 `"input_data"`）:
   - `label`：中文标签:
   - `type`：使用 `ArgumentType.XXX`:
   - `connection`：默认 `ConnectionType.SINGLE`:
6. `outputs`：同 `inputs`，且 `name` 必须与 `run` 返回字典的键一致:
7. `properties`：字典 `{prop_name: PropertyDefinition(...)}`，其中：
   - `prop_name`：英文 snake_case:
   - `type`：使用 `PropertyType.XXX`:
   - `default`：字符串形式的默认值:
   - `label`：中文标签:
   - 按类型补充字段（`choices`、`min/max/step`、`schema` 等）:
8. 端口类型(ArgumentType)目前支持：
TEXT = "文本"
INT = "整数"
FLOAT = "浮点数"
BOOL = "布尔值"
ARRAY = "列表"
CSV = "csv"
JSON = "json"
EXCEL = "excel"
FILE = "文件"
UPLOAD = "上传"
SKLEARNMODEL = "sklearn模型"
TORCHMODEL = "torch模型"
IMAGE = "图片"
9. 属性类型(PropertyType)目前支持:
TEXT = "文本"
MULTILINE = "多行文本"
LONGTEXT = "长文本"
INT = "整数"
FLOAT = "浮点数"
RANGE = "范围"
BOOL = "复选框"
CHOICE = "下拉框"
VARIABLE = "全局变量"
DYNAMICFORM = "动态表单"
10. 输入端口连接类型(ConnectionType)支持:
SINGLE = "单输入"
MULTIPLE = "多输入"
   
#### 三、run 方法规范
- 所有 import 语句必须写在 `run` 函数内部:
- run 函数参数: params, inputs
- 参数访问方式：
  - 属性：`params.prop_name`:
  - 输入：`inputs.port_name`:
  - 全局变量：`self.global_variable.var_name`:
- 返回值：必须是字典，键严格对应 `outputs` 中的 `name`，且包含所有输出端口:
- 异常处理：
  - 使用 `self.logger.error()` 记录:
  - 无法恢复的错误应 `raise`（框架会捕获）:
参考样例：
```python
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        # 在这里编写你的组件逻辑
        input_data = inputs.input1
        param1 = params.prop1
        self.logger.info("这是组件输出信息")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output1": result
        }
```

#### 四、调试块要求
在类定义之后，添加以下格式的调试入口：
```python
if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={...},          # 示例参数，覆盖所有 properties
        inputs={...},          # 示例输入，覆盖所有 inputs
        global_vars={},        # 可为空 dict
        node_id="test_node",   # 任意字符串
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
```
- `params` 和 `inputs` 必须提供合法示例值，能通过 Pydantic 校验:
- 示例值应尽量贴近真实使用场景（如 TEXT 用字符串，INT 用数字等）:
- 不要省略 `global_vars={}`（即使为空）:

#### 五、禁止内容
- 不要包含 `PortDefinition`、`PropertyType`、`ArgumentType`、`ConnectionType` 等类型定义:
- 不要在文件顶部写 `import`:
- 不要写与功能无关的注释、演示逻辑或业务特有代码（如视觉、历史、API 调用等）:

请根据以上规范回答用户问题：
'''

DEFAULT_SPLITTER_SIZES = [50, 450, 450]
HIDE_SPLITTER_SIZES = [50, 450, 0]