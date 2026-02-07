# -*- coding: utf-8 -*-
import shutil
import os
import sys
import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_submodules

# 1. 基础路径配置
base_dir = os.path.dirname(os.path.abspath(__file__))

# 自动定位 spyder 路径
try:
    import spyder

    spyder_dir = os.path.dirname(spyder.__file__)
except ImportError:
    print("错误: 当前环境未安装 spyder")
    sys.exit(1)

# 2. 【核心优化】动态搜寻插件依赖
# 自动找出 app.trigger_plugins 下的所有子模块，告诉 PyInstaller 必须包含它们
plugin_hidden_imports = collect_submodules('app.trigger_plugins')
logger_hidden_imports = ['loguru']  # 确保日志库被包含

# 3. 构造参数列表
params = [
    'main.py',
    '--onedir',
    '--windowed',
    '--name=CanvasMind',  # 直接指定名称，省去后期改名麻烦
    '--icon=' + os.path.join(base_dir, 'icons', 'logoico.ico'),

    # 数据文件包含
    f'--add-data={spyder_dir}{os.pathsep}spyder',
    f'--add-data=app{os.pathsep}app',
    f'--add-data=resource{os.pathsep}resource',
    f'--add-data=examples{os.pathsep}examples',

    # 隐藏导入：合并基础依赖与动态搜寻到的插件
    '--hidden-import=jupyter_client.provisioning.local',
    '--hidden-import=ipykernel',
    '--copy-metadata=jupyter_client',
]

# 批量添加插件隐藏导入
for imp in plugin_hidden_imports + logger_hidden_imports:
    params.append(f'--hidden-import={imp}')

# 运行时配置
params.extend([
    '--clean',
    '--noconfirm',
])


def post_build_cleanup(dist_path):
    """打包后的精简逻辑"""
    internal_path = os.path.join(dist_path, "_internal")
    if not os.path.exists(internal_path):
        # 兼容不同版本的打包结构
        internal_path = dist_path

    # 需要删除的冗余库列表
    to_remove = [
        'scipy', 'scipy.libs', 'sphinx',
        # 'matplotlib', 'PIL.ImageQt'  # 如果没用到这些巨无霸库也可以考虑删掉
    ]

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


if __name__ == "__main__":
    print(f"Starting build for CanvasMind...")
    print(f"Spyder directory: {spyder_dir}")

    # 执行打包
    PyInstaller.__main__.run(params)

    # 4. 后置处理
    dist_final = os.path.join("dist", "CanvasMind")
    if os.path.exists(dist_final):
        post_build_cleanup(dist_final)

    print("\n✅ 打包任务顺利完成！")