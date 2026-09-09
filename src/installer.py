import os
import sys
import json
import time
import shutil
import zipfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

MANIFEST_FILENAME = "str_manifest.json"

class InstallError(Exception):
    pass

def convert_format5_to_format2(v5_path: Path, v2_path: Path):
    import io, struct
    with open(v5_path, "rb") as f:
        data = f.read()

    pos = 0
    if len(data) < 28:
        return
    fmt = struct.unpack_from("<i", data, pos)[0]; pos += 4
    if fmt != 5:
        return

    major, minor, revision, build = struct.unpack_from("<4i", data, pos); pos += 16
    mod_name_bytes = data[pos:pos+64]; pos += 64
    mod_name = mod_name_bytes.split(b"\x00")[0].decode(errors="ignore")
    ptr_size = struct.unpack_from("<Q", data, pos)[0]; pos += 8
    addr_count = struct.unpack_from("<I", data, pos)[0]; pos += 4

    offsets = struct.unpack_from(f"<{addr_count}I", data, pos)
    entries = [(id, off) for id, off in enumerate(offsets) if off != 0]

    out = io.BytesIO()
    out.write(struct.pack("<i", 2))
    out.write(struct.pack("<4i", major, minor, revision, build))
    encoded_name = mod_name.encode("ascii", errors="ignore")
    out.write(struct.pack("<i", len(encoded_name)))
    out.write(encoded_name)
    out.write(struct.pack("<i", int(ptr_size)))
    out.write(struct.pack("<i", len(entries)))

    pvid = 0
    poffset = 0

    for id, off in entries:
        low = 0
        extra_id = b""
        if id == pvid + 1:
            low = 1
        elif 0 < id - pvid <= 255:
            low = 2
            extra_id = struct.pack("<B", id - pvid)
        elif 0 < pvid - id <= 255:
            low = 3
            extra_id = struct.pack("<B", pvid - id)
        elif 0 < id - pvid <= 65535:
            low = 4
            extra_id = struct.pack("<H", id - pvid)
        elif 0 < pvid - id <= 65535:
            low = 5
            extra_id = struct.pack("<H", pvid - id)
        elif id <= 65535:
            low = 6
            extra_id = struct.pack("<H", id)
        elif id <= 0xFFFFFFFF:
            low = 7
            extra_id = struct.pack("<I", id)
        else:
            low = 0
            extra_id = struct.pack("<Q", id)

        tpoffset = poffset
        h7 = 0
        extra_off = b""
        if off == tpoffset + 1:
            h7 = 1
        elif 0 < off - tpoffset <= 255:
            h7 = 2
            extra_off = struct.pack("<B", off - tpoffset)
        elif 0 < tpoffset - off <= 255:
            h7 = 3
            extra_off = struct.pack("<B", tpoffset - off)
        elif 0 < off - tpoffset <= 65535:
            h7 = 4
            extra_off = struct.pack("<H", off - tpoffset)
        elif 0 < tpoffset - off <= 65535:
            h7 = 5
            extra_off = struct.pack("<H", tpoffset - off)
        elif off <= 65535:
            h7 = 6
            extra_off = struct.pack("<H", off)
        elif off <= 0xFFFFFFFF:
            h7 = 7
            extra_off = struct.pack("<I", off)
        else:
            h7 = 0
            extra_off = struct.pack("<Q", off)

        type_byte = ((h7 & 7) << 4) | (low & 0xF)
        out.write(bytes([type_byte]))
        if extra_id:
            out.write(extra_id)
        if extra_off:
            out.write(extra_off)

        pvid = id
        poffset = off

    with open(v2_path, "wb") as f:
        f.write(out.getvalue())

