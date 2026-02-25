import os
import sys
import site
import subprocess
import glob


def find_lrelease():
    # 获取所有 Python 包安装目录
    package_paths = site.getsitepackages()

    # 在这些目录里寻找 lrelease.exe
    # 通常位于 qt5_applications/Qt/bin 目录下
    for path in package_paths:
        # 常见路径模式 1
        patterns = [
            os.path.join(path, "qt5_applications", "Qt", "bin", "lrelease.exe"),
            os.path.join(path, "PyQt5", "Qt", "bin", "lrelease.exe"),
            os.path.join(path, "pyqt5_tools", "Qt", "bin", "lrelease.exe")
        ]

        for p in patterns:
            if os.path.exists(p):
                return p
    return None


def compile():
    lrelease_exe = find_lrelease()

    if not lrelease_exe:
        print("❌ 错误：在你的 Python 环境中找不到 lrelease.exe")
        print("请尝试运行: pip install qt5-applications")
        return

    print(f"✅ 找到工具: {lrelease_exe}")

    ts_file = "resource/i18n/en_US.ts"
    qm_file = "resource/i18n/en_US.qm"

    if not os.path.exists(ts_file):
        print(f"❌ 错误：找不到源文件 {ts_file}")
        return

    # 执行命令
    cmd = [lrelease_exe, ts_file, "-qm", qm_file]
    print(f"正在执行: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"🎉 成功！已生成: {qm_file}")
    else:
        print("❌ 编译失败:")
        print(result.stderr)


if __name__ == "__main__":
    compile()