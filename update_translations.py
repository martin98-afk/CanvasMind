import os
import subprocess
import sys
import shutil

# ================= 配置区域 =================
TS_FILE = f"{os.path.dirname(os.path.abspath(__file__))}/resource/i18n/zh_CN.ts"  # 目标翻译文件
EXCLUDE_DIRS = {
    "venv", ".venv", ".venv2", ".git", "__pycache__", ".idea", ".vscode",
    "build", "dist", "egg-info", "site-packages", "components", "component_extensions"
}
# 获取脚本所在目录作为项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/app"


# ===========================================

def find_pylupdate():
    """ 自动寻找 pylupdate5 的可执行路径 """
    # 优先检查项目内的虚拟环境
    if os.name == "nt":
        potential_venv_path = os.path.join(ROOT_DIR, ".venv2", "Scripts", "pylupdate5.exe")
    else:
        potential_venv_path = os.path.join(ROOT_DIR, ".venv2", "bin", "pylupdate5")
    if os.path.exists(potential_venv_path):
        return potential_venv_path

    # 检查环境变量
    path = shutil.which("pylupdate5")
    if path: return path

    # 检查 Python 安装目录
    python_dir = os.path.dirname(sys.executable)
    if os.name == "nt":
        potential_path = os.path.join(python_dir, "Scripts", "pylupdate5.exe")
    else:
        potential_path = os.path.join(python_dir, "pylupdate5")
    if os.path.exists(potential_path): return potential_path

    return None


def main():
    print(f"🔍 正在扫描项目目录: {ROOT_DIR}")

    pylupdate_cmd = find_pylupdate()
    if not pylupdate_cmd:
        print("❌ 找不到 pylupdate5，请检查环境。")
        return
    print(f"✅ 使用工具: {pylupdate_cmd}")

    # 1. 收集 .py 文件（使用相对路径！）
    rel_py_files = []

    for root, dirs, files in os.walk(ROOT_DIR):
        # 排除无关目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".py") and file != os.path.basename(__file__):
                # 获取绝对路径
                abs_path = os.path.join(root, file)
                # 【核心修复】转换为相对路径 (例如 "app/main.py")
                # 这样可以大幅缩短命令行长度，避免 WinError 206
                rel_path = os.path.relpath(abs_path, ROOT_DIR)
                rel_py_files.append(rel_path)

    if not rel_py_files:
        print("❌ 未找到任何 .py 文件！")
        return

    print(f"📦 扫描到 {len(rel_py_files)} 个源文件，正在生成翻译...")

    # 2. 确保输出目录存在
    output_dir = os.path.dirname(TS_FILE)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 3. 构建命令
    # 注意：这里 cmd 中的文件名都是相对路径
    cmd = [pylupdate_cmd] + rel_py_files + ["-ts", TS_FILE]

    # 4. 执行命令
    try:
        # 【关键】cwd=ROOT_DIR 确保命令在项目根目录下运行
        # 这样 pylupdate5 才能找到那些相对路径的文件
        subprocess.run(cmd, check=True, cwd=ROOT_DIR)

        print(f"\n🎉 成功！翻译文件已生成于: {TS_FILE}")
        print("下一步: 使用 Qt Linguist 打开该 .ts 文件进行翻译。")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ 执行出错: {e}")
    except OSError as e:
        # 如果还是报文件名太长，说明文件实在太多了(几千个)
        if e.winerror == 206:
            print("\n❌ 错误: 文件数量过多，命令行长度超出系统限制。")
            print("建议: 请手动删除一些不必要的目录或分模块进行翻译。")
        else:
            print(f"\n❌ 操作系统错误: {e}")


if __name__ == "__main__":
    main()
