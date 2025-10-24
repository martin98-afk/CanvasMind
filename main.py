# -*- coding: utf-8 -*-
import os
import sys
import warnings
warnings.filterwarnings("ignore")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.main_window import LowCodeWindow


def enable_dpi_scale():
    """启用 DPI 缩放支持"""
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)


# ----------------------------
# 启动应用
# ----------------------------
if __name__ == '__main__':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 启用 DPI 缩放
    enable_dpi_scale()
    # 创建应用
    app = QApplication(sys.argv)

    # 创建并显示主窗口
    try:
        window = LowCodeWindow()
        window.show()
        print("✅ 低代码平台启动成功！")
    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        print(f"❌ 启动失败: {e}")
        print(traceback.format_exc())
        sys.exit(1)

    # 运行应用
    sys.exit(app.exec_())