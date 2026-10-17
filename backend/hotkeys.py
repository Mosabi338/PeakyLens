"""Global hotkeys (work even when another app has focus) using pynput.

IMPORTANT: pynput runs its own threads. Those threads must NEVER touch widgets.
They only emit Qt signals; Qt then delivers the signal to the main thread safely.
"""
from pynput import keyboard, mouse
from PySide6.QtCore import QObject, Signal

# How we translate the friendly names used in settings into pynput's syntax.
MODIFIERS = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "alt": "<alt>",
    "shift": "<shift>",
    "meta": "<cmd>",
    "win": "<cmd>",
}


def to_pynput_format(combo: str) -> str:
    """Turn 'Ctrl+Alt+E' into '<ctrl>+<alt>+e', the format pynput expects."""
    converted = []
    for part in combo.split("+"):
        name = part.strip().lower()
        if not name:
            continue
        if name in MODIFIERS:
            converted.append(MODIFIERS[name])
        elif len(name) == 1:
            converted.append(name)  # plain letters/digits stay as they are
        else:
            converted.append(f"<{name}>")  # special keys such as <f5> or <esc>
    return "+".join(converted)


def is_valid_hotkey(combo: str) -> bool:
    try:
        keyboard.HotKey.parse(to_pynput_format(combo))
        return bool(combo.strip())
    except (ValueError, KeyError):
        return False


class HotkeyManager(QObject):
    explain_pressed = Signal()
    ask_pressed = Signal()
    outside_click = Signal()  # any mouse click anywhere (the popup decides if it was "outside")
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._hotkey_listener = None
        self._mouse_listener = None

    def start(self, explain_combo: str, ask_combo: str) -> None:
        """(Re)start listening. Safe to call again after the user changes settings."""
        self.stop()
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(
                {
                    to_pynput_format(explain_combo): self._on_explain,
                    to_pynput_format(ask_combo): self._on_ask,
                }
            )
            self._hotkey_listener.start()
        except Exception as exc:  # bad combo, or the OS refused the hook
            self.error.emit(f"Could not register the hotkeys: {exc}")

        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()

    def stop(self) -> None:
        for listener in (self._hotkey_listener, self._mouse_listener):
            if listener is not None:
                listener.stop()
        self._hotkey_listener = None
        self._mouse_listener = None

    # These run on pynput's threads: emit a signal and return immediately.
    def _on_explain(self) -> None:
        self.explain_pressed.emit()

    def _on_ask(self) -> None:
        self.ask_pressed.emit()

    def _on_click(self, x, y, button, pressed) -> None:
        if pressed:
            self.outside_click.emit()


if __name__ == "__main__":
    # Quick self-test:  python -m backend.hotkeys   (press Ctrl+Alt+E / Ctrl+Alt+A)
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication([])
    manager = HotkeyManager()
    manager.explain_pressed.connect(lambda: print("Explain hotkey pressed"))
    manager.ask_pressed.connect(lambda: print("Ask hotkey pressed"))
    manager.error.connect(print)
    manager.start("Ctrl+Alt+E", "Ctrl+Alt+A")
    print("Listening... press the hotkeys. Press Ctrl+C in the terminal to stop.")
    app.exec()