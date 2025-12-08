import sys
import os
import subprocess
import time
import platform

# 設定顏色 (Windows 可能需要 colorama，這裡用簡單的 ANSI)
def print_header(text):
    print("\n" + "="*40)
    print(f"   {text}")
    print("="*40)

def open_new_console(script_path):
    """跨平台開啟新終端機執行腳本"""
    if platform.system() == 'Windows':
        # Windows: 使用 start cmd /k 來開啟新視窗並保持開啟
        subprocess.Popen(['start', 'cmd', '/k', sys.executable, script_path], shell=True)
    elif platform.system() == 'Darwin': # macOS
        # macOS: 使用 open -a Terminal
        cmd = f'"{python_exe}" "{script_path}"'
        
        # 處理雙引號跳脫 (Escape quotes for AppleScript)
        safe_cmd = cmd.replace('"', '\\"')
        
        # 呼叫 AppleScript
        subprocess.Popen(['osascript', '-e', f'tell application "Terminal" to do script "{safe_cmd}"'])
    else: # Linux
        # Linux: 嘗試 x-terminal-emulator 或 gnome-terminal
        try:
            subprocess.Popen(['x-terminal-emulator', '-e', f'{sys.executable} {script_path}'])
        except:
            subprocess.Popen([sys.executable, script_path])

def main_menu():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 確保子模組可以 import 根目錄的 config.py, utils.py
    os.environ['PYTHONPATH'] = base_dir

    while True:
        print_header("Game Store 測試選單")
        print("1. [Dev]    啟動開發者客戶端 (Developer Client)")
        print("2. [Player] 啟動玩家大廳 (Lobby Client)")
        print("3. [Info]   顯示測試遊戲路徑 (給上傳用)")
        print("4. 離開")
        
        choice = input("\n請選擇功能 (1-4): ").strip()
            
        if choice == '1':
            print(">> 正在新視窗啟動 Developer Client...")
            script = os.path.join(base_dir, 'Client', 'developer_client.py')
            open_new_console(script)
            
        elif choice == '2':
            print(">> 正在新視窗啟動 Lobby Client...")
            script = os.path.join(base_dir, 'Client', 'lobby_client.py')
            open_new_console(script)
            
        elif choice == '3':
            print_header("測試遊戲路徑")
            games_dir = os.path.join(base_dir, 'Test_Games')
            print(f"根目錄: {games_dir}")
            print("-" * 30)
            if os.path.exists(games_dir):
                for game in os.listdir(games_dir):
                    full_path = os.path.join(games_dir, game)
                    if os.path.isdir(full_path):
                        print(f"📁 {game:<20} -> {full_path}")
            else:
                print("(Test_Games 資料夾不存在，請確認部署)")
            print("-" * 30)
            print("提示：在 Developer Client 上傳時，請複製貼上完整的路徑。")
            input("\n按 Enter 返回選單...")
            
        elif choice == '4':
            print("Bye!")
            break
        else:
            print("無效輸入，請重試。")

if __name__ == '__main__':
    main_menu()