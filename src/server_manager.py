import os
import sys
import socket
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple

class ServerManager:
    @staticmethod
    def detect_ips() -> Dict[str, str]:
        """Detects available IP addresses (Radmin VPN, LAN, Localhost)."""
        ips = {
            "radmin": None,
            "lan": None,
            "localhost": "127.0.0.1"
        }
        try:
            hostname = socket.gethostname()
            _, _, addrs = socket.gethostbyname_ex(hostname)
            for addr in addrs:
                # Radmin VPN addresses start with 26.
                if addr.startswith("26."):
                    ips["radmin"] = addr
                elif addr.startswith("192.168.") or addr.startswith("10.") or addr.startswith("172."):
                    if not ips["lan"]:
                        ips["lan"] = addr
        except Exception:
            pass
        return ips

    @staticmethod
    def get_server_exe(game_dir: Path) -> Optional[Path]:
        candidates = [
            game_dir / "SkyrimTogetherServer.exe",
            game_dir / "Server" / "SkyrimTogetherServer.exe",
            game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogetherServer.exe",
            game_dir / "Data" / "SkyrimTogether" / "SkyrimTogetherServer.exe"
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    @staticmethod
    def ensure_server_config(server_dir: Path, server_name: str = "Skyrim Together Server", port: int = 10578, password: str = "") -> Path:
        """Creates or updates server_settings.ini if needed."""
        ini_path = server_dir / "server_settings.ini"
        if not ini_path.exists():
            default_content = f"""[Server]
bIsAnnounceServer = false
sServerPassword = "{password}"
sServerName = "{server_name}"
uPort = {port}
uMaxPlayers = 8
bEnablePvp = true
"""
            try:
                with open(ini_path, "w", encoding="utf-8") as f:
                    f.write(default_content)
            except Exception as e:
                print(f"Error creating server_settings.ini: {e}")
        return ini_path

    @staticmethod
    def launch_server(game_dir: Path) -> Tuple[bool, str]:
        """Launches SkyrimTogetherServer.exe in a separate console window."""
        server_exe = ServerManager.get_server_exe(game_dir)
        if not server_exe:
            return False, "Файл SkyrimTogetherServer.exe не найден. Сначала установите кооп-мод."

        ServerManager.ensure_server_config(server_exe.parent)

        try:
            # CREATE_NEW_CONSOLE to let the host see the server log
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(
                [str(server_exe)],
                cwd=str(server_exe.parent),
                creationflags=CREATE_NEW_CONSOLE
            )
            return True, "Сервер успешно запущен в отдельном окне консоли!"
        except Exception as e:
            return False, f"Не удалось запустить сервер: {e}"
