import os
import re
import subprocess
import shutil
from pathlib import Path


def update_version(app_path, version):
    """Update version in app.py"""
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(r'EK_VERSION = "[^"]+"', f'EK_VERSION = "{version}"', content)

    with open(app_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def print_tree(path, prefix=""):
    """Print directory structure in tree format"""
    if not os.path.isdir(path):
        return

    items = os.listdir(path)
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        print(f"{prefix}{'└──' if is_last else '├──'} {item}")
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            print_tree(full_path, prefix + ("    " if is_last else "│   "))


def obfuscate_app(app_path):
    """Obfuscate app.py using python-minifier"""
    try:
        import python_minifier

        with open(app_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Minify and obfuscate the code
        minified = python_minifier.minify(
            content,
            rename_globals=True,
            rename_locals=True,
            remove_annotations=True,
            remove_pass=True,
            remove_literal_statements=True,
            combine_imports=True,
            hoist_literals=True,
        )

        # Write back the obfuscated code
        with open(app_path, "w", encoding="utf-8") as f:
            f.write(minified)

        return True
    except Exception as e:
        print(f"Obfuscation failed: {e}")
        return False


def main():
    # Get version from environment variable (set by GitHub Actions)
    version = os.environ.get("GITHUB_REF_NAME", "").lstrip("v")
    if not version:
        raise ValueError("Version not found in GITHUB_REF_NAME")

    # Paths
    hf_dir = Path("hf")
    app_path = hf_dir / "app.py"

    # Update version in app.py
    update_version(app_path, version)

    # Obfuscate app.py
    if not obfuscate_app(app_path):
        raise RuntimeError("Failed to obfuscate app.py")

    print(f"Successfully processed app.py with version {version}")


if __name__ == "__main__":
    main()
