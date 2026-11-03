"""构建不包含本机数据的 Windows x64 便携包；从项目根目录用 -m 运行。"""
import hashlib
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

from PySide6.QtWidgets import QApplication

from water_assistant import __version__
from water_assistant.config import CHARACTERS
from water_assistant.ui import app_icon


ROOT = Path(__file__).resolve().parents[1]


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main():
    if sys.platform != "win32" or platform.machine().upper() != "AMD64":
        raise SystemExit("请使用 Windows x64 Python 构建。")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"build-v{__version__}-", dir=cache))
    assets = work / "assets/v2"
    for name in ("bubble.png", "NOTICE.md"):
        copy(ROOT / "assets/v2" / name, assets / name)
    for character in CHARACTERS:
        relative = Path("characters") / character
        folder = ROOT / "assets/v2" / relative
        manifest = json.loads((folder / "animation.json").read_text(encoding="utf-8"))
        names = {"portrait.png", "animation.json"}
        names.update(frame for state in manifest["states"].values() for frame in state["frames"])
        for name in sorted(names):
            copy(folder / name, assets / relative / name)

    application = QApplication.instance() or QApplication([])
    icon = work / "assistant.ico"
    if not app_icon().pixmap(64, 64).save(str(icon), "ICO"):
        raise RuntimeError("无法生成应用图标")
    hooks = work / "hooks"
    hooks.mkdir()
    # 应用只读取 PNG，QtNetwork 只用于本机 IPC，不分发 PDF/SVG/TLS 插件。
    for module in ("QtGui", "QtNetwork"):
        (hooks / f"hook-PySide6.{module}.py").write_text(
            "from PyInstaller.utils.hooks.qt import add_qt6_dependencies\n"
            "hiddenimports, binaries, datas = add_qt6_dependencies(__file__)\n"
            "binaries = [(src, dst) for src, dst in binaries if '/plugins/' not in dst.replace('\\\\', '/') "
            "or '/styles' in dst.replace('\\\\', '/') or src.endswith('qwindows.dll')]\n",
            encoding="utf-8")
    windows = Path(os.environ["SystemRoot"])
    build_env = {**os.environ, "PATH": os.pathsep.join(map(str, (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        windows / "System32", windows,
    )))}
    # 避免从其他工具的 PATH 收集同名 ICU/OpenSSL 或旧版 Windows 兼容 DLL。
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--noupx",
        "--name", "ShechuAssistant", "--icon", str(icon),
        "--additional-hooks-dir", str(hooks),
        "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
        "--specpath", str(work), "--add-data", f"{assets};assets/v2",
        str(ROOT / "run_v2.py"),
    ], cwd=ROOT, env=build_env, check=True)

    folder = work / "dist/ShechuAssistant"
    for name in ("LICENSE", "README.md", "启动社畜小助手.bat", "install_startup.bat", "remove_startup.bat",
                 "tools/startup.ps1", "docs/便携版说明.md", "docs/第三方依赖.md",
                 "assets/v2/NOTICE.md", "docs/evidence/V2提醒动作预览.webp"):
        copy(ROOT / name, folder / name)
    shutil.copytree(ROOT / "LICENSES", folder / "LICENSES")
    copy(Path(sys.base_prefix) / "LICENSE.txt", folder / "LICENSES/Python.txt")
    for name in ("PySide6_Essentials", "shiboken6", "PyInstaller"):
        package = distribution(name)
        for entry in package.files or []:
            if "/licenses/" in str(entry).replace("\\", "/"):
                copy(package.locate_file(entry), folder / "LICENSES" / name / Path(entry).name)
    (folder / "BUILD.json").write_text(json.dumps({
        "version": __version__, "platform": "windows-x64", "python": platform.python_version(),
        "PySide6": distribution("PySide6_Essentials").version,
        "PyInstaller": distribution("PyInstaller").version,
    }, indent=2), encoding="utf-8")

    output = ROOT / "output/releases"
    output.mkdir(parents=True, exist_ok=True)
    name = f"shechu-assistant-v{__version__}-windows-x64"
    archive = output / f"{name}.zip"
    # 每次保留独立构建目录，不覆盖已有下载包。
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, Path(name) / path.relative_to(folder))
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    print(json.dumps({"archive": str(archive), "folder": str(folder),
                      "bytes": archive.stat().st_size, "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
