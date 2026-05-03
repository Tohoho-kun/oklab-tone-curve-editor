import sys
import os
import webbrowser
import threading
import time

def open_browser():
    """サーバー起動後にブラウザを開く"""
    time.sleep(2.0)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    # エラーログの準備
    error_path = os.path.expanduser("~/Desktop/okhsl_error_log.txt")
    
    try:
        # インポートをメイン処理の中に移動（エラーをキャッチするため）
        import uvicorn
        from main import app
        
        # ブラウザ起動スレッドを開始
        threading.Thread(target=open_browser, daemon=True).start()
        
        # FastAPIサーバーを起動
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
        
    except Exception as e:
        # 起動失敗時にデスクトップに詳細なログを残す
        with open(error_path, "w") as f:
            import traceback
            f.write(f"Error during startup: {str(e)}\n")
            f.write("-" * 40 + "\n")
            f.write(traceback.format_exc())
        
        # Windows/Mac 両方でエラーが見えるようにメッセージボックスを出すなどの工夫も可能ですが
        # まずはファイルへの書き出しを確実に行います。
        sys.exit(1)
