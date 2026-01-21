# -*- coding: utf-8 -*-
import os
import sys
import warnings
import matplotlib
import qtconsole.client
from PyQt5.QtCore import QTranslator, QCoreApplication  # 必须导入这个
from PyQt5.QtGui import QPalette, QColor

from app.utils.utils import get_icon

warnings.filterwarnings("ignore")

from app.utils import icons_rc
from PyQt5.QtCore import Qt, QLocale
from PyQt5.QtWidgets import QApplication

from app.main_window import LowCodeWindow


def enable_dpi_scale():
    """启用 DPI 缩放支持"""
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)


def enable_opengl():
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)


def create_application():
    # 启用 DPI 缩放
    enable_dpi_scale()
    enable_opengl()
    # 创建应用
    sys.argv.append("--no-sandbox")

    app = QApplication(sys.argv)
    # 启用fusion样式
    app.setStyle("Fusion")
    tooltip_style = """
        QToolTip {
            color: white;
            background-color: black;
            border: none;
            padding: 2px;
            font-size: 12px;
        }
        """
    # 如果你已有全局样式，合并进去
    app.setStyleSheet(app.styleSheet() + tooltip_style)

    # Required for correct icon on GNOME/Wayland:
    if hasattr(app, 'setDesktopFileName'):
        app.setDesktopFileName('CanvasMind')

    return app


def load_localization(app,  language="en"):
    translator = QTranslator()
    language_map = {
        'en': 'en_US',
        'zh': 'zh_CN'
     }
    qm_path = os.path.join('resource', 'i18n', f'{language_map[language]}.qm')


    # 3. 加载并安装
    if os.path.exists(qm_path):
        if translator.load(qm_path):
            app.installTranslator(translator)
            print(f"✅ 成功加载翻译: {qm_path}")
        else:
            print(f"❌ 文件存在但加载失败 (格式错误?): {qm_path}")
    else:
        print(f"❌ 找不到翻译文件: {qm_path}")

    test_text = QCoreApplication.translate("CanvasPage", "未命名工作流")
    print(f"测试翻译结果: {test_text}")

# ----------------------------
# 启动应
# ----------------------------
if __name__ == '__main__':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    app = create_application()
    load_localization(app)
    # 创建并显示主窗口
    try:
        window = LowCodeWindow()
        window.show()
        print("✅ 启动成功！")
    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        print(f"❌ 启动失败: {e}")
        print(traceback.format_exc())
        sys.exit(1)

    # 运行应用
    sys.exit(app.exec_())