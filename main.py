# -*- coding: utf-8 -*-
"""
LLM Chatter 主入口
以独立弹窗模式启动，无需 FluentWindow 框架
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ["PYTHONIOENCODING"] = "utf-8"

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def main():
    """启动 LLM Chatter"""
    import platform
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    from loguru import logger
    from app.utils import icons_rc
    
    # ========== 必须在创建 QApplication 之前设置 Qt 属性 ==========
    # 这些设置必须在任何 Qt 模块导入之前或 QApplication 创建之前完成
    
    # DPI 缩放设置
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    # OpenGL 共享上下文（解决 QtWebEngineWidgets 导入问题）
    if platform.system() != "Darwin":
        QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    
    # ========== 导入可能触发 WebEngine 的模块（在 QApplication 创建之前）==========
    # 提前导入，确保在 app 创建之前触发
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    
    # 设置日志
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        os.path.join(log_dir, "llm_chatter.log"),
        rotation="10 MB",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("LLM Chatter")
    app.setApplicationDisplayName("LLM Chatter")
    
    app.setStyleSheet("""
        QToolTip {
            color: white;
            background-color: black;
            border: none;
            padding: 2px;
            font-size: 12px;
        }
    """)
    
    # 设置主题
    from qfluentwidgets import Theme, setTheme
    setTheme(Theme.DARK)
    
    # 导入独立应用模块
    from app.widgets.side_dock_area.plugins.llm_chatter.standalone_app import create_window
    
    # 创建并显示窗口
    logger.info("LLM Chatter 启动中...")
    
    window = create_window()
    llm_window = window()
    llm_window.show()
    
    logger.info("LLM Chatter 启动成功")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()