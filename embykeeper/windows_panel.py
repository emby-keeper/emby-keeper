import ctypes
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

PANEL_URL = "http://127.0.0.1:8000/"


class PanelController:
    def __init__(self):
        self.server = None
        self.thread = None
        self.error = None
        self.stopping = False

    def set_server(self, server):
        self.server = server
        if self.stopping:
            server.should_exit = True

    def start(self):
        self.thread = threading.Thread(target=self._run, name="panel-server")
        self.thread.start()

    def _run(self):
        try:
            from embykeeperapi.app import _run_server
            from embykeeperapi.settings import panel_settings

            config_file = panel_settings.resolved_backend_config_file()
            config_file.parent.mkdir(parents=True, exist_ok=True)
            if not config_file.exists():
                config_file.touch(exist_ok=True)

            _run_server(
                host="127.0.0.1",
                port=8000,
                target_host="127.0.0.1",
                target_port=8001,
                autostart=True,
                reload=False,
                debug=False,
                cors=[],
                server_callback=self.set_server,
            )
        except BaseException as exc:
            self.error = exc

    def is_ready(self):
        return bool(self.server and self.server.started and not self.stopping)

    def open_panel(self):
        if self.is_ready():
            webbrowser.open(PANEL_URL)

    def stop(self):
        self.stopping = True
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive() and self.server:
                self.server.force_exit = True
                self.thread.join(timeout=10)


def _message(text):
    ctypes.windll.user32.MessageBoxW(None, text, "Embykeeper", 0x10)


def _redirect_output():
    if sys.stdout is not None and sys.stderr is not None:
        return
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Embykeeper"
    directory.mkdir(parents=True, exist_ok=True)
    output = (directory / "panel.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or output
    sys.stderr = sys.stderr or output


def main():
    if sys.platform != "win32":
        raise RuntimeError("The tray launcher is only available on Windows")

    _redirect_output()
    if not os.environ.get("EK_WEBPASS") or os.environ.get("EK_WEBPASS") == "your-password":
        _message("Please start Embykeeper using Embykeeper.bat and choose a password.")
        return

    from ctypes import wintypes
    from PIL import Image, ImageDraw
    import pystray
    from embykeeperapi.app import _resolve_static_dir

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, "Local\\EmbykeeperPanel")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        webbrowser.open(PANEL_URL)
        return

    static_dir = _resolve_static_dir()
    icon_path = static_dir / "tray.ico" if static_dir else None
    if icon_path and icon_path.is_file():
        image = Image.open(icon_path)
    else:
        image = Image.new("RGB", (64, 64), "#167c74")
        ImageDraw.Draw(image).text((20, 17), "EK", fill="white")

    controller = PanelController()
    icon = pystray.Icon(
        "embykeeper",
        image,
        "Embykeeper",
        pystray.Menu(
            pystray.MenuItem("Open Embykeeper", lambda: controller.open_panel(), default=True),
            pystray.MenuItem("Exit", lambda tray: tray.stop()),
        ),
    )

    def setup(tray):
        tray.visible = True
        if controller.stopping:
            return
        controller.start()
        deadline = time.monotonic() + 30
        while not controller.stopping and time.monotonic() < deadline and controller.thread.is_alive():
            if controller.is_ready():
                controller.open_panel()
                return
            time.sleep(0.1)
        if controller.stopping:
            return
        _message("The panel could not start. Check port 8000 and the Embykeeper panel log.")
        tray.stop()

    try:
        icon.run(setup=setup)
    finally:
        controller.stop()
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
