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


def patch_nodegraphqt():
    """解决nodegraphqt内部函数问题"""
    def add_label_item(self, label, node_id):
        item = QtGui.QStandardItem(label)
        item.setToolTip(node_id)
        metrics = QtGui.QFontMetrics(item.font())
        if hasattr(metrics, 'horizontalAdvance'):
            width = metrics.horizontalAdvance(item.text())
        else:
            width = metrics.width(item.text())
        width *= 1.5
        item.setSizeHint(QtCore.QSize(int(width), 20))
        self.model().appendRow(item)
        self.selectionModel().setCurrentIndex(
            self.model().indexFromItem(item),
            QtCore.QItemSelectionModel.ClearAndSelect)
    # 动态替换掉库里的原始函数
    NodeGraphQt.widgets.viewer_nav.NodeNavigationWidget.add_label_item = add_label_item


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


# ----------------------------
# 启动应
# ----------------------------
if __name__ == '__main__':
    import os
    import sys
    import warnings

    import NodeGraphQt
    import matplotlib
    import qtconsole.client
    from PyQt5 import QtGui, QtCore
    from PyQt5.QtCore import QTranslator, QCoreApplication  # 必须导入这个
    from PyQt5.QtGui import QPalette, QColor

    from app.utils.utils import get_icon

    warnings.filterwarnings("ignore")

    from app.utils import icons_rc
    from PyQt5.QtCore import Qt, QLocale
    from PyQt5.QtWidgets import QApplication

    from app.main_window import LowCodeWindow

    patch_nodegraphqt()
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    app = create_application()
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