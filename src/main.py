import os
import sys
import ctypes
from pathlib import Path

# Add src to sys.path so local imports work seamlessly
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

def enable_dpi_awareness():
    """Enables crisp per-monitor DPI scaling on Windows 10/11."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def main():
    enable_dpi_awareness()
    if "--gui" in sys.argv:
        try:
            from gui import SkyrimLauncherApp
            app = SkyrimLauncherApp()
            app.mainloop()
            return
        except Exception as e:
            print(f"Не удалось запустить GUI: {e}. Переключение на консоль...")

    from terminal_app import TerminalLauncherApp
    app = TerminalLauncherApp()
    app.run()

if __name__ == "__main__":
    main()
