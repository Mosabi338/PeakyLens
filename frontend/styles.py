"""Dark (and light) theme as a Qt stylesheet (QSS: like CSS, for Qt widgets)."""
from string import Template

PALETTES = {
    "dark": {
        "bg": "#1e1f29", "panel": "#282a36", "border": "#3b3e50", "text": "#e6e6ef",
        "muted": "#9a9db5", "accent": "#7c6cf0", "accent_text": "#ffffff", "code_bg": "#161722",
    },
    "light": {
        "bg": "#fafafc", "panel": "#ffffff", "border": "#d5d7e3", "text": "#22232e",
        "muted": "#6b6e85", "accent": "#5b4bd6", "accent_text": "#ffffff", "code_bg": "#f0f1f7",
    },
}

# $name placeholders are filled in from the palette above.
STYLE_TEMPLATE = Template(
    """
QWidget#PopupRoot { background: transparent; }
QFrame#Card { background: $bg; border: 1px solid $border; border-radius: 12px; }
QWidget#ThemedWindow { background: $bg; }

QLabel { color: $text; background: transparent; }
QLabel#Status, QLabel#Muted { color: $muted; }

QPlainTextEdit, QLineEdit, QListWidget, QKeySequenceEdit, QComboBox {
    background: $panel; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 4px; selection-background-color: $accent;
}
QTextBrowser { background: $panel; color: $text; border: 1px solid $border;
    border-radius: 6px; selection-background-color: $accent; }
QTextBrowser#Explanation { background: transparent; border: none; }
QComboBox QAbstractItemView { background: $panel; color: $text; selection-background-color: $accent; }

QFrame#CodeBlock { background: $code_bg; border: 1px solid $border; border-radius: 8px; }
QFrame#CodeBlock QPlainTextEdit { background: transparent; border: none; }

QPushButton { background: $panel; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 5px 10px; }
QPushButton:hover { border-color: $accent; }
QPushButton#ModeButton { padding: 4px 6px; }
QPushButton#ModeButton:checked, QPushButton#PrimaryButton {
    background: $accent; color: $accent_text; border-color: $accent; }
QPushButton#CopyButton { padding: 2px 8px; font-size: 11px; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QSplitter::handle { background: $border; }
"""
)


def build_stylesheet(theme: str) -> str:
    palette = PALETTES.get(theme, PALETTES["dark"])
    return STYLE_TEMPLATE.substitute(palette)