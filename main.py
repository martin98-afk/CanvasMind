# -*- coding: utf-8 -*-
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


def load_localization(app, language="en"):
    # 将 translator 绑定到 app 对象上，防止被垃圾回收
    app.translator = QTranslator()

    language_map = {
        'en': 'en_US',
        'zh': 'zh_CN'
    }

    # 确保文件名匹配（比如 zh_CN.qm）
    file_name = language_map.get(language, 'en_US')
    qm_path = os.path.join('resource', 'i18n', f'{file_name}.qm')

    if os.path.exists(qm_path):
        # 注意：使用 app.translator
        if app.translator.load(qm_path):
            app.installTranslator(app.translator)
            print(f"✅ 成功加载翻译: {qm_path}")
            return True
        else:
            print(f"❌ 文件存在但加载失败 (格式错误?): {qm_path}")
    else:
        print(f"❌ 找不到翻译文件: {qm_path}")
    return False


# ----------------------------
# 启动应
# ----------------------------
if __name__ == '__main__':
    import os
    import sys
    import NodeGraphQt
    import qtconsole.client
    import warnings
    warnings.filterwarnings("ignore")

    from PyQt5.QtCore import Qt, QLocale
    from PyQt5.QtWidgets import QApplication
    from PyQt5 import QtGui, QtCore
    from PyQt5.QtCore import QTranslator, QCoreApplication  # 必须导入这个
    from PyQt5.QtGui import QPalette, QColor

    from app.utils import icons_rc
    from app.widgets.custom_nodegraphqt.nodegraphqt_patcher import patch_nodegraphqt
    patch_nodegraphqt()

    from app.main_window import LowCodeWindow
    sys.path.append(".")
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    app = create_application()
    app.setQuitOnLastWindowClosed(False)
    # load_localization(app)
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