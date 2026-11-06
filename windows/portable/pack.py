import argparse
import json
from pathlib import Path
import py_compile
import shutil
import tempfile
import zipfile

# Packages that scan their own filesystem (notably apprise) must stay outside the archive.
ARCHIVED_PACKAGES = (
    "embykeeper",
    "embykeeperapi",
    "pyrogram",
    "telethon",
    "faker",
    "emoji",
    "pygments",
    "rich",
    "pydantic",
    "fastapi",
    "starlette",
    "tzdata",
)


def inventory(directory):
    files = [path for path in directory.rglob("*") if path.is_file()]
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}


def compact_runtime(runtime):
    runtime = Path(runtime)
    archive = runtime / "packages.zip"
    if archive.exists():
        raise FileExistsError("Use a freshly installed staging runtime, not an already compacted runtime")
    site_packages = runtime / "Lib" / "site-packages"
    path_file = next(runtime.glob("python*._pth"))
    before = inventory(runtime)
    for path in list(site_packages.rglob("tests")):
        if path.is_dir():
            shutil.rmtree(path)
    for path in (site_packages / "numpy" / "core" / "include", site_packages / "numpy" / "_core" / "include"):
        if path.is_dir():
            shutil.rmtree(path)
    static = site_packages / "embykeeperapi" / "static"
    if static.is_dir():
        shutil.move(str(static), runtime / "static")

    packed = []
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(
        archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6
    ) as bundle:
        for name in ARCHIVED_PACKAGES:
            package = site_packages / name
            if not package.is_dir():
                continue
            for source in sorted(package.rglob("*")):
                if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                    continue
                relative = source.relative_to(site_packages)
                if source.suffix.lower() in (".pyd", ".dll", ".so", ".dylib"):
                    raise ValueError(f"Native library cannot be archived: {relative}")
                bundle.write(source, relative)
                if source.suffix == ".py":
                    bytecode = Path(directory) / relative.with_suffix(".pyc")
                    bytecode.parent.mkdir(parents=True, exist_ok=True)
                    py_compile.compile(
                        str(source),
                        cfile=str(bytecode),
                        dfile=relative.as_posix(),
                        doraise=True,
                        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                    )
                    bundle.write(bytecode, relative.with_suffix(".pyc"))
            packed.append(name)

    paths = path_file.read_text(encoding="ascii").splitlines()
    paths.insert(0, archive.name)
    path_file.write_text("\n".join(paths) + "\n", encoding="ascii")
    for name in packed:
        shutil.rmtree(site_packages / name)
    for path in site_packages.glob("pip*"):
        if path.is_dir() and (path.name == "pip" or path.name.endswith(".dist-info")):
            shutil.rmtree(path)
    for path in site_packages.rglob("__pycache__"):
        shutil.rmtree(path)
    scripts = runtime / "Scripts"
    if scripts.is_dir():
        shutil.rmtree(scripts)

    return {"before": before, "after": inventory(runtime), "archived_packages": packed}


def main():
    parser = argparse.ArgumentParser(description="Build the compact Windows portable archive")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = compact_runtime(args.runtime)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(args.runtime.rglob("*")):
            if path.is_file():
                bundle.write(path, Path("runtime") / path.relative_to(args.runtime))
        for name in ("Start-Embykeeper.bat", "install.ps1"):
            bundle.write(args.installer / name, name)
        bundle.writestr("version.txt", args.version + "\n")
    report["archive_bytes"] = args.output.stat().st_size
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
