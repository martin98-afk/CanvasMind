import shutil

import PyInstaller.__main__
import os
import sys
import spyder  # 先导入，用于自动定位路径

# 1. 自动获取 spyder 库的安装路径
# os.path.dirname(spyder.__file__) 通常指向 .../site-packages/spyder
spyder_dir = os.path.dirname(spyder.__file__)

# 2. 定义项目根目录（确保相对路径正确）
base_dir = os.path.dirname(os.path.abspath(__file__))

# 3. 构造参数列表
params = [
    'main.py',
    '--onedir',
    '--windowed',
    '--icon=' + os.path.join('icons', 'logoico.ico'),

    # 动态添加 Spyder 数据文件夹
    # 格式： "源路径;目标名" (Windows下用分号)
    f'--add-data={spyder_dir}{os.pathsep}spyder',

    # 其他固定数据文件夹
    f'--add-data=app{os.pathsep}app',
    f'--add-data=resource{os.pathsep}resource',
    f'--add-data=examples{os.pathsep}examples',

    # 元数据和隐藏导入
    '--copy-metadata=jupyter_client',
    '--hidden-import=jupyter_client.provisioning.local',
    '--hidden-import=ipykernel',
    # 建议加上 --clean 清理之前的缓存，避免路径残留
    '--clean',
    '--noconfirm',
]

# 4. 运行前检查一下关键路径是否存在（调试用）
print(f"Checking Spyder path: {spyder_dir}")
if not os.path.exists(spyder_dir):
    print(f"错误: 找不到 Spyder 路径: {spyder_dir}")
    sys.exit(1)

# 5. 执行打包
if __name__ == "__main__":
    PyInstaller.__main__.run(params)
    print("打包完成！")
