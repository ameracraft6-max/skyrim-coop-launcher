import os
import sys
import time
import shutil
import ctypes
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Fix Windows console UTF-8 encoding immediately
if sys.platform == "win32":
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local imports work seamlessly
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import load_config, save_config, get_app_dir
from game_detector import find_skyrim_directory, inspect_game, get_file_version
from installer import Installer, convert_format5_to_format2, get_7z_exe
from server_manager import ServerManager
from downloader import Downloader, DownloadError

# =====================================================================
# ANSI COLORS & WINDOWS VIRTUAL TERMINAL PROCESSING
# =====================================================================
def enable_ansi_terminal():
    """Enables ANSI escape sequence processing in Windows CMD / PowerShell."""
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                mode.value |= 0x0004
                kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass

enable_ansi_terminal()

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
GRAY    = "\033[90m"

# =====================================================================
# UI HELPER FUNCTIONS
# =====================================================================
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    banner = f"""{CYAN}======================================================================
           {WHITE}{BOLD}SKYRIM TOGETHER REBORN -- CO-OP LAUNCHER{RESET}{CYAN}
                 {YELLOW}Консольная версия для Windows{CYAN}
======================================================================{RESET}"""
    print(banner)

def render_progress_bar(fraction: float, total_width: int = 30) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(total_width * fraction))
    bar = f"{GREEN}{'#' * filled}{GRAY}{'-' * (total_width - filled)}{RESET}"
    percent = f"{int(fraction * 100):3d}%"
    return f"[{bar}] {BOLD}{percent}{RESET}"

def prompt_press_enter(msg: str = "Нажмите Enter, чтобы вернуться в меню..."):
    print()
    input(f"{GRAY}{msg}{RESET}")

# =====================================================================
# STATUS INSPECTION HELPERS
# =====================================================================
def get_address_library_detailed_status(game_dir: Path) -> Tuple[bool, str]:
    """Inspects versionlib binary format (Format 2 vs Format 5)."""
    skse_plugins = game_dir / "Data" / "SKSE" / "Plugins"
    if not skse_plugins.exists():
        return False, f"{RED}[X] Не установлен (папка SKSE\\Plugins не найдена){RESET}"

    bins = list(skse_plugins.glob("versionlib-*.bin"))
    if not bins:
        return False, f"{RED}[X] Не установлен (файлы versionlib-*.bin не найдены){RESET}"

    has_format5 = False
    v2_names = []
    for b in bins:
        try:
            with open(b, "rb") as f:
                header = f.read(4)
            if len(header) == 4:
                fmt = int.from_bytes(header, "little")
                if fmt == 2:
                    v2_names.append(b.name)
                elif fmt == 5:
                    has_format5 = True
        except Exception:
            pass

    if has_format5:
        return False, f"{YELLOW}[!] Установлен, но Format 5 (Нужно исправить! Пункт [4]){RESET}"
    if v2_names:
        return True, f"{GREEN}[OK] Установлен (Format 2 - Оптимизирован для коопа){RESET}"
    return True, f"{GREEN}[OK] Установлен{RESET}"

def get_together_patch_status(together_exe_path: Optional[Path]) -> Tuple[bool, str]:
    """Checks if SkyrimTogether.exe has the modern SteamStub and SkyrimVM 0x210 patches."""
    if not together_exe_path or not together_exe_path.exists():
        return False, f"{RED}[X] Не установлен{RESET}"

    try:
        with open(together_exe_path, "rb") as f:
            # Check hook offset: 0x2688c4
            f.seek(0x2688c4)
            b = f.read(1)
            # Check VM offset: 0x2ad15d
            f.seek(0x2ad15d)
            vm = f.read(7)

        is_steamstub = (b == b"\xe9")
        is_vm = (vm == bytes.fromhex("48 8b 88 10 02 00 00"))

        if is_steamstub and is_vm:
            return True, f"{GREEN}[OK] Установлен и пропатчен (SteamStub + SkyrimVM 1.7+ Fix){RESET}"
        elif not is_steamstub or not is_vm:
            return False, f"{YELLOW}[!] Установлен, но НЕ пропатчен (Нужно исправить! Пункт [4]){RESET}"
        else:
            return True, f"{GREEN}[OK] Установлен ({together_exe_path.name}){RESET}"
    except Exception:
        return True, f"{GREEN}[OK] Установлен{RESET}"

