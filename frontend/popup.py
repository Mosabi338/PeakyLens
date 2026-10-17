"""The small frameless popup that shows near the mouse cursor.

This file is only the VIEW: it shows things and emits signals when the user
does something. The logic (calling the AI, saving history) lives in main.py.
"""
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from backend.prompts import MODE_BUTTON_LABELS

# Finds ```language\ncode``` blocks inside the AI's Markdown answer.
CODE_BLOCK_PATTERN = re.compile(r"```[ \t]*([\w+#.\-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def monospace_font(size: int = 10) -> QFont:
    font = QFont("Consolas", size)
    font.setStyleHint(QFont.Monospace)  # fall back to any monospace font
    return font


def split_markdown(markdown: str) -> list:
    """Split text into [("text", str), ("code", (language, code)), ...] in order."""
    pieces = []
    position = 0
    for match in CODE_BLOCK_PATTERN.finditer(markdown):
        before = markdown[position:match.start()]
        if before.strip():
            pieces.append(("text", before))
        pieces.append(("code", (match.group(1), match.group(2).rstrip("\n"))))
        position = match.end()
    rest = markdown[position:]
    if rest.strip():
        pieces.append(("text", rest))
    return pieces


class AutoHeightBrowser(QTextBrowser):
    """A Markdown viewer that grows to fit its text (so the parent scrolls, not this)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Explanation")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)

    def set_markdown_text(self, markdown: str) -> None:
        self.setMarkdown(markdown)
        self.fit_height()

    def fit_height(self) -> None:
        width = self.viewport().width() or 440
        self.document().setTextWidth(width)
        self.setFixedHeight(int(self.document().size().height()) + 8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_height()  # width changed, so wrapped text height changes too


class CodeBlock(QFrame):
    """One code block: language label, Copy button and read-only monospace text."""

    def __init__(self, code: str, language: str):
        super().__init__()
        self.setObjectName("CodeBlock")
        self._code = code

        label = QLabel(language or "code")
        label.setObjectName("Muted")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("CopyButton")
        self.copy_button.clicked.connect(self.copy_code)

        header = QHBoxLayout()
        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(self.copy_button)

        editor = QPlainTextEdit(code)
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        editor.setFont(monospace_font(10))
        visible_lines = min(code.count("\n") + 1, 14)  # taller blocks scroll inside
        editor.setFixedHeight(visible_lines * editor.fontMetrics().lineSpacing() + 34)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(editor)

    def copy_code(self) -> None:
        QGuiApplication.clipboard().setText(self._code)
        self.copy_button.setText("Copied")
        QTimer.singleShot(1200, lambda: self.copy_button.setText("Copy"))


class ExplanationView(QStackedWidget):
    """Shows the AI answer.

    Page 0 (while streaming): one simple Markdown viewer, updated every ~80 ms.
    Page 1 (when finished):   Markdown text pieces + code blocks with Copy buttons.
    """

    def __init__(self):
        super().__init__()
        self._markdown = ""   # last finished answer (used by Export and follow-ups)
        self._base = ""       # text shown before the streaming answer (earlier Q&A)
        self._buffer = ""     # tokens received so far
        self._streaming = False

        self._stream_view = QTextBrowser()
        self._stream_view.setObjectName("Explanation")
        self.addWidget(self._stream_view)

        self._segments = QWidget()
        self._segment_layout = QVBoxLayout(self._segments)
        self._segment_layout.setContentsMargins(0, 0, 4, 0)
        self._segment_layout.setSpacing(8)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._segments)
        self.addWidget(self._scroll)

        # Updating the viewer on EVERY token would feel jittery; batch the updates.
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(80)
        self._flush_timer.timeout.connect(self._flush)

    def current_markdown(self) -> str:
        return self._markdown

    def clear(self) -> None:
        self._markdown = ""
        self._base = ""
        self._buffer = ""
        self._streaming = False
        self._flush_timer.stop()
        self._stream_view.clear()
        self.setCurrentWidget(self._stream_view)

    def begin_stream(self, prefix_markdown: str = "") -> None:
        self._streaming = True
        self._base = prefix_markdown
        self._buffer = ""
        self._stream_view.setMarkdown(prefix_markdown)
        self.setCurrentWidget(self._stream_view)

    def append_token(self, token: str) -> None:
        self._buffer += token
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush(self) -> None:
        self._stream_view.setMarkdown(self._base + self._buffer)
        bar = self._stream_view.verticalScrollBar()
        bar.setValue(bar.maximum())  # keep the newest text visible

    def finish_stream(self) -> None:
        self._flush_timer.stop()
        self.show_markdown(self._base + self._buffer)

    def show_error(self, message: str) -> None:
        partial = (self._base + self._buffer) if self._streaming else self._markdown
        self.show_markdown(f"{partial}\n\n> ⚠️ {message}", remember=False)

    def show_markdown(self, markdown: str, remember: bool = True) -> None:
        self._streaming = False
        self._flush_timer.stop()
        if remember:
            self._markdown = markdown
        self._clear_segments()
        for kind, content in split_markdown(markdown):
            if kind == "text":
                browser = AutoHeightBrowser()
                browser.set_markdown_text(content)
                self._segment_layout.addWidget(browser)
            else:
                language, code = content
                self._segment_layout.addWidget(CodeBlock(code, language))
        self._segment_layout.addStretch(1)
        self.setCurrentWidget(self._scroll)

    def _clear_segments(self) -> None:
        while self._segment_layout.count():
            item = self._segment_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()


class PopupWindow(QWidget):
    rerun_requested = Signal(str, str)    # (snippet, mode): "Re-run" button
    mode_selected = Signal(str, str)      # (snippet, mode): a mode button was clicked
    followup_requested = Signal(str)      # text typed in the bottom box

    def __init__(self):
        super().__init__()
        self.setObjectName("PopupRoot")
        # Tool = no taskbar button, Frameless = no title bar, StaysOnTop = above other apps.
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)  # lets the card have rounded corners
        self.setFixedSize(540, 480)
        self._ignore_outside_clicks = False
        self._build_ui()

    # ---------- building the layout ----------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)  # room for the drop shadow

        card = QFrame()
        card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 140))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1) Captured snippet (editable) + Re-run
        self.snippet_row = QWidget()
        snippet_layout = QHBoxLayout(self.snippet_row)
        snippet_layout.setContentsMargins(0, 0, 0, 0)
        self.snippet_edit = QPlainTextEdit()
        self.snippet_edit.setFont(monospace_font(10))
        self.snippet_edit.setPlaceholderText("Captured code appears here (you can edit it)")
        self.snippet_edit.setFixedHeight(84)
        self.rerun_button = QPushButton("Re-run")
        self.rerun_button.clicked.connect(self._on_rerun)
        snippet_layout.addWidget(self.snippet_edit, 1)
        snippet_layout.addWidget(self.rerun_button, 0, Qt.AlignTop)
        layout.addWidget(self.snippet_row)

        # 2) Mode buttons
        self.mode_row = QWidget()
        mode_layout = QHBoxLayout(self.mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(4)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for mode, label in MODE_BUTTON_LABELS.items():
            button = QPushButton(label)
            button.setObjectName("ModeButton")
            button.setCheckable(True)
            button.setProperty("mode", mode)  # remember which mode this button stands for
            self._mode_group.addButton(button)
            mode_layout.addWidget(button)
        self._mode_group.buttons()[0].setChecked(True)
        self._mode_group.buttonClicked.connect(self._on_mode_clicked)
        layout.addWidget(self.mode_row)

        # 3) Explanation
        self.explanation = ExplanationView()
        layout.addWidget(self.explanation, 1)

        # 4) Status + export
        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.export_button = QPushButton("Export .md")
        self.export_button.clicked.connect(self.export_markdown)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.export_button)
        layout.addLayout(status_row)

        # 5) Follow-up / question input
        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask a follow-up...")
        self.input_box.returnPressed.connect(self._on_send)
        send_button = QPushButton("Ask")
        send_button.setObjectName("PrimaryButton")
        send_button.clicked.connect(self._on_send)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(send_button)
        layout.addLayout(input_row)

    # ---------- reading state ----------
    def current_mode(self) -> str:
        return self._mode_group.checkedButton().property("mode")

    def snippet_text(self) -> str:
        return self.snippet_edit.toPlainText().strip()

    # ---------- showing / hiding ----------
    def show_for_snippet(self, snippet: str) -> None:
        self._set_ask_layout(False)
        self.snippet_edit.setPlainText(snippet)
        self.explanation.clear()
        self.set_status("")
        self._show_at_cursor()

    def show_for_ask(self) -> None:
        self._set_ask_layout(True)
        self.snippet_edit.clear()
        self.explanation.clear()
        self.set_status("")
        self._show_at_cursor()

    def show_notice(self, message: str) -> None:
        """Used for 'No text selected'."""
        self._set_ask_layout(False)
        self.snippet_edit.clear()
        self.explanation.show_markdown(f"> {message}", remember=False)
        self.set_status("")
        self._show_at_cursor()

    def _set_ask_layout(self, ask_mode: bool) -> None:
        # In 'Ask' mode there is no snippet and no mode buttons, only the question box.
        self.snippet_row.setVisible(not ask_mode)
        self.mode_row.setVisible(not ask_mode)
        self.input_box.setPlaceholderText(
            "Ask any programming question..." if ask_mode else "Ask a follow-up..."
        )

    def _show_at_cursor(self) -> None:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()

        x = cursor.x() + 16
        y = cursor.y() + 16
        if y + self.height() > area.bottom():   # no room below: open above the cursor
            y = cursor.y() - self.height() - 16
        # Final clamp guarantees the popup never leaves the screen.
        x = max(area.left(), min(x, area.right() - self.width()))
        y = max(area.top(), min(y, area.bottom() - self.height()))

        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_box.setFocus()

    def hide_popup(self) -> None:
        self.hide()

    def handle_outside_click(self) -> None:
        """Called for every global mouse click; hides the popup if the click was outside it."""
        if not self.isVisible() or self._ignore_outside_clicks:
            return
        if QApplication.activePopupWidget() is not None:
            return
        if not self.frameGeometry().contains(QCursor.pos()):
            self.hide_popup()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide_popup()
        else:
            super().keyPressEvent(event)

    # ---------- streaming API used by main.py ----------
    def clear_explanation(self) -> None:
        self.explanation.clear()

    def begin_stream(self, question: str = None) -> None:
        """Start a new answer. With `question`, keep the earlier answers above it."""
        prefix = ""
        if question is not None:
            existing = self.explanation.current_markdown()
            prefix = f"**You:** {question}\n\n"
            if existing:
                prefix = existing + "\n\n---\n\n" + prefix
        self.explanation.begin_stream(prefix)
        self.set_status("Thinking...")

    def append_token(self, token: str) -> None:
        self.explanation.append_token(token)

    def finish_stream(self) -> None:
        self.explanation.finish_stream()
        self.set_status("")

    def show_result(self, markdown: str) -> None:
        self.explanation.show_markdown(markdown)
        self.set_status("Loaded from saved history (no API call)")

    def show_error(self, message: str) -> None:
        self.explanation.show_error(message)
        self.set_status("")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    # ---------- user actions ----------
    def _on_rerun(self) -> None:
        snippet = self.snippet_text()
        if snippet:
            self.rerun_requested.emit(snippet, self.current_mode())

    def _on_mode_clicked(self, _button) -> None:
        snippet = self.snippet_text()
        if snippet:
            self.mode_selected.emit(snippet, self.current_mode())

    def _on_send(self) -> None:
        text = self.input_box.text().strip()
        if text:
            self.input_box.clear()
            self.followup_requested.emit(text)

    def export_markdown(self) -> None:
        explanation = self.explanation.current_markdown()
        if not explanation:
            self.set_status("Nothing to export yet")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = str(Path.home() / f"peakylens-note-{stamp}.md")

        # While the file dialog is open, clicks in it must not hide the popup.
        self._ignore_outside_clicks = True
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save explanation", default_name, "Markdown (*.md)"
            )
        finally:
            self._ignore_outside_clicks = False
        if not path:
            return

        note = (
            f"# PeakyLens note\n\n"
            f"*{datetime.now():%Y-%m-%d %H:%M}*\n\n"
            f"## Code\n\n````\n{self.snippet_text()}\n````\n\n"
            f"## Explanation\n\n{explanation}\n"
        )
        Path(path).write_text(note, encoding="utf-8")
        self.set_status(f"Saved {Path(path).name}")


if __name__ == "__main__":
    # Visual self-test from the project folder:  python -m frontend.popup
    import sys
    from frontend.styles import build_stylesheet

    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet("dark"))
    popup = PopupWindow()
    popup.show_for_snippet("for i, name in enumerate(names):\n    print(i, name)")

    demo = "`enumerate()` pairs each item with its index.\n\n```python\nfor i, x in enumerate('ab'):\n    print(i, x)\n```\n\n- Starts at 0 by default."
    popup.begin_stream()
    chunks = [demo[i:i + 6] for i in range(0, len(demo), 6)]

    def feed():
        if chunks:
            popup.append_token(chunks.pop(0))
            QTimer.singleShot(30, feed)
        else:
            popup.finish_stream()

    feed()
    sys.exit(app.exec())