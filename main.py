"""Entry point: creates every piece and wires them together.

Flow for the Explain hotkey:
  hotkey (pynput thread) -> signal -> on_explain_hotkey (main thread)
  -> CaptureWorker copies the selection -> on_captured
  -> cache lookup, or AIWorker streams tokens -> popup shows them
  -> on_completed saves the answer to SQLite.
"""
import logging
import sys
import threading

from PySide6.QtCore import QObject, QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.ai_client import AIWorker
from backend.capture import CaptureWorker
from backend.config import active_provider, base_dir, get_api_key, load_config
from backend.database import Database
from backend.hotkeys import HotkeyManager
from backend.prompts import MODE_BUTTON_LABELS, build_system_prompt, build_user_message
from frontend.history_window import HistoryWindow
from frontend.popup import PopupWindow
from frontend.settings_window import SettingsWindow
from frontend.styles import build_stylesheet
from frontend.tray import TrayIcon

CACHEABLE_MODES = set(MODE_BUTTON_LABELS.keys())  # Explain, ELI5, ... (not Ask/Follow-up)


class Controller(QObject):
    """Owns the app state. QObject so hotkey signals are delivered on the main thread."""

    def __init__(self, qt_app: QApplication):
        super().__init__()
        self.qt_app = qt_app
        self.config = load_config()
        self.database = Database(base_dir() / "history.db")

        self.popup = PopupWindow()
        self.history_window = HistoryWindow(self.database)
        self.settings_window = SettingsWindow(self.config)
        self.tray = TrayIcon()
        self.hotkeys = HotkeyManager()

        # Conversation state for the current popup session.
        self.messages = []               # what we send to the AI (system/user/assistant)
        self.request_id = 0              # bumps on every request; stale answers are ignored
        self.current_worker = None
        self.live_workers = []           # keep references until threads finish
        self.capture_worker = None
        self.pending_save = ("", "")     # (text, mode) to store when the answer completes

        self._connect_signals()
        self.apply_theme()
        self.hotkeys.start(self.config["hotkeys"]["explain"], self.config["hotkeys"]["ask"])
        self.tray.show()
        self.tray.showMessage("PeakyLens", "Running in the tray. Highlight code and press "
                              f"{self.config['hotkeys']['explain']}.")

        # First run: no key yet, so open Settings straight away.
        if not get_api_key(self.config):
            self.settings_window.open_window()

    # ---------- wiring ----------
    def _connect_signals(self) -> None:
        self.hotkeys.explain_pressed.connect(self.on_explain_hotkey)
        self.hotkeys.ask_pressed.connect(self.on_ask_hotkey)
        self.hotkeys.outside_click.connect(self.popup.handle_outside_click)
        self.hotkeys.error.connect(self.notify)

        self.popup.rerun_requested.connect(self.on_rerun)
        self.popup.mode_selected.connect(self.on_mode_selected)
        self.popup.followup_requested.connect(self.on_followup)

        self.tray.open_requested.connect(self.on_ask_hotkey)
        self.tray.history_requested.connect(self.history_window.open_window)
        self.tray.settings_requested.connect(self.settings_window.open_window)
        self.tray.quit_requested.connect(self.qt_app.quit)

        self.settings_window.settings_saved.connect(self.on_settings_saved)
        self.qt_app.aboutToQuit.connect(self.shutdown)

    def apply_theme(self) -> None:
        self.qt_app.setStyleSheet(build_stylesheet(self.config["theme"]))

    def notify(self, message: str) -> None:
        self.tray.showMessage("PeakyLens", message)

    # ---------- hotkey handlers ----------
    def on_explain_hotkey(self) -> None:
        if self.popup.isVisible():          # pressing the hotkey again hides the popup
            self.popup.hide_popup()
            return
        if self.capture_worker is not None and self.capture_worker.isRunning():
            return                          # a capture is already in progress
        self.capture_worker = CaptureWorker()
        self.capture_worker.captured.connect(self.on_captured)
        self.capture_worker.start()

    def on_captured(self, text: str) -> None:
        if not text.strip():
            self.reset_session()
            self.popup.show_notice("No text selected")
            return
        self.reset_session()
        self.popup.show_for_snippet(text)
        self.start_explain(text, self.popup.current_mode(), use_cache=True)

    def on_ask_hotkey(self) -> None:
        if self.popup.isVisible():
            self.popup.hide_popup()
            return
        self.reset_session()
        self.popup.show_for_ask()

    # ---------- popup actions ----------
    def on_rerun(self, snippet: str, mode: str) -> None:
        self.start_explain(snippet, mode, use_cache=False)  # Re-run = fresh answer

    def on_mode_selected(self, snippet: str, mode: str) -> None:
        self.start_explain(snippet, mode, use_cache=True)

    def on_followup(self, text: str) -> None:
        self.cancel_current_request()
        if not self.messages:  # first question in Ask mode: start a new conversation
            system_prompt = build_system_prompt("Ask", self.config["level"])
            self.messages = [{"role": "system", "content": system_prompt}]
            save_mode = "Ask"
        else:
            save_mode = "Follow-up"
        self.messages.append({"role": "user", "content": text})
        self.popup.begin_stream(question=text)
        self.start_request(save_text=text, save_mode=save_mode)

    # ---------- AI flow ----------
    def reset_session(self) -> None:
        self.cancel_current_request()
        self.messages = []

    def start_explain(self, snippet: str, mode: str, use_cache: bool) -> None:
        self.cancel_current_request()
        system_prompt = build_system_prompt(mode, self.config["level"])
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(snippet)},
        ]
        self.popup.clear_explanation()

        if use_cache:
            cached = self.database.find_cached(snippet, mode)
            if cached:
                # Keep the saved answer in the conversation so follow-ups have context.
                self.messages.append({"role": "assistant", "content": cached})
                self.popup.show_result(cached)
                return

        self.popup.begin_stream()
        self.start_request(save_text=snippet, save_mode=mode)

    def start_request(self, save_text: str, save_mode: str) -> None:
        self.live_workers = [w for w in self.live_workers if w.isRunning()]
        self.request_id += 1
        self.pending_save = (save_text, save_mode)

        worker = AIWorker(self.request_id, self.config, list(self.messages))
        worker.token_received.connect(self.on_token)
        worker.completed.connect(self.on_completed)
        worker.failed.connect(self.on_failed)
        self.current_worker = worker
        self.live_workers.append(worker)
        worker.start()

    def cancel_current_request(self) -> None:
        if self.current_worker is not None:
            self.current_worker.cancel()
        self.current_worker = None
        self.request_id += 1  # any late signal from the old worker now has a stale id

    def on_token(self, request_id: int, token: str) -> None:
        if request_id == self.request_id:
            self.popup.append_token(token)

    def on_completed(self, request_id: int, full_text: str) -> None:
        if request_id != self.request_id:
            return
        self.messages.append({"role": "assistant", "content": full_text})
        self.popup.finish_stream()

        text, mode = self.pending_save
        if full_text.strip():
            model = active_provider(self.config)["model"]
            self.database.save(text, mode, full_text, model)

    def on_failed(self, request_id: int, message: str) -> None:
        if request_id == self.request_id:
            self.popup.show_error(message)

    # ---------- settings / shutdown ----------
    def on_settings_saved(self) -> None:
        self.apply_theme()
        self.hotkeys.start(self.config["hotkeys"]["explain"], self.config["hotkeys"]["ask"])
        self.notify("Settings saved.")

    def shutdown(self) -> None:
        self.hotkeys.stop()
        for worker in self.live_workers:
            worker.cancel()
            worker.wait(2000)  # give the thread a moment to end cleanly


def install_error_logging() -> None:
    """Log every unhandled error to peakylens.log so nothing fails silently."""
    logging.basicConfig(
        filename=base_dir() / "peakylens.log",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    def log_exception(exc_type, exc_value, exc_traceback):
        logging.error("Unhandled error", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = log_exception
    threading.excepthook = lambda args: log_exception(args.exc_type, args.exc_value, args.exc_traceback)


def main() -> int:
    install_error_logging()
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("PeakyLens")
    qt_app.setQuitOnLastWindowClosed(False)  # tray apps must survive closing windows

    # Single-instance guard: only the first copy can create this shared memory block.
    # Windows frees it automatically when the process ends, even after a crash.
    guard = QSharedMemory("PeakyLensSingleInstanceGuard")
    if not guard.create(1):
        QMessageBox.information(None, "PeakyLens", "PeakyLens is already running (see the tray).")
        return 0

    controller = Controller(qt_app)  # keep a reference so it isn't garbage collected
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())