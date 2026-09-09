import os
import sys
import zipfile
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import load_config
from downloader import Downloader
from installer import get_7z_exe

def create_release_bundle():
    print("=== Создание SkyrimTogether_Release_Bundle.zip для GitHub Releases ===")
    cfg = load_config()
    api_key = cfg.get("nexus_api_key", "").strip()
    if not api_key:
        print("[ОШИБКА] API ключ Nexus не найден в конфиге.")
        return

    temp_dir = BASE_DIR / "bundle_staging"
    temp_dir.mkdir(exist_ok=True)
    out_bundle = BASE_DIR / "SkyrimTogether_Release_Bundle.zip"

    # 1. Download Address Library
    print("\n1. Скачивание Address Library...")
    addr_files = Downloader.get_nexus_mod_files(api_key, 32444)
    main_addr = [f for f in addr_files if f.get("category_name") == "MAIN"]
    addr_file = main_addr[-1] if main_addr else addr_files[-1]
    addr_url = Downloader.get_nexus_download_link(api_key, 32444, addr_file["file_id"])
    
    dl = Downloader()
    addr_zip = temp_dir / "address_library.zip"
    dl.download_file(addr_url, addr_zip, progress_callback=lambda f, s, dl, t: print(f"Address Library: {t}"))

    # 2. Download Skyrim Together Reborn
    print("\n2. Скачивание Skyrim Together Reborn...")
    str_files = Downloader.get_nexus_mod_files(api_key, 69993)
    main_str = [f for f in str_files if f.get("category_name") == "MAIN"]
    str_file = main_str[-1] if main_str else str_files[-1]
    str_url = Downloader.get_nexus_download_link(api_key, 69993, str_file["file_id"])

    str_zip = temp_dir / "skyrim_together.zip"
    dl.download_file(str_url, str_zip, progress_callback=lambda f, s, dl, t: print(f"STR: {t}"))

    # 3. Unpack both into bundle staging directory using 7z
    extract_dir = temp_dir / "merged"
    extract_dir.mkdir(exist_ok=True)

    seven_z = get_7z_exe()
    import subprocess
    print("\n3. Распаковка и объединение файлов...")
    subprocess.run([str(seven_z), "x", str(addr_zip), f"-o{extract_dir}", "-y"], check=True)
    subprocess.run([str(seven_z), "x", str(str_zip), f"-o{extract_dir}", "-y"], check=True)

    # 4. Pack into final standard ZIP (Deflate level 6 so standard python / any unarchiver reads it without 7z)
    print("\n4. Упаковка в универсальный ZIP-архив...")
    with zipfile.ZipFile(out_bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, files in os.walk(extract_dir):
            for file in files:
                full_p = Path(root) / file
                rel_p = full_p.relative_to(extract_dir)
                z.write(full_p, arcname=str(rel_p))

    shutil.rmtree(temp_dir, ignore_errors=True)
    size_mb = out_bundle.stat().st_size / (1024 * 1024)
    print(f"\n[УСПЕХ] Готовый архив для GitHub Releases создан: {out_bundle} ({size_mb:.1f} МБ)")
    print("Вы можете загрузить этот архив и SkyrimCoopLauncher.exe в Release вашего GitHub!")

if __name__ == "__main__":
    create_release_bundle()
