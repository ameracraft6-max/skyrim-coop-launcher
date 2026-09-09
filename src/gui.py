import os
import sys
import time
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any

import customtkinter as ctk

from config import load_config, save_config, get_app_dir
from game_detector import find_skyrim_directory, inspect_game, get_file_version
from downloader import Downloader, DownloadError
from installer import Installer, InstallError
from server_manager import ServerManager

# Configure CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

COLOR_BG_CARD = "#1c2128"
COLOR_BG_CARD_LIGHT = "#242c38"
COLOR_ACCENT_GOLD = "#e5c07b"
COLOR_ACCENT_BLUE = "#3b82f6"
COLOR_GREEN = "#22c55e"
COLOR_RED = "#ef4444"
COLOR_TEXT_MUTED = "#9ca3af"

class SkyrimLauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Skyrim Together Co-op Launcher")
        self.geometry("860x650")
        self.minsize(800, 580)

        # Set window icon if exists
        icon_path = get_app_dir() / "assets" / "app_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.config = load_config()
        self.downloader = Downloader()
        self.is_busy = False

        # If game_path is not set, try auto-detection
        saved_path = self.config.get("game_path")
        if not saved_path or not Path(saved_path).exists():
            detected = find_skyrim_directory()
            if detected:
                self.game_dir = detected
                self.config["game_path"] = str(detected)
                save_config(self.config)
            else:
                self.game_dir = Path(saved_path) if saved_path else None
        else:
            self.game_dir = Path(saved_path)

        self._build_ui()
        self._refresh_game_status()

    def _build_ui(self):
        # Header banner
        self.header_frame = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=12)
        self.header_frame.pack(fill="x", padx=16, pady=(16, 8))

        header_title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_title_frame.pack(side="left", padx=16, pady=12)

        title_label = ctk.CTkLabel(
            header_title_frame,
            text="⚔ Skyrim Together Reborn",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            header_title_frame,
            text="Единый лаунчер, автоустановщик и сервер для совместной игры",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED
        )
        subtitle_label.pack(anchor="w")

        # Top status badge
        self.status_badge = ctk.CTkLabel(
            self.header_frame,
            text="Проверка игры...",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151",
            text_color="#ffffff",
            corner_radius=8,
            padx=12,
            pady=6
        )
        self.status_badge.pack(side="right", padx=16, pady=12)

        # Tab view
        self.tabview = ctk.CTkTabview(self, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tab_main = self.tabview.add("⚔ Главная (Игра и Мод)")
        self.tab_server = self.tabview.add("🛡 Сервер для друзей")
        self.tab_guide = self.tabview.add("📜 Памятка для игроков")
        self.tab_settings = self.tabview.add("⚙ Настройки")

        self._build_main_tab()
        self._build_server_tab()
        self._build_guide_tab()
        self._build_settings_tab()

    # ----------------------------------------------------
    # TAB 1: MAIN
    # ----------------------------------------------------
    def _build_main_tab(self):
        # Game Path Card
        path_card = ctk.CTkFrame(self.tab_main, fg_color=COLOR_BG_CARD, corner_radius=10)
        path_card.pack(fill="x", padx=10, pady=10)

        path_header = ctk.CTkLabel(
            path_card,
            text="📁 Папка с игрой Skyrim Special Edition:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        path_header.pack(anchor="w", padx=14, pady=(10, 4))

        path_row = ctk.CTkFrame(path_card, fg_color="transparent")
        path_row.pack(fill="x", padx=14, pady=(0, 10))

        self.path_entry = ctk.CTkEntry(
            path_row,
            placeholder_text="Выберите путь к папке Skyrim Special Edition...",
            font=ctk.CTkFont(size=12)
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if self.game_dir:
            self.path_entry.insert(0, str(self.game_dir))

        self.browse_btn = ctk.CTkButton(
            path_row,
            text="Обзор...",
            width=100,
            command=self._on_browse_game_dir
        )
        self.browse_btn.pack(side="right", padx=(0, 4))

        self.autodetect_btn = ctk.CTkButton(
            path_row,
            text="Автопоиск",
            width=100,
            fg_color="#4b5563",
            hover_color="#374151",
            command=self._on_autodetect
        )
        self.autodetect_btn.pack(side="right")

        # Mod Status Card
        self.info_card = ctk.CTkFrame(self.tab_main, fg_color=COLOR_BG_CARD, corner_radius=10)
        self.info_card.pack(fill="x", padx=10, pady=(0, 10))

        self.lbl_game_info = ctk.CTkLabel(
            self.info_card,
            text="Версия SkyrimSE.exe: —",
            font=ctk.CTkFont(size=13)
        )
        self.lbl_game_info.pack(anchor="w", padx=14, pady=(10, 2))

        self.lbl_mod_info = ctk.CTkLabel(
            self.info_card,
            text="Статус мода: —",
            font=ctk.CTkFont(size=13)
        )
        self.lbl_mod_info.pack(anchor="w", padx=14, pady=(0, 2))

        self.lbl_address_lib = ctk.CTkLabel(
            self.info_card,
            text="Address Library: —",
            font=ctk.CTkFont(size=13)
        )
        self.lbl_address_lib.pack(anchor="w", padx=14, pady=(0, 10))

        # Big Action Button Area
        action_card = ctk.CTkFrame(self.tab_main, fg_color=COLOR_BG_CARD, corner_radius=10)
        action_card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.lbl_action_status = ctk.CTkLabel(
            action_card,
            text="Готов к работе",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_action_status.pack(pady=(16, 6))

        self.btn_main_action = ctk.CTkButton(
            action_card,
            text="⬇ Скачать и установить кооп-мод",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=46,
            fg_color=COLOR_ACCENT_BLUE,
            hover_color="#2563eb",
            command=self._on_main_action_clicked
        )
        self.btn_main_action.pack(fill="x", padx=40, pady=(0, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(action_card, height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=40, pady=(0, 12))

        # Bottom Sub-actions
        bottom_btns = ctk.CTkFrame(action_card, fg_color="transparent")
        bottom_btns.pack(fill="x", padx=40, pady=(0, 14))

        self.btn_reinstall = ctk.CTkButton(
            bottom_btns,
            text="🔄 Переустановить / Обновить",
            width=200,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._on_reinstall_clicked
        )
        self.btn_reinstall.pack(side="left")

        self.btn_uninstall = ctk.CTkButton(
            bottom_btns,
            text="🗑 Вернуть чистый Skyrim",
            width=200,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            command=self._on_uninstall_clicked
        )
        self.btn_uninstall.pack(side="right")

    # ----------------------------------------------------
    # TAB 2: SERVER
    # ----------------------------------------------------
    def _build_server_tab(self):
        server_card = ctk.CTkFrame(self.tab_server, fg_color=COLOR_BG_CARD, corner_radius=10)
        server_card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            server_card,
            text="🛡 Локальный сервер для совместной игры",
            font=ctk.CTkFont(size=16, weight="bold")
        ) .pack(anchor="w", padx=16, pady=(16, 6))

        ctk.CTkLabel(
            server_card,
            text="Если вы хотите быть хостом и играть с друзьями, запустите сервер здесь.\nДрузья подключаются к вам по вашему IP адресу (через Radmin VPN или локальную сеть).",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED,
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

        # IP addresses display
        ips_frame = ctk.CTkFrame(server_card, fg_color=COLOR_BG_CARD_LIGHT, corner_radius=8)
        ips_frame.pack(fill="x", padx=16, pady=(0, 14))

        ips = ServerManager.detect_ips()
        radmin_ip = ips.get("radmin") or "Radmin VPN не запущен"
        lan_ip = ips.get("lan") or "127.0.0.1"

        row1 = ctk.CTkFrame(ips_frame, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(row1, text="🌐 Ваш IP в Radmin VPN:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.lbl_radmin_ip = ctk.CTkLabel(row1, text=radmin_ip, font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_ACCENT_GOLD)
        self.lbl_radmin_ip.pack(side="left", padx=10)

        if ips.get("radmin"):
            btn_copy_radmin = ctk.CTkButton(
                row1,
                text="📋 Скопировать для друзей",
                width=180,
                command=lambda: self._copy_to_clipboard(ips.get("radmin"))
            )
            btn_copy_radmin.pack(side="right")

        row2 = ctk.CTkFrame(ips_frame, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkLabel(row2, text="🏠 Локальный IP (для дома):", font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkLabel(row2, text=lan_ip, font=ctk.CTkFont(size=13), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=10)

        btn_copy_lan = ctk.CTkButton(
            row2,
            text="📋 Скопировать",
            width=110,
            fg_color="#4b5563",
            hover_color="#374151",
            command=lambda: self._copy_to_clipboard(lan_ip)
        )
        btn_copy_lan.pack(side="right")

        # Launch Server button
        self.btn_launch_server = ctk.CTkButton(
            server_card,
            text="🛡 Запустить сервер (SkyrimTogetherServer.exe)",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            fg_color="#059669",
            hover_color="#047857",
            command=self._on_launch_server_clicked
        )
        self.btn_launch_server.pack(fill="x", padx=16, pady=(10, 10))

        # Host instructions
        inst_card = ctk.CTkFrame(server_card, fg_color=COLOR_BG_CARD_LIGHT, corner_radius=8)
        inst_card.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        instructions = (
            "📌 Пошаговая инструкция для хоста:\n\n"
            "1. Создайте сеть в Radmin VPN (или Hamachi) и добавьте туда своих друзей.\n"
            "2. Нажмите кнопку «Запустить сервер» выше — откроется черное окно консоли сервера (не закрывайте его во время игры!).\n"
            "3. Нажмите «Скопировать для друзей» и отправьте этот IP адрес в ваш чат.\n"
            "4. Запустите Скайрим через главную кнопку «Играть».\n"
            "5. В игре нажмите F2 (или правый Ctrl) -> Connect -> введите 127.0.0.1 (для хоста) или ваш Radmin IP.\n"
            "6. Ваши друзья вводят ваш Radmin IP и нажимают Connect. Вы в одном мире!"
        )
        ctk.CTkLabel(
            inst_card,
            text=instructions,
            font=ctk.CTkFont(size=12),
            text_color="#d1d5db",
            justify="left"
        ).pack(anchor="nw", padx=14, pady=12)

    # ----------------------------------------------------
    # TAB 3: GUIDE
    # ----------------------------------------------------
    def _build_guide_tab(self):
        scroll_frame = ctk.CTkScrollableFrame(self.tab_guide, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        rules = [
            ("1. Хелген проходить СТРОГО В ОДИНОЧКУ!",
             "Скриптовая повозка и дракон в Хелгене гарантированно ломают мультиплеер. Каждый игрок должен начать новую игру соло, пройти обучение в Хелгене, выйти из пещеры и только потом соединяться с друзьями (например, встретившись у Камней-Хранителей или в Ривервуде)."),
            ("2. Только ОДИН лидер заданий (Party Leader)",
             "После подключения объединитесь в группу (Party). Выберите одного человека лидером. ТОЛЬКО лидер должен начинать диалоги с сюжетными NPC, брать квесты и нажимать рычаги в подземельях, иначе стадии квестов могут разойтись."),
            ("3. Одинаковые файлы у всех игроков",
             "Никаких лишних сторонних модов! У всех участников должны быть установлены одинаковые файлы через этот лаунчер. Если кто-то поставит скриптовые моды, мир рассинхронизируется."),
            ("4. Как вызвать меню подключения в игре",
             "В любой момент в игре нажмите клавишу F2 (на некоторых клавиатурах правый Ctrl). Откроется интерфейс мода со списком игроков, чатом и окном подключения по IP."),
            ("5. Сохранения и перезагрузки",
             "Не используйте быстрое сохранение F5 и быструю загрузку F9 на лету. Сохраняйтесь через обычное меню игры. Если у кого-то игра вылетела — просто запустите снова и переподключитесь через F2.")
        ]

        for title, desc in rules:
            card = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_CARD, corner_radius=10)
            card.pack(fill="x", pady=6)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=COLOR_ACCENT_GOLD
            ).pack(anchor="w", padx=14, pady=(10, 4))

            ctk.CTkLabel(
                card,
                text=desc,
                font=ctk.CTkFont(size=12),
                text_color="#d1d5db",
                justify="left",
                wraplength=760
            ).pack(anchor="w", padx=14, pady=(0, 10))

    # ----------------------------------------------------
    # TAB 4: SETTINGS
    # ----------------------------------------------------
    def _build_settings_tab(self):
        sett_card = ctk.CTkFrame(self.tab_settings, fg_color=COLOR_BG_CARD, corner_radius=10)
        sett_card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            sett_card,
            text="⚙ Настройки источников и ключей",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 12))

        # Nexus API Key Row
        ctk.CTkLabel(
            sett_card,
            text="Nexus Mods Personal API Key (Премиум ключ для загрузки напрямую с Nexus):",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(0, 4))

        nexus_row = ctk.CTkFrame(sett_card, fg_color="transparent")
        nexus_row.pack(fill="x", padx=16, pady=(0, 12))

        self.entry_nexus_key = ctk.CTkEntry(
            nexus_row,
            show="*",
            font=ctk.CTkFont(size=12)
        )
        self.entry_nexus_key.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_nexus_key.insert(0, self.config.get("nexus_api_key", ""))

        self.btn_test_nexus = ctk.CTkButton(
            nexus_row,
            text="Проверить ключ",
            width=140,
            command=self._on_test_nexus_key
        )
        self.btn_test_nexus.pack(side="right")

        self.lbl_nexus_status = ctk.CTkLabel(
            sett_card,
            text="Ключ настроен",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_nexus_status.pack(anchor="w", padx=16, pady=(0, 14))

        # GitHub Repo Row
        ctk.CTkLabel(
            sett_card,
            text="GitHub репозиторий (резервный источник или ваш личный форк):",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(0, 4))

        self.entry_github_repo = ctk.CTkEntry(
            sett_card,
            font=ctk.CTkFont(size=12)
        )
        self.entry_github_repo.pack(fill="x", padx=16, pady=(0, 16))
        self.entry_github_repo.insert(0, self.config.get("github_repo", "SkyrimTogether/SkyrimTogetherReborn"))

        # Bundle Creation Button (For distributing to friends)
        bundle_card = ctk.CTkFrame(sett_card, fg_color=COLOR_BG_CARD_LIGHT, corner_radius=8)
        bundle_card.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            bundle_card,
            text="📦 Создать архив для друзей (Bundle ZIP):",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            bundle_card,
            text="Вы можете собрать все установленные файлы мода в один готовый ZIP-архив, чтобы скинуть друзьям или загрузить в ваш репозиторий на GitHub.",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED,
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        self.btn_create_bundle = ctk.CTkButton(
            bundle_card,
            text="📦 Собрать ZIP-архив для друзей",
            width=240,
            command=self._on_create_bundle_clicked
        )
        self.btn_create_bundle.pack(anchor="w", padx=12, pady=(0, 12))

        # Save settings button
        self.btn_save_settings = ctk.CTkButton(
            sett_card,
            text="💾 Сохранить настройки",
            width=200,
            fg_color="#059669",
            hover_color="#047857",
            command=self._on_save_settings_clicked
        )
        self.btn_save_settings.pack(anchor="w", padx=16, pady=(10, 16))

    # ----------------------------------------------------
    # LOGIC & HANDLERS
    # ----------------------------------------------------
    def _refresh_game_status(self):
        """Inspects game files and updates UI status badges and buttons."""
        if not self.game_dir or not self.game_dir.exists():
            self.status_badge.configure(text="Игра не найдена", fg_color=COLOR_RED)
            self.lbl_game_info.configure(text="Версия SkyrimSE.exe: Не найдена")
            self.lbl_mod_info.configure(text="Статус мода: —")
            self.lbl_address_lib.configure(text="Address Library: —")
            self.btn_main_action.configure(text="Укажите папку с игрой", state="disabled")
            return

        inspection = inspect_game(self.game_dir)
        ver_str = inspection["version"] or "Не определена"

        if inspection["valid"]:
            self.status_badge.configure(text=f"Skyrim SE v{ver_str} (Готов)", fg_color=COLOR_GREEN)
            self.lbl_game_info.configure(text=f"Версия игры: Skyrim SE {ver_str} (Совместима)")
        else:
            self.status_badge.configure(text=f"Skyrim SE v{ver_str} (Внимание)", fg_color="#d97706")
            notes = "; ".join(inspection["notes"])
            self.lbl_game_info.configure(text=f"Версия игры: {ver_str} — {notes}")

        # Address Library status
        if inspection["address_library_installed"]:
            self.lbl_address_lib.configure(text="Address Library: Установлена ✅", text_color=COLOR_GREEN)
        else:
            self.lbl_address_lib.configure(text="Address Library: Не установлена ❌", text_color="#d97706")

        # Mod Status
        if inspection["together_installed"]:
            mod_ver = inspection["together_version"] or "1.8.0"
            self.lbl_mod_info.configure(text=f"Skyrim Together: Установлен ({mod_ver}) ✅", text_color=COLOR_GREEN)
            self.btn_main_action.configure(
                text="⚔ Запустить Skyrim Together",
                state="normal",
                fg_color="#059669",
                hover_color="#047857"
            )
            self.btn_reinstall.configure(state="normal")
            self.btn_uninstall.configure(state="normal")
            self.lbl_action_status.configure(text="Кооп-мод готов к игре!")
        else:
            self.lbl_mod_info.configure(text="Skyrim Together: Не установлен ❌", text_color="#d97706")
            self.btn_main_action.configure(
                text="⬇ Скачать и установить кооп-мод (Nexus/GitHub)",
                state="normal",
                fg_color=COLOR_ACCENT_BLUE,
                hover_color="#2563eb"
            )
            self.btn_reinstall.configure(state="disabled")
            self.btn_uninstall.configure(state="normal")
            self.lbl_action_status.configure(text="Нажмите кнопку для автоматической установки")

    def _on_browse_game_dir(self):
        initial = str(self.game_dir) if self.game_dir else "C:\\"
        selected = filedialog.askdirectory(title="Выберите папку Skyrim Special Edition", initialdir=initial)
        if selected:
            self.game_dir = Path(selected)
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, str(self.game_dir))
            self.config["game_path"] = str(self.game_dir)
            save_config(self.config)
            self._refresh_game_status()

    def _on_autodetect(self):
        detected = find_skyrim_directory()
        if detected:
            self.game_dir = detected
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, str(detected))
            self.config["game_path"] = str(detected)
            save_config(self.config)
            self._refresh_game_status()
            messagebox.showinfo("Успех", f"Игра найдена:\n{detected}")
        else:
            messagebox.showwarning("Поиск", "Не удалось автоматически найти Skyrim SE. Пожалуйста, укажите папку вручную через кнопку «Обзор...».")

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Скопировано", f"IP адрес скопирован в буфер обмена:\n{text}")

    def _on_save_settings_clicked(self):
        self.config["nexus_api_key"] = self.entry_nexus_key.get().strip()
        self.config["github_repo"] = self.entry_github_repo.get().strip()
        save_config(self.config)
        messagebox.showinfo("Сохранено", "Настройки успешно сохранены!")

    def _on_test_nexus_key(self):
        key = self.entry_nexus_key.get().strip()
        self.lbl_nexus_status.configure(text="Проверка ключа...")

        def _test():
            res = Downloader.validate_nexus_key(key)
            if res.get("valid"):
                name = res.get("name")
                prem = "Премиум" if res.get("is_premium") else "Обычный"
                msg = f"Ключ действителен! Пользователь: {name} ({prem})"
                self.after(0, lambda: self.lbl_nexus_status.configure(text=msg, text_color=COLOR_GREEN))
            else:
                err = res.get("error", "Ошибка проверки")
                self.after(0, lambda: self.lbl_nexus_status.configure(text=f"Ошибка: {err}", text_color=COLOR_RED))

        threading.Thread(target=_test, daemon=True).start()

    def _on_main_action_clicked(self):
        inspection = inspect_game(self.game_dir)
        if inspection["together_installed"]:
            self._launch_game(inspection["together_exe"])
        else:
            self._start_installation()

    def _on_reinstall_clicked(self):
        if messagebox.askyesno("Переустановка", "Вы хотите переустановить кооп-мод и обновить все библиотеки?"):
            self._start_installation()

    def _launch_game(self, exe_path_str: Optional[str]):
        if not exe_path_str or not Path(exe_path_str).exists():
            messagebox.showerror("Ошибка", "Исполняемый файл SkyrimTogether.exe не найден!")
            return
        try:
            exe_path = Path(exe_path_str)
            subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
            self.lbl_action_status.configure(text="Игра запущена! Приятного прохождения!")
        except Exception as e:
            messagebox.showerror("Ошибка запуска", f"Не удалось запустить игру:\n{e}")

    def _on_launch_server_clicked(self):
        if not self.game_dir:
            messagebox.showwarning("Внимание", "Сначала укажите папку с игрой!")
            return
        success, msg = ServerManager.launch_server(self.game_dir)
        if success:
            messagebox.showinfo("Сервер запущен", msg)
        else:
            messagebox.showerror("Ошибка сервера", msg)

    def _on_uninstall_clicked(self):
        if not self.game_dir:
            return
        if not messagebox.askyesno("Удаление мода", "Вы уверены, что хотите удалить кооп-мод?\nОригинальные файлы игры и сохранения останутся нетронутыми."):
            return

        def _do_uninstall():
            try:
                count = Installer.uninstall_mod(self.game_dir)
                self.after(0, lambda: [
                    messagebox.showinfo("Удалено", f"Мод удален. Удалено файлов: {count}.\nВанильный Skyrim чист!"),
                    self._refresh_game_status()
                ])
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось удалить: {e}"))

        threading.Thread(target=_do_uninstall, daemon=True).start()

    # ----------------------------------------------------
    # INSTALLATION WORKFLOW
    # ----------------------------------------------------
    def _start_installation(self):
        if self.is_busy:
            return
        if not self.game_dir or not (self.game_dir / "SkyrimSE.exe").exists():
            messagebox.showerror("Ошибка", "Укажите корректную папку со SkyrimSE.exe перед установкой.")
            return

        self.is_busy = True
        self.btn_main_action.configure(state="disabled")
        self.btn_reinstall.configure(state="disabled")
        self.progress_bar.set(0)

        threading.Thread(target=self._installation_worker, daemon=True).start()

    def _update_progress(self, frac: float, text: str):
        self.after(0, lambda: [
            self.progress_bar.set(frac),
            self.lbl_action_status.configure(text=text)
        ])

    def _installation_worker(self):
        temp_dir = get_app_dir() / "temp_downloads"
        temp_dir.mkdir(exist_ok=True)
        api_key = self.config.get("nexus_api_key", "").strip()

        try:
            # 1. Check if we have Nexus API Key
            if api_key:
                self._update_progress(0.05, "Подключение к Nexus Mods API...")
                
                # Fetch Address Library (mod_id 32444)
                self._update_progress(0.1, "Поиск файлов Address Library...")
                addr_files = Downloader.get_nexus_mod_files(api_key, 32444)
                main_addr = [f for f in addr_files if f.get("category_name") == "MAIN"]
                if not main_addr:
                    main_addr = addr_files[-1:]
                addr_file = main_addr[-1]

                self._update_progress(0.15, f"Получение ссылки для Address Library ({addr_file.get('name')})...")
                addr_url = Downloader.get_nexus_download_link(api_key, 32444, addr_file["file_id"])
                if not addr_url:
                    raise DownloadError("Не удалось получить ссылку на Address Library с Nexus.")

                addr_zip = temp_dir / "address_library.zip"
                self._update_progress(0.2, "Скачивание Address Library...")
                self.downloader.download_file(
                    addr_url,
                    addr_zip,
                    progress_callback=lambda f, s, dl, t: self._update_progress(0.2 + f * 0.2, f"Address Library: {t}")
                )

                # Extract Address Library into Data
                self._update_progress(0.42, "Распаковка Address Library...")
                Installer.install_archive(addr_zip, self.game_dir, target_subfolder="Data", version_label=f"AddressLibrary-{addr_file.get('version')}")

                # Fetch Skyrim Together Reborn (mod_id 69993)
                self._update_progress(0.45, "Поиск файлов Skyrim Together Reborn...")
                str_files = Downloader.get_nexus_mod_files(api_key, 69993)
                main_str = [f for f in str_files if f.get("category_name") == "MAIN"]
                if not main_str:
                    main_str = str_files[-1:]
                str_file = main_str[-1]

                self._update_progress(0.5, f"Получение ссылки для Skyrim Together ({str_file.get('name')})...")
                str_url = Downloader.get_nexus_download_link(api_key, 69993, str_file["file_id"])
                if not str_url:
                    raise DownloadError("Не удалось получить ссылку на Skyrim Together с Nexus.")

                str_zip = temp_dir / "skyrim_together_reborn.zip"
                self._update_progress(0.55, "Скачивание Skyrim Together Reborn...")
                self.downloader.download_file(
                    str_url,
                    str_zip,
                    progress_callback=lambda f, s, dl, t: self._update_progress(0.55 + f * 0.35, f"Skyrim Together: {t}")
                )

                # Extract Skyrim Together into Data
                self._update_progress(0.92, "Распаковка Skyrim Together Reborn (через 7-Zip)...")
                Installer.install_archive(str_zip, self.game_dir, target_subfolder="Data", version_label=f"STR-{str_file.get('version')}")

            else:
                # Fallback to GitHub Releases or Bundle
                self._update_progress(0.1, "Поиск последнего релиза на GitHub...")
                repo = self.config.get("github_repo", "SkyrimTogether/SkyrimTogetherReborn")
                rel = Downloader.get_github_latest_release(repo)
                assets = rel.get("assets", [])
                zip_asset = next((a for a in assets if a["name"].endswith(".zip")), None)
                if not zip_asset:
                    raise DownloadError(f"В релизе GitHub {repo} не найден ZIP архив.")

                zip_path = temp_dir / zip_asset["name"]
                self._update_progress(0.2, f"Скачивание {zip_asset['name']} с GitHub...")
                self.downloader.download_file(
                    zip_asset["download_url"],
                    zip_path,
                    progress_callback=lambda f, s, dl, t: self._update_progress(0.2 + f * 0.7, t)
                )

                self._update_progress(0.92, "Распаковка мода в директорию игры...")
                Installer.install_archive(zip_path, self.game_dir, target_subfolder="Data", version_label=rel.get("tag", "github"))

            # Cleanup temp files
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

            self._update_progress(1.0, "Установка успешно завершена!")
            self.after(0, lambda: [
                messagebox.showinfo("Успех!", "Skyrim Together Reborn и Address Library успешно установлены и готовы к игре!"),
                self._refresh_game_status()
            ])

        except Exception as e:
            self._update_progress(0.0, f"Ошибка: {e}")
            self.after(0, lambda: messagebox.showerror("Ошибка установки", str(e)))

        finally:
            self.is_busy = False
            self.after(0, self._refresh_game_status)

    def _on_create_bundle_clicked(self):
        if not self.game_dir:
            return
        inspection = inspect_game(self.game_dir)
        if not inspection["together_installed"]:
            messagebox.showwarning("Внимание", "Сначала установите мод на свой компьютер, чтобы собрать архив для друзей.")
            return

        save_dest = filedialog.asksaveasfilename(
            title="Сохранить архив для друзей",
            defaultextension=".zip",
            filetypes=[("ZIP Archive", "*.zip")],
            initialfile="SkyrimTogether_Friends_Bundle.zip"
        )
        if not save_dest:
            return

        manifest_path = Installer.get_manifest_path(self.game_dir)
        import zipfile
        try:
            with zipfile.ZipFile(save_dest, "w", zipfile.ZIP_DEFLATED) as z:
                if manifest_path.exists():
                    import json
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for rel in data.get("files", []):
                        fp = self.game_dir / rel
                        if fp.exists():
                            z.write(fp, arcname=rel)
                else:
                    # Fallback common files
                    for rel in ["SkyrimTogether.exe", "SkyrimTogetherServer.exe"]:
                        fp = self.game_dir / rel
                        if fp.exists():
                            z.write(fp, arcname=rel)
                    skse_dir = self.game_dir / "Data" / "SKSE"
                    if skse_dir.exists():
                        for root, _, files in os.walk(skse_dir):
                            for file in files:
                                full = Path(root) / file
                                rel = full.relative_to(self.game_dir)
                                z.write(full, arcname=str(rel))

            messagebox.showinfo("Готово!", f"Архив для друзей создан:\n{save_dest}\n\nВы можете скинуть его друзьям или выложить на ваш GitHub!")
        except Exception as e:
            messagebox.showerror("Ошибка создания архива", str(e))
