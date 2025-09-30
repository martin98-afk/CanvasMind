import multiprocessing
import sys
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.main_window import LowCodeWindow

def enable_dpi_scale():
    """启用 DPI 缩放支持"""
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)


def setup_environment():
    """设置运行环境"""
    # 确保当前目录在 sys.path 中
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    # 设置工作目录
    os.chdir(current_dir)

    # 确保必要的目录存在
    required_dirs = ["components", "environments", "workflows"]
    for dir_name in required_dirs:
        dir_path = os.path.join(current_dir, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)


# ----------------------------
# 启动应用
# ----------------------------
if __name__ == '__main__':
    if getattr(sys, 'frozen', False):
        multiprocessing.freeze_support()

    # 设置环境
    setup_environment()

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

        print(f"❌ 启动失败: {e}")
        print(traceback.format_exc())
        sys.exit(1)

    # 运行应用
    sys.exit(app.exec_())