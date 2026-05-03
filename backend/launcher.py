import sys
import os
import webbrowser
import uvicorn
import threading
import time
from main import app

def open_browser():
    """サーバー起動後にブラウザを開く"""
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    try:
        # ブラウザ起動スレッドを開始
        threading.Thread(target=open_browser, daemon=True).start()
        
        # FastAPIサーバーを起動
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    except Exception as e:
        # 起動失敗時にデスクトップにログを残す
        error_path = os.path.expanduser("~/Desktop/okhsl_error_log.txt")
        with open(error_path, "w") as f:
            import traceback
            f.write(f"Error during startup: {str(e)}\n")
            f.write(traceback.format_exc())
        sys.exit(1)
