"""
Desktop launcher using pywebview that starts the Flask app and opens a native window.
Run: python run_desktop.py

Packaging hint (Windows):
  pip install pyinstaller
  pyinstaller --noconfirm --onefile --add-data "templates;templates" run_desktop.py

This script tries to import the app from api.py and start it on a free localhost port
then opens a pywebview window pointing at the local server.
"""
import socket
import threading
import time
import sys

# Prefer requests for health checks; fall back to urllib
try:
    import requests
except Exception:
    requests = None

# Import the Flask app from the project
try:
    import api
    flask_app = api.app
except Exception as e:
    print("Failed to import Flask app from api.py:", e)
    raise

# optional import of pywebview (may be missing in some builds)
try:
    import webview
except Exception:
    webview = None


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    addr, port = s.getsockname()
    s.close()
    return port


def start_flask(port: int):
    # Start Flask development server in a thread (use_reloader=False)
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    return flask_thread


def wait_until_up(url, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests:
                r = requests.get(url, timeout=1.0)
                if r.status_code < 500:
                    return True
            else:
                import urllib.request
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status < 500:
                        return True
        except Exception:
            time.sleep(0.1)
    return False


if __name__ == '__main__':
    port = find_free_port()
    url = f'http://127.0.0.1:{port}/'
    print('Starting Flask server on', url)
    start_flask(port)
    print('Waiting for server to become ready...')
    ok = wait_until_up(url, timeout=15.0)
    if not ok:
        print('Server did not become ready in time; see logs for errors')
        sys.exit(1)

    if webview is None:
        print('\nWARNING: The native GUI backend (pywebview) is not available in this build.')
        print('Falling back to opening the default web browser. This avoids requiring pywebview to be bundled.')
        try:
            import webbrowser
            webbrowser.open(url)
            print('Opened default browser at', url)
            print('Press Ctrl+C in this console to stop the server and exit.')
            # Keep the main thread alive while the Flask server runs in background
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print('Interrupted by user, exiting.')
                sys.exit(0)
        except Exception as e:
            print('Failed to open the system browser:', e)
            print('Run the app in Python instead: python run_desktop.py')
            sys.exit(1)

    print('Opening native window...')
    # Create a webview window pointing to the local server
    webview.create_window('EDHRec Deck Builder', url, width=900, height=720)
    webview.start()

    print('Webview closed; exiting')
    sys.exit(0)

