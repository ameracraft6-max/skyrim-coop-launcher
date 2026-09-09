import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
ASSETS_DIR = BASE_DIR / "assets"
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
ICON_PATH = ASSETS_DIR / "app_icon.ico"

def build():
    print("=== Начало сборки SkyrimCoopLauncher.exe ===")

    # Import customtkinter to get its directory
    import customtkinter
    ctk_dir = Path(customtkinter.__file__).parent
    print(f"Путь CustomTkinter: {ctk_dir}")

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "SkyrimCoopLauncher",
        f"--icon={ICON_PATH}",
        f"--add-data={ctk_dir};customtkinter",
        f"--add-data={ASSETS_DIR};assets",
        f"--paths={SRC_DIR}",
        "--clean",
        str(SRC_DIR / "main.py")
    ]

    print("Команда сборки:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode == 0:
        exe_path = DIST_DIR / "SkyrimCoopLauncher.exe"
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n[УСПЕХ] Сборка завершена успешно!")
        print(f"Готовый файл: {exe_path} ({size_mb:.1f} МБ)")
    else:
        print(f"\n[ОШИБКА] Сборка завершилась с ошибкой (код {res.returncode})")
        sys.exit(res.returncode)

if __name__ == "__main__":
    build()
