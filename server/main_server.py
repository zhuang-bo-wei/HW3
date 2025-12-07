# Server/main_server.py
import threading
import time
import sys
import os

# --- 路徑設定 ---
# 取得目前檔案 (main_server.py) 的目錄路徑 (即 Server/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得專案根目錄 (GameStore_Final/)
project_root = os.path.dirname(current_dir)
# 將專案根目錄加入 Python 搜尋路徑，確保能找到 config.py, db_manager.py
if project_root not in sys.path:
    sys.path.append(project_root)

# --- 導入模組 ---
# [修正] 改用直接導入，因為它們在同一層目錄
from developer_server import DeveloperServer
from lobby_server import LobbyServer

def main():
    print("=== Game Store Server Manager ===")
    
    # 1. 初始化 Developer Server
    print("Initializing Developer Server...")
    dev_server = DeveloperServer()
    
    dev_thread = threading.Thread(target=dev_server.start, daemon=True)
    dev_thread.start()

    # 3. 初始化並啟動 Lobby Server
    print("Initializing Lobby Server...")
    

    lobby_server = LobbyServer()
    lobby_thread = threading.Thread(target=lobby_server.start, daemon=True)
    lobby_thread.start()

    print("\nServers are running!")
    print("Type 'stop' or 'exit' to shut down the servers.\n")

    try:
        while True:
            command = input()
            if command.strip().lower() in ['stop', 'exit', 'quit']:
                print("Stopping servers...")
                break
            elif command.strip().lower() == 'status':
                print(f"Developer Server: Running")
                print(f"Logged in Developers: {list(dev_server.logged_in_developers.keys())}")
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nForce stopping...")

    # 5. 關閉伺服器
    dev_server.stop()
    lobby_server.stop()
    
    dev_thread.join(timeout=1)
    lobby_thread.join(timeout=1)

    print("All servers stopped successfully.")

if __name__ == '__main__':
    main()