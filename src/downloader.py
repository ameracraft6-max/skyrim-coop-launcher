import os
import sys
import time
import requests
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List

HEADERS_USER_AGENT = {
    "User-Agent": "SkyrimCoopLauncher/1.0 (Windows NT 10.0; Win64; x64)"
}

class DownloadError(Exception):
    pass

class Downloader:
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def download_file(
        self,
        url: str,
        dest_path: Path,
        progress_callback: Optional[Callable[[float, float, float, str], None]] = None,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Path:
        """
        Downloads a file with real-time progress.
        progress_callback(fraction: 0.0-1.0, speed_mb_s, downloaded_mb, status_text)
        """
        self._cancelled = False
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dest = dest_path.with_suffix(dest_path.suffix + ".part")

        headers = dict(HEADERS_USER_AGENT)
        if custom_headers:
            headers.update(custom_headers)

        try:
            with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0
                start_time = time.time()
                last_time = start_time
                last_bytes = 0
                speed = 0.0

                with open(temp_dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if self._cancelled:
                            f.close()
                            if temp_dest.exists():
                                temp_dest.unlink()
                            raise DownloadError("Загрузка отменена пользователем.")
                        
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            elapsed = now - last_time
                            if elapsed >= 0.5:
                                speed = (downloaded - last_bytes) / elapsed / (1024 * 1024)
                                last_bytes = downloaded
                                last_time = now

                                frac = downloaded / total_size if total_size > 0 else 0.0
                                dl_mb = downloaded / (1024 * 1024)
                                tot_mb = total_size / (1024 * 1024) if total_size > 0 else 0.0
                                status = f"{dl_mb:.1f} / {tot_mb:.1f} МБ ({speed:.2f} МБ/с)" if total_size > 0 else f"{dl_mb:.1f} МБ ({speed:.2f} МБ/с)"

                                if progress_callback:
                                    progress_callback(frac, speed, dl_mb, status)

                if temp_dest.exists():
                    if dest_path.exists():
                        dest_path.unlink()
                    temp_dest.rename(dest_path)
                return dest_path

        except Exception as e:
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except Exception:
                    pass
            if self._cancelled:
                raise DownloadError("Загрузка отменена.")
            raise DownloadError(f"Ошибка скачивания: {e}")

    @staticmethod
    def get_github_latest_release(repo: str) -> Dict[str, Any]:
        """
        Fetches metadata and asset download URLs for the latest GitHub release.
        repo format: "owner/repo" (e.g. "SkyrimTogether/SkyrimTogetherReborn")
        """
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        r = requests.get(url, headers=HEADERS_USER_AGENT, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        tag = data.get("tag_name", "unknown")
        assets = []
        for asset in data.get("assets", []):
            assets.append({
                "name": asset.get("name"),
                "size": asset.get("size"),
                "download_url": asset.get("browser_download_url"),
            })
        return {
            "tag": tag,
            "name": data.get("name") or tag,
            "body": data.get("body", ""),
            "assets": assets
        }

    @staticmethod
    def validate_nexus_key(api_key: str) -> Dict[str, Any]:
        """Validates Nexus Mods API key against Nexus API."""
        if not api_key.strip():
            return {"valid": False, "error": "API ключ не указан"}
        
        url = "https://api.nexusmods.com/v1/users/validate.json"
        headers = dict(HEADERS_USER_AGENT)
        headers["apikey"] = api_key.strip()
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return {
                    "valid": True,
                    "name": data.get("name", "User"),
                    "is_premium": data.get("is_premium", False),
                    "is_supporter": data.get("is_supporter", False)
                }
            elif r.status_code == 401:
                return {"valid": False, "error": "Неверный или просроченный API-ключ Nexus"}
            else:
                return {"valid": False, "error": f"Ошибка сервера Nexus (Код {r.status_code})"}
        except Exception as e:
            return {"valid": False, "error": f"Сетевая ошибка: {e}"}

    @staticmethod
    def get_nexus_mod_files(api_key: str, mod_id: int, game: str = "skyrimspecialedition") -> List[Dict[str, Any]]:
        """Retrieves list of files for a specific mod on Nexus."""
        url = f"https://api.nexusmods.com/v1/games/{game}/mods/{mod_id}/files.json"
        headers = dict(HEADERS_USER_AGENT)
        headers["apikey"] = api_key.strip()
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("files", [])

    @staticmethod
    def get_nexus_download_link(api_key: str, mod_id: int, file_id: int, game: str = "skyrimspecialedition") -> Optional[str]:
        """Requests direct download link for a mod file from Nexus (Requires Premium or direct key)."""
        url = f"https://api.nexusmods.com/v1/games/{game}/mods/{mod_id}/files/{file_id}/download_link.json"
        headers = dict(HEADERS_USER_AGENT)
        headers["apikey"] = api_key.strip()
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("URI")
        return None
