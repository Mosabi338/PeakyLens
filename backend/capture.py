"""Copies the text the user highlighted in ANY app, without losing their clipboard.

Steps (all the Windows pitfalls from the project brief are handled here):
1. Remember what is on the clipboard now.
2. Put a unique marker on the clipboard, so we can tell if the copy really worked.
3. Wait until the user lets go of Ctrl/Alt/Shift/Win (otherwise Ctrl+C becomes
   Ctrl+Alt+C, which does nothing).
4. Simulate Ctrl+C, wait ~150 ms for the other app to fill the clipboard.
5. Read the new text and put the original clipboard text back.
"""
import logging
import sys
import time

import pyperclip
from pynput.keyboard import Controller, Key
from PySide6.QtCore import QThread, Signal

# If the clipboard still holds this after Ctrl+C, nothing was selected.
MARKER = "__peakylens_nothing_copied__"
COPY_DELAY_SECONDS = 0.15  # time the other app needs to update the clipboard

# Windows "virtual key" codes: Shift, Ctrl, Alt, Left Win, Right Win.
MODIFIER_VIRTUAL_KEYS = (0x10, 0x11, 0x12, 0x5B, 0x5C)


def _any_modifier_pressed() -> bool:
    import ctypes  # imported here because windll only exists on Windows

    get_key_state = ctypes.windll.user32.GetAsyncKeyState
    # The highest bit (0x8000) is set while the key is physically held down.
    return any(get_key_state(code) & 0x8000 for code in MODIFIER_VIRTUAL_KEYS)


def wait_for_modifiers_release(timeout_seconds: float = 3.0) -> None:
    if sys.platform != "win32":
        time.sleep(0.3)  # fallback so the file can be imported on other systems
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _any_modifier_pressed():
            break
        time.sleep(0.02)
    time.sleep(0.05)  # tiny settle time after the release


def _read_clipboard() -> str:
    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException:
        return ""


def capture_selected_text() -> str:
    """Return the highlighted text, or "" if nothing was captured."""
    original_clipboard = _read_clipboard()
    try:
        pyperclip.copy(MARKER)
        wait_for_modifiers_release()

        keyboard = Controller()
        with keyboard.pressed(Key.ctrl):  # holds Ctrl while 'c' is tapped
            keyboard.press("c")
            keyboard.release("c")

        time.sleep(COPY_DELAY_SECONDS)
        captured = _read_clipboard()
    finally:
        # Always restore, even if something above failed.
        # Limitation: only TEXT is restored (images/files on the clipboard are lost).
        pyperclip.copy(original_clipboard)

    return "" if captured == MARKER else captured


class CaptureWorker(QThread):
    """Runs the capture off the main thread so the UI never freezes."""

    captured = Signal(str)  # emitted with the text ("" when nothing was selected)

    def run(self) -> None:
        try:
            self.captured.emit(capture_selected_text())
        except Exception:
            logging.exception("Capturing the selection failed")
            self.captured.emit("")


if __name__ == "__main__":
    # Quick self-test:  python -m backend.capture
    print("Highlight some text in another window. Capturing in 4 seconds...")
    time.sleep(4)
    print("Captured:", repr(capture_selected_text()))