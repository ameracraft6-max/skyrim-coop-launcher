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
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def main():
    enable_dpi_awareness()
    from gui import SkyrimLauncherApp
    app = SkyrimLauncherApp()
    app.mainloop()

if __name__ == "__main__":
    main()
