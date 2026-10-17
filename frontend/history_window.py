"""History viewer: searchable list on the left, full saved explanation on the right."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)


class HistoryWindow(QWidget):
    def __init__(self, database):
        super().__init__()
        self.setObjectName("ThemedWindow")
        self.setWindowTitle("PeakyLens - History")
        self.resize(900, 560)
        self._database = database

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search snippets and explanations...")
        self.search_box.textChanged.connect(self.refresh)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._show_selected)

        self.detail = QTextBrowser()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.detail)
        splitter.setSizes([300, 600])

        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_box)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.count_label)

    def open_window(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self) -> None:
        rows = self._database.search(self.search_box.text())
        self.list_widget.clear()
        for row in rows:
            first_line = row["snippet"].strip().splitlines()[0][:40] if row["snippet"].strip() else ""
            item = QListWidgetItem(f"{row['created_at']}  [{row['mode']}]\n{first_line}")
            item.setData(Qt.UserRole, dict(row))  # stash the whole row on the item
            self.list_widget.addItem(item)
        self.count_label.setText(f"{len(rows)} result(s)")
        if rows:
            self.list_widget.setCurrentRow(0)
        else:
            self.detail.clear()

    def _show_selected(self, current, _previous) -> None:
        if current is None:
            return
        row = current.data(Qt.UserRole)
        self.detail.setMarkdown(
            f"**Mode:** {row['mode']}  \n**Date:** {row['created_at']}  \n"
            f"**Model:** {row['model'] or 'n/a'}\n\n"
            f"````\n{row['snippet']}\n````\n\n{row['explanation']}"
        )