Running EDHRec as a simple desktop app (Windows / macOS / Linux)

This project is primarily a Flask app with a small UI. The `run_desktop.py` script starts the Flask server on a free localhost port and opens the UI in a native window using pywebview.

Quick start (recommended in a virtualenv):

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_desktop.py
```

macOS / Linux (bash/zsh):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_desktop.py
```

Packaging with PyInstaller (single executable)

1. Install pyinstaller:
   pip install pyinstaller

2. Create a one-file executable (Windows example):
   pyinstaller --noconfirm --onefile --add-data "templates;templates" run_desktop.py

3. Copy any additional data files (like `inventory.csv`) near the generated executable.

Notes & limitations

- The pywebview build will open a native window and run the Flask development server. This is suitable for personal/local use but not a production deployment.
- If your environment blocks outbound connections to edhrec.com, server-side EDHRec calls will fail. See the progress log for errors.
- For professional packaging (auto-updates, code signing, Windows installer) use platform-specific tooling (InnoSetup, electron-builder, or NSIS).

If you want, I can:
- Add a simple `pyinstaller.spec` with data files wired in.
- Create a tiny helper to copy static files into the built exe folder at runtime.
- Provide a script to build a portable ZIP for Windows.

