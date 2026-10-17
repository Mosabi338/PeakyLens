"""Settings window: provider, model, API key, hotkeys, theme and explanation level."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QKeySequenceEdit, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from backend.config import has_api_key, save_api_key, save_config
from backend.hotkeys import is_valid_hotkey

# Nice names shown in the dropdown. The dictionary keys match config["providers"].
PROVIDER_LABELS = {"groq": "Groq", "openrouter": "OpenRouter"}


def _single_chord_editor(combo: str) -> QKeySequenceEdit:
    editor = QKeySequenceEdit(QKeySequence(combo))
    if hasattr(editor, "setMaximumSequenceLength"):  # Qt 6.5+: only one chord allowed
        editor.setMaximumSequenceLength(1)
    return editor


class SettingsWindow(QWidget):
    settings_saved = Signal()

    def __init__(self, config: dict):
        super().__init__()
        self.setObjectName("ThemedWindow")
        self.setWindowTitle("PeakyLens - Settings")
        self.setMinimumWidth(480)
        self._config = config  # the SAME dict main.py uses, so changes apply immediately
        self._models = {}      # model text typed for each provider
        self._new_keys = {}    # API keys typed in this window (not saved until you click Save)
        self._shown_provider = None

        # Provider dropdown: shows "Groq", but remembers the key name "groq" as hidden data.
        self.provider_box = QComboBox()
        for name in config["providers"]:
            self.provider_box.addItem(PROVIDER_LABELS.get(name, name), name)
        self.provider_box.currentIndexChanged.connect(self._on_provider_changed)

        self.model_edit = QLineEdit()

        # API key field: dots instead of letters, with a checkbox to reveal it.
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.show_key_box = QCheckBox("Show key")
        self.show_key_box.toggled.connect(self._toggle_key_visibility)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_key_box)
        self.key_label = QLabel("API key")

        self.level_box = QComboBox()
        self.level_box.addItems(["beginner", "intermediate", "advanced"])
        self.theme_box = QComboBox()
        self.theme_box.addItems(["dark", "light"])
        self.explain_key = _single_chord_editor(config["hotkeys"]["explain"])
        self.ask_key = _single_chord_editor(config["hotkeys"]["ask"])

        form = QFormLayout()
        form.addRow("AI provider", self.provider_box)
        form.addRow("Model name", self.model_edit)
        form.addRow(self.key_label, key_row)
        form.addRow("Explanation level", self.level_box)
        form.addRow("Theme", self.theme_box)
        form.addRow("Explain hotkey", self.explain_key)
        form.addRow("Ask hotkey", self.ask_key)

        self.key_hint = QLabel("")
        self.key_hint.setObjectName("Muted")
        self.key_hint.setWordWrap(True)

        save_button = QPushButton("Save")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._on_save)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.key_hint)
        layout.addLayout(buttons)

    # ---------- opening / loading ----------
    def open_window(self) -> None:
        self._load_from_config()
        self.show()
        self.raise_()
        self.activateWindow()

    def _load_from_config(self) -> None:
        self._models = {name: p["model"] for name, p in self._config["providers"].items()}
        self._new_keys = {}
        self._shown_provider = self._config["provider"]

        self.provider_box.blockSignals(True)  # don't trigger _on_provider_changed yet
        self.provider_box.setCurrentIndex(self.provider_box.findData(self._shown_provider))
        self.provider_box.blockSignals(False)

        self.model_edit.setText(self._models[self._shown_provider])
        self.key_edit.clear()
        self.show_key_box.setChecked(False)
        self._refresh_key_field()

        self.level_box.setCurrentText(self._config["level"])
        self.theme_box.setCurrentText(self._config["theme"])
        self.explain_key.setKeySequence(QKeySequence(self._config["hotkeys"]["explain"]))
        self.ask_key.setKeySequence(QKeySequence(self._config["hotkeys"]["ask"]))

    # ---------- API key field helpers ----------
    def _env_name(self, provider: str) -> str:
        return self._config["providers"][provider]["api_key_env"]

    def _refresh_key_field(self) -> None:
        """Update the label and hint to match the provider that is currently shown."""
        provider = self._shown_provider
        label = PROVIDER_LABELS.get(provider, provider)
        self.key_label.setText(f"{label} API key")
        if has_api_key(self._env_name(provider)):
            self.key_edit.setPlaceholderText("Key saved. Leave empty to keep it")
            self.key_hint.setText(f"A {label} key is already saved. Paste a new one only to replace it.")
        else:
            self.key_edit.setPlaceholderText(f"Paste your {label} API key")
            self.key_hint.setText(f"No {label} key saved yet. Paste it above and click Save.")

    def _toggle_key_visibility(self, visible: bool) -> None:
        mode = QLineEdit.Normal if visible else QLineEdit.Password
        self.key_edit.setEchoMode(mode)

    def _on_provider_changed(self, _index: int) -> None:
        # Remember what was typed for the old provider...
        old = self._shown_provider
        if old:
            self._models[old] = self.model_edit.text().strip()
            typed_key = self.key_edit.text().strip()
            if typed_key:
                self._new_keys[old] = typed_key
            else:
                self._new_keys.pop(old, None)

        # ...then show the stored values for the new one.
        self._shown_provider = self.provider_box.currentData()
        self.model_edit.setText(self._models.get(self._shown_provider, ""))
        self.key_edit.setText(self._new_keys.get(self._shown_provider, ""))
        self._refresh_key_field()

    # ---------- saving ----------
    def _on_save(self) -> None:
        explain = self.explain_key.keySequence().toString(QKeySequence.PortableText)
        ask = self.ask_key.keySequence().toString(QKeySequence.PortableText)

        if not (is_valid_hotkey(explain) and is_valid_hotkey(ask)):
            QMessageBox.warning(self, "Hotkeys", "Both hotkeys must be valid key combinations.")
            return
        if explain == ask:
            QMessageBox.warning(self, "Hotkeys", "The two hotkeys must be different.")
            return

        # Capture the provider that is on screen right now.
        current = self.provider_box.currentData()
        self._models[current] = self.model_edit.text().strip()
        typed_key = self.key_edit.text().strip()
        if typed_key:
            self._new_keys[current] = typed_key

        for name, model in self._models.items():
            if model:
                self._config["providers"][name]["model"] = model

        # Save every key that was typed (into .env and into the running app).
        for name, key in self._new_keys.items():
            save_api_key(self._env_name(name), key)

        self._config["provider"] = current
        self._config["level"] = self.level_box.currentText()
        self._config["theme"] = self.theme_box.currentText()
        self._config["hotkeys"] = {"explain": explain, "ask": ask}

        save_config(self._config)
        self.settings_saved.emit()
        self.close()