# =====================================================================
# TERMINAL APPLICATION CLASS
# =====================================================================
class TerminalLauncherApp:
    def __init__(self):
        self.config = load_config()
        self.game_dir: Optional[Path] = None
        self._init_game_directory()

    def _init_game_directory(self):
        saved_path = self.config.get("game_path", "").strip()
        if saved_path and Path(saved_path).exists() and (Path(saved_path) / "SkyrimSE.exe").exists():
            self.game_dir = Path(saved_path)
            return

        # Auto-detect Skyrim SE
        detected = find_skyrim_directory()
        if detected:
            self.game_dir = detected
            self.config["game_path"] = str(detected)
            save_config(self.config)

    def print_dashboard(self):
        print(f"{BOLD}[ СТАТУС СИСТЕМЫ ]{RESET}")
        
        # 1. Game Path & Version
        if self.game_dir and (self.game_dir / "SkyrimSE.exe").exists():
            ver = get_file_version(str(self.game_dir / "SkyrimSE.exe")) or "Неизвестна"
            print(f"  * Папка игры:      {WHITE}{self.game_dir}{RESET}")
            print(f"  * Версия Skyrim:   {WHITE}{ver}{RESET} {GREEN}[OK - Совместима]{RESET}")
        else:
            print(f"  * Папка игры:      {RED}[X] НЕ НАЙДЕНА (Укажите в Настройках [6]){RESET}")

        if not self.game_dir:
            print()
            return

        # 2. Address Library Status
        _, addr_msg = get_address_library_detailed_status(self.game_dir)
        print(f"  * Address Library: {addr_msg}")

        # 3. Skyrim Together Status
        st_exe = self.game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogether.exe"
        if not st_exe.exists():
            st_exe = self.game_dir / "SkyrimTogether.exe"
        _, st_msg = get_together_patch_status(st_exe if st_exe.exists() else None)
        print(f"  * Skyrim Together: {st_msg}")

        # 4. Server Status
        srv_exe = ServerManager.get_server_exe(self.game_dir)
        if srv_exe:
            print(f"  * Сервер коопа:    {GREEN}[OK] Установлен ({srv_exe.name}){RESET}")
        else:
            print(f"  * Сервер коопа:    {GRAY}[-] Не установлен (будет добавлен с модом){RESET}")

        # 5. Network IPs
        ips = ServerManager.detect_ips()
        radmin = ips.get("radmin")
        lan = ips.get("lan")
        ip_parts = []
        if radmin:
            ip_parts.append(f"{GREEN}Radmin VPN: {radmin}{RESET}")
        else:
            ip_parts.append(f"{GRAY}Radmin VPN: не запущен{RESET}")
        if lan:
            ip_parts.append(f"LAN: {lan}")
        ip_str = " | ".join(ip_parts)
        print(f"  * IP для друзей:   {ip_str}")
        print()

    def print_menu(self):
        print(f"{BOLD}[ МЕНЮ ДЕЙСТВИЙ ]{RESET}")
        print(f"  {CYAN}[1]{RESET} {BOLD}>> Запустить Skyrim Together (Кооператив){RESET}")
        print(f"  {CYAN}[2]{RESET} {BOLD}>> Запустить Сервер (Для хоста игры){RESET}")
        print(f"  {CYAN}[3]{RESET} [~] Установить / Переустановить кооп-мод")
        print(f"  {CYAN}[4]{RESET} [!] Проверить и исправить файлы (Патч SteamStub + Address Library)")
        print(f"  {CYAN}[5]{RESET} [-] Удалить кооп-мод (Вернуть чистый Skyrim)")
        print(f"  {CYAN}[6]{RESET} [*] Настройки (Путь к игре, порт сервера)")
        print(f"  {CYAN}[0]{RESET} [X] Выход")
        print()

    def run(self):
        while True:
            clear_screen()
            print_banner()
            self.print_dashboard()
            self.print_menu()

            try:
                choice = input(f"{BOLD}Выберите действие [0-6]: {RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{YELLOW}Выход из программы...{RESET}")
                break

            if choice == "1":
                self.action_launch_game()
            elif choice == "2":
                self.action_launch_server()
            elif choice == "3":
                self.action_install_mod()
            elif choice == "4":
                self.action_diagnose_and_fix()
            elif choice == "5":
                self.action_uninstall_mod()
            elif choice == "6":
                self.action_settings()
            elif choice == "0":
                print(f"\n{GREEN}До встречи в Скайриме!{RESET}")
                time.sleep(0.5)
                break
            else:
                print(f"{RED}Неверный выбор! Введите число от 0 до 6.{RESET}")
                time.sleep(1)

    # -----------------------------------------------------------------
    # ACTION: LAUNCH GAME
    # -----------------------------------------------------------------
    def action_launch_game(self):
        clear_screen()
        print_banner()
        print(f"{BOLD}{CYAN}=== ЗАПУСК SKYRIM TOGETHER ==={RESET}\n")

        if not self.game_dir or not (self.game_dir / "SkyrimSE.exe").exists():
            print(f"{RED}Ошибка: Папка со SkyrimSE.exe не найдена! Укажите путь в Настройках [6].{RESET}")
            prompt_press_enter()
            return

        # Find SkyrimTogether.exe
        st_exe = self.game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogether.exe"
        if not st_exe.exists():
            st_exe = self.game_dir / "SkyrimTogether.exe"
        if not st_exe.exists():
            print(f"{RED}Ошибка: Файл SkyrimTogether.exe не найден!{RESET}")
            print(f"{YELLOW}Сначала установите кооп-мод через пункт [3] меню.{RESET}")
            prompt_press_enter()
            return

        print(f"[*] Проверка совместимости Address Library и патча SteamStub...")
        Installer.fix_address_library_compatibility(self.game_dir)

        print(f"[*] Запуск игры: {st_exe}...")
        print(f"[*] Рабочая директория (CWD): {self.game_dir} (исключает ошибку SETUPAPI.dll)")

        try:
            # CRITICAL: working directory MUST be game_dir
            creationflags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
            subprocess.Popen([str(st_exe)], cwd=str(self.game_dir), creationflags=creationflags)
            print(f"\n{GREEN}{BOLD}[OK] Игра успешно запущена!{RESET}")
            print(f"{YELLOW}Совет: В главном меню игры нажмите клавишу F2 или Right Ctrl для подключения к серверу.{RESET}")
        except Exception as e:
            print(f"\n{RED}Ошибка при запуске игры: {e}{RESET}")

        prompt_press_enter()

    # -----------------------------------------------------------------
    # ACTION: LAUNCH SERVER
    # -----------------------------------------------------------------
    def action_launch_server(self):
        clear_screen()
        print_banner()
        print(f"{BOLD}{CYAN}=== ЗАПУСК СЕРВЕРА SKYRIM TOGETHER ==={RESET}\n")

        if not self.game_dir:
            print(f"{RED}Сначала укажите путь к игре в Настройках [6]!{RESET}")
            prompt_press_enter()
            return

        ips = ServerManager.detect_ips()
        radmin = ips.get("radmin")
        lan = ips.get("lan")

        print(f"{BOLD}Сетевые адреса для подключения друзей:{RESET}")
        if radmin:
            print(f"  * {GREEN}{BOLD}Radmin VPN IP: {radmin}{RESET}  <- {YELLOW}Сообщите этот IP друзьям!{RESET}")
        else:
            print(f"  * {YELLOW}Radmin VPN IP не обнаружен. Рекомендуется запустить Radmin VPN.{RESET}")
        if lan:
            print(f"  * Локальная сеть (LAN): {lan}")
        print(f"  * Локальный хост (для вас): 127.0.0.1")
        print()

        success, msg = ServerManager.launch_server(self.game_dir)
        if success:
            print(f"{GREEN}{BOLD}[OK] {msg}{RESET}")
            print(f"{YELLOW}Окно сервера открылось отдельно. Не закрывайте его, пока играете!{RESET}")
        else:
            print(f"{RED}[ОШИБКА] {msg}{RESET}")

        prompt_press_enter()

    # -----------------------------------------------------------------
    # ACTION: DIAGNOSE & FIX
    # -----------------------------------------------------------------
    def action_diagnose_and_fix(self):
        clear_screen()
        print_banner()
        print(f"{BOLD}{CYAN}=== ДИАГНОСТИКА И АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ==={RESET}\n")

        if not self.game_dir or not (self.game_dir / "SkyrimSE.exe").exists():
            print(f"{RED}Папка игры не найдена! Укажите путь в Настройках [6].{RESET}")
            prompt_press_enter()
            return

        print(f"[*] Сканирование папки: {self.game_dir}")
        ver = get_file_version(str(self.game_dir / "SkyrimSE.exe"))
        print(f"[*] Версия SkyrimSE.exe: {ver}")

        # 1. Address Library Format Check & Fix
        print(f"\n[*] 1. Проверка Address Library...")
        skse_plugins = self.game_dir / "Data" / "SKSE" / "Plugins"
        if skse_plugins.exists():
            for b in skse_plugins.glob("versionlib-*.bin"):
                try:
                    with open(b, "rb") as f:
                        hdr = f.read(4)
                    fmt = int.from_bytes(hdr, "little") if len(hdr) == 4 else 0
                    if fmt == 5:
                        print(f"    {YELLOW}-> Найден {b.name} в Format 5 (вызывает сбой в Skyrim Together Reborn)!{RESET}")
                        print(f"    [*] Авто-конвертация {b.name} из Format 5 в Format 2...")
                        backup = b.with_suffix(".bin.v5_backup")
                        if not backup.exists():
                            shutil.copy2(b, backup)
                        convert_format5_to_format2(b, b)
                        print(f"    {GREEN}[OK] Файл {b.name} успешно конвертирован в Format 2!{RESET}")
                    elif fmt == 2:
                        print(f"    {GREEN}[OK] {b.name} уже в правильном Format 2.{RESET}")
                    else:
                        print(f"    [*] {b.name} имеет формат {fmt}.")
                except Exception as e:
                    print(f"    {RED}Ошибка проверки {b.name}: {e}{RESET}")
        else:
            print(f"    {RED}Папка Data\\SKSE\\Plugins отсутствует. Установите Address Library через пункт [3].{RESET}")

        # 2. Patch SkyrimTogether.exe for SteamStub
        print(f"\n[*] 2. Проверка бинарного файла SkyrimTogether.exe...")
        st_exe = self.game_dir / "Data" / "SkyrimTogetherReborn" / "SkyrimTogether.exe"
        if not st_exe.exists():
            st_exe = self.game_dir / "SkyrimTogether.exe"

        if st_exe.exists():
            is_patched, _ = get_together_patch_status(st_exe)
            if is_patched:
                print(f"    {GREEN}[OK] Патч SteamStub CEG уже установлен в {st_exe.name}.{RESET}")
            else:
                print(f"    {YELLOW}-> {st_exe.name} не имеет патча для современных версий Skyrim!{RESET}")
                print(f"    [*] Применение байт-патча code-cave...")
                Installer.patch_skyrim_together_binary(st_exe)
                is_patched_after, _ = get_together_patch_status(st_exe)
                if is_patched_after:
                    print(f"    {GREEN}[OK] Патч успешно применен! Игра больше не будет зависать/вылетать.{RESET}")
                else:
                    print(f"    {RED}[!] Не удалось автоматически применить патч.{RESET}")
        else:
            print(f"    {RED}SkyrimTogether.exe не найден. Установите мод через пункт [3].{RESET}")

        print(f"\n{GREEN}{BOLD}[OK] Диагностика и исправление завершены!{RESET}")
        prompt_press_enter()

    # -----------------------------------------------------------------
    # ACTION: INSTALL MOD
    # -----------------------------------------------------------------
    def action_install_mod(self):
        clear_screen()
        print_banner()
        print(f"{BOLD}{CYAN}=== УСТАНОВКА / ОБНОВЛЕНИЕ КООП-МОДА ==={RESET}\n")

        if not self.game_dir or not (self.game_dir / "SkyrimSE.exe").exists():
            print(f"{RED}Сначала укажите корректную папку со SkyrimSE.exe в Настройках [6]!{RESET}")
            prompt_press_enter()
            return

        # Check local archives first
        app_dir = get_app_dir()
        candidate_bundles = [
            app_dir / "skyrim-coop-bundle.zip",
            app_dir / "SkyrimTogether_Release_Bundle.zip",
            app_dir / "CoopBundle.zip",
            app_dir.parent / "skyrim-coop-bundle.zip",
        ]
        local_bundle = next((c for c in candidate_bundles if c.exists()), None)

        print("Выберите источник для установки модов:")
        if local_bundle:
            size_mb = local_bundle.stat().st_size / (1024 * 1024)
            print(f"  {CYAN}[1]{RESET} {BOLD}Установить из локального архива (быстро, офлайн){RESET}")
            print(f"      {GRAY}Найден файл: {local_bundle.name} ({size_mb:.1f} МБ){RESET}")
        else:
            print(f"  {CYAN}[1]{RESET} Указать путь к локальному ZIP архиву вручную")

        print(f"  {CYAN}[2]{RESET} Скачать автоматически с GitHub (ameracraft6-max/skyrim-coop-launcher)")
        api_key = self.config.get("nexus_api_key", "").strip()
        if api_key:
            print(f"  {CYAN}[3]{RESET} Скачать с Nexus Mods (по сохраненному API-ключу)")
        print(f"  {CYAN}[0]{RESET} Отмена")
        print()

        src_choice = input(f"{BOLD}Выберите источник [0-3]: {RESET}").strip()
        if src_choice == "0":
            return

        downloader = Downloader()

        if src_choice == "1":
            archive_to_install = local_bundle
            if not archive_to_install:
                custom_path = input("Введите полный путь к ZIP архиву модов: ").strip().strip('"')
                archive_to_install = Path(custom_path)
                if not archive_to_install.exists():
                    print(f"{RED}Файл не найден: {archive_to_install}{RESET}")
                    prompt_press_enter()
                    return

            print(f"\n[*] Распаковка архива {archive_to_install.name}...")
            try:
                def on_extract_progress(frac, msg):
                    bar = render_progress_bar(frac)
                    print(f"\r  {bar} {msg[:40]:<40}", end="", flush=True)

                Installer.install_archive(
                    archive_to_install,
                    self.game_dir,
                    target_subfolder="Data",
                    version_label="coop-bundle",
                    progress_callback=on_extract_progress
                )
                print(f"\n\n{GREEN}{BOLD}[OK] Кооп-мод успешно установлен!{RESET}")
                Installer.fix_address_library_compatibility(self.game_dir)
            except Exception as e:
                print(f"\n\n{RED}Ошибка установки: {e}{RESET}")

        elif src_choice == "2":
            # Download from GitHub
            repo = self.config.get("github_repo", "ameracraft6-max/skyrim-coop-launcher")
            print(f"\n[*] Подключение к GitHub ({repo})...")
            try:
                rel = Downloader.get_github_latest_release(repo)
                assets = rel.get("assets", [])
                zip_asset = next((a for a in assets if a["name"].endswith(".zip")), None)
                if not zip_asset:
                    print(f"{RED}В последнем релизе GitHub не найден ZIP архив с модами!{RESET}")
                    prompt_press_enter()
                    return

                temp_dir = app_dir / "temp_downloads"
                temp_dir.mkdir(exist_ok=True)
                dest_zip = temp_dir / zip_asset["name"]

                print(f"[*] Скачивание {zip_asset['name']}...")
                def on_dl_progress(frac, speed, dl_mb, status):
                    bar = render_progress_bar(frac)
                    print(f"\r  {bar} {status[:35]:<35}", end="", flush=True)

                downloader.download_file(zip_asset["download_url"], dest_zip, progress_callback=on_dl_progress)
                print(f"\n\n[*] Распаковка файлов в игру...")

                def on_extract_progress(frac, msg):
                    bar = render_progress_bar(frac)
                    print(f"\r  {bar} {msg[:40]:<40}", end="", flush=True)

                Installer.install_archive(
                    dest_zip,
                    self.game_dir,
                    target_subfolder="Data",
                    version_label=f"github-{rel.get('tag', 'latest')}",
                    progress_callback=on_extract_progress
                )
                print(f"\n\n{GREEN}{BOLD}[OK] Кооп-мод успешно скачан и установлен!{RESET}")
                Installer.fix_address_library_compatibility(self.game_dir)
            except Exception as e:
                print(f"\n\n{RED}Ошибка загрузки с GitHub: {e}{RESET}")

        elif src_choice == "3" and api_key:
            print(f"\n[*] Подключение к Nexus Mods API...")
            try:
                temp_dir = app_dir / "temp_downloads"
                temp_dir.mkdir(exist_ok=True)

                def on_dl_progress(frac, speed, dl_mb, status):
                    bar = render_progress_bar(frac)
                    print(f"\r  {bar} {status[:35]:<35}", end="", flush=True)

                # 1. Address Library (32444)
                print("[*] Поиск файлов Address Library на Nexus...")
                addr_files = Downloader.get_nexus_mod_files(api_key, 32444)
                main_addr = [f for f in addr_files if f.get("category_name") == "MAIN"] or addr_files[-1:]
                addr_url = Downloader.get_nexus_download_link(api_key, 32444, main_addr[-1]["file_id"])
                addr_zip = temp_dir / "address_library.zip"
                print(f"[*] Скачивание Address Library ({main_addr[-1].get('name')})...")
                downloader.download_file(addr_url, addr_zip, progress_callback=on_dl_progress)
                print()

                # 2. Skyrim Together Reborn (69993)
                print("[*] Поиск файлов Skyrim Together Reborn на Nexus...")
                str_files = Downloader.get_nexus_mod_files(api_key, 69993)
                main_str = [f for f in str_files if f.get("category_name") == "MAIN"] or str_files[-1:]
                str_url = Downloader.get_nexus_download_link(api_key, 69993, main_str[-1]["file_id"])
                str_zip = temp_dir / "skyrim_together_reborn.zip"
                print(f"[*] Скачивание Skyrim Together ({main_str[-1].get('name')})...")
                downloader.download_file(str_url, str_zip, progress_callback=on_dl_progress)
                print()

                # Extract both
                print("[*] Распаковка Address Library...")
                Installer.install_archive(addr_zip, self.game_dir, target_subfolder="Data", version_label="Nexus-AddressLibrary")
                print("[*] Распаковка Skyrim Together Reborn...")
                Installer.install_archive(str_zip, self.game_dir, target_subfolder="Data", version_label="Nexus-STR")

                Installer.fix_address_library_compatibility(self.game_dir)
                print(f"\n{GREEN}{BOLD}[OK] Все моды успешно установлены с Nexus Mods!{RESET}")
            except Exception as e:
                print(f"\n\n{RED}Ошибка Nexus Mods: {e}{RESET}")

        prompt_press_enter()

    # -----------------------------------------------------------------
    # ACTION: UNINSTALL MOD
    # -----------------------------------------------------------------
    def action_uninstall_mod(self):
        clear_screen()
        print_banner()
        print(f"{BOLD}{RED}=== УДАЛЕНИЕ КООП-МОДОВ ==={RESET}\n")

        if not self.game_dir:
            print(f"{RED}Папка игры не указана!{RESET}")
            prompt_press_enter()
            return

        print(f"{YELLOW}Внимание: Будут удалены файлы кооп-мода (Skyrim Together и связанные библиотеки).{RESET}")
        print(f"Оригинальные файлы Skyrim SE, сохранения и настройки затронуты НЕ будут.\n")

        confirm = input(f"{BOLD}Вы действительно хотите удалить кооп-мод? (y/n): {RESET}").strip().lower()
        if confirm not in ("y", "yes", "д", "да"):
            print("Удаление отменено.")
            prompt_press_enter()
            return

        print(f"\n[*] Удаление файлов мода...")
        try:
            count = Installer.uninstall_mod(self.game_dir)
            print(f"\n{GREEN}{BOLD}[OK] Удаление завершено! Удалено файлов: {count}.{RESET}")
            print(f"{GREEN}Ваш Skyrim снова чистый (Vanilla)!{RESET}")
        except Exception as e:
            print(f"\n{RED}Ошибка при удалении: {e}{RESET}")

        prompt_press_enter()

    # -----------------------------------------------------------------
    # ACTION: SETTINGS
    # -----------------------------------------------------------------
    def action_settings(self):
        while True:
            clear_screen()
            print_banner()
            print(f"{BOLD}{CYAN}=== НАСТРОЙКИ ==={RESET}\n")

            current_path = self.config.get("game_path", "Не указан")
            current_port = self.config.get("server_port", 10578)
            current_repo = self.config.get("github_repo", "ameracraft6-max/skyrim-coop-launcher")

            print(f"  {CYAN}[1]{RESET} Папка игры:    {WHITE}{current_path}{RESET}")
            print(f"  {CYAN}[2]{RESET} Автопоиск игры (реестр и Steam)")
            print(f"  {CYAN}[3]{RESET} Порт сервера:  {WHITE}{current_port}{RESET}")
            print(f"  {CYAN}[4]{RESET} Репозиторий:   {WHITE}{current_repo}{RESET}")
            print(f"  {CYAN}[0]{RESET} Назад в главное меню")
            print()

            sub = input(f"{BOLD}Выберите пункт [0-4]: {RESET}").strip()
            if sub == "0":
                break
            elif sub == "1":
                new_p = input(f"\nВведите полный путь к папке со SkyrimSE.exe:\n> ").strip().strip('"')
                if new_p:
                    p = Path(new_p)
                    if (p / "SkyrimSE.exe").exists():
                        self.game_dir = p
                        self.config["game_path"] = str(p)
                        save_config(self.config)
                        print(f"{GREEN}[OK] Путь сохранен!{RESET}")
                    else:
                        print(f"{RED}В указанной папке файл SkyrimSE.exe не найден!{RESET}")
                    time.sleep(1.5)
            elif sub == "2":
                print("\n[*] Автопоиск Skyrim Special Edition...")
                found = find_skyrim_directory()
                if found:
                    self.game_dir = found
                    self.config["game_path"] = str(found)
                    save_config(self.config)
                    print(f"{GREEN}[OK] Найдено: {found}{RESET}")
                else:
                    print(f"{RED}Автоматически найти Skyrim не удалось. Введите путь вручную через [1].{RESET}")
                time.sleep(1.5)
            elif sub == "3":
                port_str = input(f"\nВведите порт сервера (по умолчанию 10578): ").strip()
                if port_str.isdigit():
                    self.config["server_port"] = int(port_str)
                    save_config(self.config)
                    print(f"{GREEN}[OK] Порт сохранен!{RESET}")
                else:
                    print(f"{RED}Порт должен быть числом!{RESET}")
                time.sleep(1.5)
            elif sub == "4":
                repo_str = input(f"\nВведите имя репозитория GitHub (owner/repo): ").strip()
                if repo_str:
                    self.config["github_repo"] = repo_str
                    save_config(self.config)
                    print(f"{GREEN}[OK] Репозиторий сохранен!{RESET}")
                time.sleep(1.5)

def main():
    app = TerminalLauncherApp()
    app.run()

if __name__ == "__main__":
    main()
