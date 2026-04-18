import http.server
import socketserver
import webbrowser
import os
import threading
import time

PORT = 8000
Handler = http.server.SimpleHTTPRequestHandler

def start_server():
    try:
        # すでにポートが使われている場合のエラーを防ぐ設定
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"ローカルサーバーを起動しました。ポート番号: {PORT}")
            print("停止するにはターミナル内で Ctrl+C を押してください。")
            httpd.serve_forever()
    except Exception as e:
        print(f"サーバーの起動中にエラーが発生しました: {e}")

# サーバーを別処理として起動
server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

# サーバーの起動を少し待ってからブラウザを開く
time.sleep(1)

# index.htmlを開く
print("ブラウザでプレビューを開きます...")
webbrowser.open(f"http://localhost:{PORT}")

try:
    # サーバーを維持
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nプレビューを終了しました。")