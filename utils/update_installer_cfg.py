import configparser
import subprocess
import re
import sys
import venv
import shutil
from pathlib import Path
import tempfile
from packaging import version


def create_venv_and_install(cfg_packages):
    """创建虚拟环境并安装包"""
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp())
    venv_path = temp_dir / "venv"

    print("Creating virtual environment...")
    venv.create(venv_path, with_pip=True)

    # 获取python和pip路径
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"

    print("Installing current project...")
    project_dir = Path(__file__).parent.parent
    try:
        subprocess.run(
            [str(pip_path), "install", "-e", str(project_dir)], capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error installing project: {e.stderr}")
        shutil.rmtree(temp_dir)
        raise

    # 获取安装后的版本信息
    result = subprocess.run([str(pip_path), "list", "--format=freeze"], capture_output=True, text=True)

    # 清理临时目录
    shutil.rmtree(temp_dir)

    # 解析安装的包信息
    installed = {}
    for line in result.stdout.split("\n"):
        if "==" in line:
            name, ver = line.strip().split("==")
            installed[name.lower()] = ver

    return installed


def read_installer_cfg(file_path):
    """读取installer.cfg文件中的包信息"""
    config = configparser.ConfigParser()
    config.read(file_path)

    wheels = config.get("Include", "pypi_wheels").strip().split("\n")
    wheels = [wheel.strip() for wheel in wheels]

    packages = {}
    for wheel in wheels:
        if "==" in wheel:
            name, ver = wheel.split("==")
            packages[name] = ver
    return packages, config


def check_updates(cfg_packages, installed_packages):
    """比较配置文件和实际安装的包的差异"""
    updates = {}  # 版本不同的包
    no_updates = {}  # 版本相同的包
    to_add = {}  # 新增的包（在安装中有但配置里没有）
    to_remove = {}  # 要删除的包（在配置里有但安装中没有）

    # 检查配置文件中的包
    for name, cfg_ver in cfg_packages.items():
        name_lower = name.lower()
        if name_lower in installed_packages:
            inst_ver = installed_packages[name_lower]
            try:
                if version.parse(inst_ver) != version.parse(cfg_ver):
                    updates[name] = (cfg_ver, inst_ver)
                else:
                    no_updates[name] = cfg_ver
            except Exception:
                no_updates[name] = cfg_ver
        else:
            to_remove[name] = cfg_ver

    # 检查新增的包
    for name, ver in installed_packages.items():
        if not any(name == n.lower() for n in cfg_packages):
            to_add[name] = ver

    return updates, no_updates, to_add, to_remove


def update_config_file(file_path, final_packages):
    """更新配置文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 构建新的pypi_wheels部分
    packages = []
    for name in sorted(final_packages.keys()):
        packages.append(f"{name}=={final_packages[name]}")

    # 找到pypi_wheels部分并替换
    pattern = r"pypi_wheels\s*=\s*.*?(?=\n\n|$)"
    replacement = "pypi_wheels = " + "\n    ".join(packages)
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # 写入文件
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def confirm_action(message):
    """获取用户确认"""
    while True:
        response = input(f"{message} (y/n): ").lower()
        if response in ["y", "n"]:
            return response == "y"


def main():
    file_path = "installer.cfg"
    if not Path(file_path).exists():
        print(f"Error: {file_path} not found!")
        return

    print("Reading current package versions...")
    cfg_packages, _ = read_installer_cfg(file_path)

    print("Creating test environment and checking package compatibility...")
    try:
        installed_packages = create_venv_and_install(cfg_packages)
    except Exception as e:
        print(f"Error: Failed to verify current package versions: {e}")
        return

    print("\nAnalyzing package status...")
    updates, no_updates, to_add, to_remove = check_updates(cfg_packages, installed_packages)

    # 显示状态报告
    if updates:
        print("\nPackages with version differences:")
        for name, (cfg_ver, inst_ver) in updates.items():
            print(f"  {name}: {cfg_ver} -> {inst_ver}")

    if to_add:
        print("\nNew packages to add:")
        for name, ver in to_add.items():
            print(f"  {name}: {ver}")

    if to_remove:
        print("\nPackages to remove:")
        for name, ver in to_remove.items():
            print(f"  {name}: {ver}")

    if no_updates:
        print(f"\nPackages up to date: {len(no_updates)}")

    # 分别处理添加和删除的包
    final_packages = {**cfg_packages}  # 从当前配置开始

    if to_add:
        for name, ver in to_add.items():
            if confirm_action(f"Add {name}=={ver} to configuration?"):
                final_packages[name] = ver

    if to_remove:
        for name, ver in to_remove.items():
            if confirm_action(f"Remove {name}=={ver} from configuration?"):
                final_packages.pop(name)

    # 一次性确认所有更新
    if updates and confirm_action("\nUpdate all packages with version differences?"):
        for name, (_, new_ver) in updates.items():
            final_packages[name] = new_ver

    # 如果有任何改动，更新配置文件
    if final_packages != cfg_packages:
        print("\nUpdating configuration file...")
        update_config_file(file_path, final_packages)
        print("Configuration file has been updated successfully!")
    else:
        print("\nNo changes made to configuration.")


if __name__ == "__main__":
    main()
