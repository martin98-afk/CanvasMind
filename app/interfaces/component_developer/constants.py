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
SideDockRegistry.register("组件开发", OpenAIChatToolWindow.name, OpenAIChatToolWindow, DockPosition.BOTTOM)


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

DEFAULT_SPLITTER_SIZES = [50, 450, 450]
HIDE_SPLITTER_SIZES = [50, 450, 0]