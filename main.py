import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.workflow import LowCodeWindow


def enable_dpi_scale():
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)


# ----------------------------
# 启动应用
# ----------------------------
if __name__ == '__main__':
    enable_dpi_scale()
    app = QApplication(sys.argv)
    window = LowCodeWindow()
    window.show()
    sys.exit(app.exec_())
