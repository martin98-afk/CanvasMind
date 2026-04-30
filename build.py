# -*- coding: utf-8 -*-
import os
import shutil
import platform
from pathlib import Path

import PyInstaller.__main__

# 1. 基础路径配置
base_dir = os.path.dirname(os.path.abspath(__file__))
extra_modules = [
]
# 需要删除的冗余库列表
to_remove = [
    "scipy",
    "cv2",
    "pyarrow",
    "jieba",
    "scipy.libs",
    "sphinx",
    "matplotlib",
    "torch",
    "tensorflow",
    "torchaudio",
    "sqlalchemy",
]
# 2. 图标选择 (跨平台)
icon_arg = None
if platform.system() == "Windows":
    icon_path = Path(base_dir) / "icons" / "drifox.ico"
    if icon_path.exists():
        icon_arg = f"--icon={icon_path}"
elif platform.system() == "Darwin":
    icon_path = Path(base_dir) / "icons" / "logoico.ico"
    if icon_path.exists():
        icon_arg = f"--icon={icon_path}"

# 3. 构造参数列表
params = [
    "main.py",
    "--onedir",
    "--windowed",
    "--name=Drifox",  # 直接指定名称，省去后期改名麻烦
    # 数据文件包含
    f"--add-data=app/llm_chatter/agents{os.pathsep}app/llm_chatter",
]

if icon_arg:
    params.append(icon_arg)

# macOS: 指定单一架构，避免 universal2 体积膨胀
if platform.system() == "Darwin":
    arch = os.environ.get("PYINSTALLER_ARCH", "").strip() or platform.machine()
    # PyInstaller 期望的值一般是 "arm64" 或 "x86_64"
    if arch not in ("arm64", "x86_64"):
        arch = "arm64"
    params.append(f"--target-arch={arch}")


# 运行时配置
params.extend(
    [
        "--clean",
        "--noconfirm",
    ]
)


def post_build_cleanup(dist_path):
    """打包后的精简逻辑"""
    internal_path = os.path.join(dist_path, "_internal")
    if not os.path.exists(internal_path):
        # 兼容不同版本的打包结构
        internal_path = dist_path

    print("正在精简打包体积...")
    for folder in to_remove:
        target = os.path.join(internal_path, folder)
        if os.path.exists(target):
            try:
                if os.path.isfile(target):
                    os.remove(target)
                else:
                    shutil.rmtree(target)
                print(f"  - 已移除: {folder}")
            except Exception as e:
                print(f"  - 移除 {folder} 失败: {e}")

    for root, dirs, files in os.walk(internal_path):
        for d in dirs:
            if d in (".mypy_cache", "__pycache__"):
                try:
                    shutil.rmtree(os.path.join(root, d))
                    print(f"  - 已移除: {os.path.join(root, d)}")
                except Exception as e:
                    print(f"  - 移除 {d} 失败: {e}")


if __name__ == "__main__":
    print(f"Starting build for CanvasMind...")

    # 执行打包
    PyInstaller.__main__.run(params)

    # 4. 后置处理
    dist_final = os.path.join("dist", "Drifox")
    if os.path.exists(dist_final):
        post_build_cleanup(dist_final)

    print("\n✅ 打包任务顺利完成！")

