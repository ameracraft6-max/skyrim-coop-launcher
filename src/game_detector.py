import os
import re
import string
import sys
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

def get_file_version(filepath: str) -> Optional[str]:
    """Extracts FileVersion string from a Windows PE binary (.exe/.dll) using Win32 API."""
    if not os.path.exists(filepath):
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
        if size == 0:
            return None
        res = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(filepath, 0, size, res):
            return None
        
        # VS_FIXEDFILEINFO query
        p_val = ctypes.c_void_p()
        u_len = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(res, "\\", ctypes.byref(p_val), ctypes.byref(u_len)):
            return None
        
        # Structure has dwFileVersionMS and dwFileVersionLS at offset 8 and 12
        raw_bytes = ctypes.string_at(p_val, u_len.value)
        # MS (Major.Minor) at bytes 8-12, LS (Build.Revision) at bytes 12-16
        ms_part = int.from_bytes(raw_bytes[8:12], byteorder="little")
        ls_part = int.from_bytes(raw_bytes[12:16], byteorder="little")
        major = ms_part >> 16
        minor = ms_part & 0xFFFF
        build = ls_part >> 16
        revision = ls_part & 0xFFFF
        return f"{major}.{minor}.{build}.{revision}"
    except Exception:
        return None

def parse_steam_libraries() -> List[Path]:
    """Finds all Steam library folders by parsing libraryfolders.vdf."""
    libraries = []
    try:
        import winreg
        steam_path = None
        for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                sub_path = r"Software\Valve\Steam" if root_key == winreg.HKEY_CURRENT_USER else r"SOFTWARE\WOW6432Node\Valve\Steam"
                with winreg.OpenKey(root_key, sub_path) as key:
                    val, _ = winreg.QueryValueEx(key, "SteamPath" if root_key == winreg.HKEY_CURRENT_USER else "InstallPath")
                    if val and os.path.exists(val):
                        steam_path = Path(val)
                        break
            except Exception:
                continue
        
        if steam_path:
            libraries.append(steam_path)
            vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
            if vdf_path.exists():
                with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Matches "path"		"D:\\SteamLibrary"
                matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
                for m in matches:
                    p = Path(m.replace(r"\\", "\\"))
                    if p.exists() and p not in libraries:
                        libraries.append(p)
    except Exception:
        pass
    return libraries

def get_drive_letters() -> List[str]:
    drives = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1
    except Exception:
        drives = ["C:\\", "D:\\", "E:\\"]
    return drives

def find_skyrim_directory() -> Optional[Path]:
    """Attempts to auto-detect Skyrim Special Edition installation directory."""
    import winreg

    # 1. Check Bethesda registry
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim Special Edition"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Bethesda Softworks\Skyrim Special Edition"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim"),
    ]
    for hkey, subkey in reg_paths:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                val, _ = winreg.QueryValueEx(key, "installed path")
                if val and (Path(val) / "SkyrimSE.exe").exists():
                    return Path(val)
        except Exception:
            continue

    # 2. Check Steam libraries
    for lib in parse_steam_libraries():
        candidate = lib / "steamapps" / "common" / "Skyrim Special Edition"
        if (candidate / "SkyrimSE.exe").exists():
            return candidate

    # 3. Check common folder patterns on all drives
    common_subdirs = [
        r"SteamLibrary\steamapps\common\Skyrim Special Edition",
        r"Games\Skyrim Special Edition",
        r"Games\Skyrim SE",
        r"Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition",
        r"Program Files\Steam\steamapps\common\Skyrim Special Edition",
        r"Skyrim Special Edition",
    ]
    for drive in get_drive_letters():
        for sub in common_subdirs:
            candidate = Path(drive) / sub
            if (candidate / "SkyrimSE.exe").exists():
                return candidate

    return None

def inspect_game(game_dir: Path) -> Dict[str, Any]:
    """Inspects the specified game directory and returns diagnostic details."""
    result = {
        "valid": False,
        "exe_found": False,
        "version": None,
        "version_compatible": False,
        "together_installed": False,
        "together_version": None,
        "together_exe": None,
        "server_exe": None,
        "address_library_installed": False,
        "notes": []
    }
    
    if not game_dir or not game_dir.exists():
        result["notes"].append("Папка игры не выбрана или не существует.")
        return result

    exe_path = game_dir / "SkyrimSE.exe"
    if not exe_path.exists():
        result["notes"].append("Файл SkyrimSE.exe не найден в указанной папке.")
        return result

    result["exe_found"] = True
    ver = get_file_version(str(exe_path))
    result["version"] = ver

    # Skyrim Together Reborn requires version 1.6.x (1.6.590+)
    if ver:
        parts = [int(p) for p in ver.split(".") if p.isdigit()]
        if len(parts) >= 2 and (parts[0] > 1 or (parts[0] == 1 and parts[1] >= 6)):
            result["version_compatible"] = True
        else:
            result["notes"].append(f"Версия игры {ver} ниже 1.6. Нужен Skyrim SE версии 1.6+ (Anniversary update).")
    else:
        # Fallback if version couldn't be read: assume compatible if exe exists
        result["version_compatible"] = True

    # Check for Address Library
    address_lib_se = game_dir / "Data" / "SKSE" / "Plugins" / "versionlib-1-6-640-0.bin"
    address_lib_dir = game_dir / "Data" / "SKSE" / "Plugins"
    if address_lib_dir.exists() and any(address_lib_dir.glob("versionlib-*.bin")):
        result["address_library_installed"] = True

    # Check for Skyrim Together executable
    together_candidates = [
        game_dir / "SkyrimTogether.exe",
        game_dir / "SkyrimTogetherReborn" / "SkyrimTogether.exe",
        game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogether.exe",
        game_dir / "Data" / "SkyrimTogether" / "SkyrimTogether.exe"
    ]
    for c in together_candidates:
        if c.exists():
            result["together_installed"] = True
            result["together_exe"] = str(c)
            result["together_version"] = get_file_version(str(c)) or "Установлен"
            break

    # Check for Server executable
    server_candidates = [
        game_dir / "SkyrimTogetherServer.exe",
        game_dir / "Server" / "SkyrimTogetherServer.exe",
        game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogetherServer.exe",
        game_dir / "Data" / "SkyrimTogether" / "SkyrimTogetherServer.exe"
    ]
    for s in server_candidates:
        if s.exists():
            result["server_exe"] = str(s)
            break

    result["valid"] = result["exe_found"] and result["version_compatible"]
    return result