def get_7z_exe() -> Optional[Path]:
    """Finds embedded or system 7z.exe executable."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)).resolve()
    candidates = [
        base / "assets" / "7z" / "7z.exe",
        Path(__file__).resolve().parent.parent / "assets" / "7z" / "7z.exe",
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for c in candidates:
        if c.exists():
            return c
    w = shutil.which("7z")
    return Path(w) if w else None

class Installer:
    @staticmethod
    def get_manifest_path(game_dir: Path) -> Path:
        return game_dir / MANIFEST_FILENAME

    @staticmethod
    def is_installed(game_dir: Path) -> bool:
        manifest_path = Installer.get_manifest_path(game_dir)
        return manifest_path.exists()

    @staticmethod
    def list_archive_files_7z(seven_z: Path, archive_path: Path) -> List[str]:
        """Lists file paths inside archive using 7z."""
        cmd = [str(seven_z), "l", "-slt", str(archive_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
        files = []
        current_path = None
        is_dir = False
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("Path = "):
                current_path = line[7:].strip()
            elif line.startswith("Attributes = "):
                attrs = line[13:].strip()
                is_dir = "D" in attrs
            elif line == "":
                if current_path and not is_dir:
                    # Ignore the archive path itself
                    if current_path != str(archive_path) and not current_path.endswith(archive_path.name):
                        files.append(current_path)
                current_path = None
                is_dir = False
        return files

    @staticmethod
    def install_archive(
        archive_path: Path,
        game_dir: Path,
        target_subfolder: str = "Data",
        version_label: str = "custom",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Extracts an archive (ZIP, 7z, Deflate64, LZMA) into game_dir / target_subfolder.
        Uses embedded 7-Zip for 100% compatibility with all compression methods.
        """
        if not archive_path.exists():
            raise InstallError(f"Файл архива не найден: {archive_path}")
        if not game_dir.exists():
            raise InstallError(f"Папка игры не существует: {game_dir}")

        dest_dir = game_dir / target_subfolder if target_subfolder else game_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        seven_z = get_7z_exe()
        installed_files = []

        if seven_z and seven_z.exists():
            # Get list of files before extract
            if progress_callback:
                progress_callback(0.1, f"Анализ архива {archive_path.name}...")

            raw_files = Installer.list_archive_files_7z(seven_z, archive_path)

            if progress_callback:
                progress_callback(0.3, f"Распаковка {len(raw_files)} файлов через 7-Zip...")

            cmd = [str(seven_z), "x", str(archive_path), f"-o{dest_dir}", "-y"]
            proc = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")
            if proc.returncode != 0:
                raise InstallError(f"Ошибка 7-Zip при распаковке: {proc.stderr or proc.stdout}")

            # Calculate relative path from game_dir for manifest
            prefix = f"{target_subfolder}/" if target_subfolder else ""
            for f in raw_files:
                rel = f"{prefix}{f.replace('\\', '/')}"
                installed_files.append(rel)

        else:
            # Fallback to standard zipfile if 7z is missing
            try:
                with zipfile.ZipFile(archive_path, "r") as z:
                    infolist = z.infolist()
                    total = len(infolist)
                    prefix = f"{target_subfolder}/" if target_subfolder else ""

                    for i, item in enumerate(infolist):
                        if item.filename.endswith("/"):
                            continue
                        out_path = dest_dir / item.filename
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(item) as src, open(out_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                        rel = f"{prefix}{item.filename.replace('\\', '/')}"
                        installed_files.append(rel)

                        if progress_callback and total > 0:
                            progress_callback(0.3 + 0.6 * (i + 1) / total, f"Распаковка: {item.filename}")
            except Exception as e:
                raise InstallError(f"Ошибка при распаковке архива: {e}")

        # Auto-convert Address Library files from Format 5 to Format 2
        Installer.fix_address_library_compatibility(game_dir)

        # Update or create manifest
        manifest_path = Installer.get_manifest_path(game_dir)
        existing_manifest = {"files": [], "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    existing_manifest = json.load(f)
            except Exception:
                pass

        all_files = list(set(existing_manifest.get("files", []) + installed_files))
        manifest = {
            "version": version_label,
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": all_files
        }
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save manifest: {e}")

        return manifest

    @staticmethod
    def fix_address_library_compatibility(game_dir: Path):
        """Checks Data/SKSE/Plugins for versionlib files in Format 5 and converts them to Format 2."""
        skse_plugins = game_dir / "Data" / "SKSE" / "Plugins"
        if not skse_plugins.exists():
            return
        for bin_file in skse_plugins.glob("versionlib-*.bin"):
            try:
                with open(bin_file, "rb") as f:
                    header = f.read(4)
                if len(header) == 4 and int.from_bytes(header, "little") == 5:
                    print(f"[Installer] Converting Address Library {bin_file.name} to Format 2...")
                    convert_format5_to_format2(bin_file, bin_file)
            except Exception as e:
                print(f"[Installer] Warning: Failed to convert {bin_file}: {e}")

    @staticmethod
    def uninstall_mod(
        game_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> int:
        """
        Removes all installed mod files recorded in the manifest.
        Restores clean vanilla Skyrim without touching game files.
        """
        manifest_path = Installer.get_manifest_path(game_dir)
        if not manifest_path.exists():
            # If no manifest, check common mod files
            fallback_files = [
                "Data/SkyrimTogether.esp",
                "Data/SkyrimTogetherReborn",
                "Data/SkyrimTogether",
                "Data/SkyrimTogetherRebornBehaviors",
                "SkyrimTogether.exe",
                "SkyrimTogetherServer.exe",
                "server_settings.ini"
            ]
            count = 0
            for f in fallback_files:
                p = game_dir / f
                if p.is_file():
                    p.unlink()
                    count += 1
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    count += 1
            return count

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            raise InstallError(f"Не удалось прочитать манифест: {e}")

        files = manifest.get("files", [])
        total = len(files)
        deleted_count = 0

        for i, rel_path in enumerate(files):
            target = game_dir / rel_path
            if target.exists() and target.is_file():
                try:
                    target.unlink()
                    deleted_count += 1
                except Exception:
                    pass

            if progress_callback and total > 0:
                progress_callback((i + 1) / total, f"Удаление: {rel_path}")

        # Clean up empty folders in Data
        for folder_name in ["SkyrimTogetherReborn", "SkyrimTogetherRebornBehaviors", "SkyrimTogether"]:
            p = game_dir / "Data" / folder_name
            if p.exists() and p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

        try:
            manifest_path.unlink()
        except Exception:
            pass

        return deleted_count
