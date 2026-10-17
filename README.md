# PeakyLens

Tray app for Windows 10/11: highlight code in any app, press a hotkey, get an AI explanation.

## Setup
1. `python -m venv .venv` then `.venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and add your API key(s)
4. `python main.py`

## Hotkeys (changeable in Settings)
- Ctrl+Alt+E: explain highlighted text
- Ctrl+Alt+A: ask a programming question
- Esc / click outside / hotkey again: hide popup

## Known limitations
- Admin apps: a non-admin PeakyLens cannot send Ctrl+C to an app running as administrator. Run PeakyLens as admin too if you need that.
- Only text is restored to the clipboard after capture (images/files are lost).
- Some editors copy the whole line when nothing is selected.
- Ctrl+Alt+key acts as AltGr on some keyboard layouts; change the hotkey in Settings if typing breaks.