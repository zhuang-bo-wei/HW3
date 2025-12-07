import time
import sys
import os
import json
import shutil
import base64
import tempfile
# 取得目前檔案 (t2.py) 的絕對路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得上一層目錄 (project_root)
parent_dir = os.path.dirname(current_dir)
# 將上一層目錄加入系統搜尋路徑
sys.path.append(parent_dir)
from client_core import DeveloperClientCore
from config import SERVER_HOST, DEVELOPER_PORT

# 輔助函式：確保輸入有效
def get_input(prompt, required=True):
    while True:
        try:
            user_input = input(prompt).strip()
            
            if required and not user_input:
                print("輸入不能為空，請重新輸入。")
                continue
            return user_input
        except EOFError:
            print("\n輸入中斷。")
            return None
        except Exception:
            # 處理終端機異常，特別是隱藏輸入
            return input(prompt).strip()

class DeveloperClient:
    def __init__(self):
        self.user_info = None  # 儲存登入成功的開發者資訊
        self.message = ""      # 用於顯示系統訊息
        
        # 網路核心
        self.core = DeveloperClientCore()

    def _fetch_and_list_games(self, action_name=""):
        """
        向 Server 請求已上架遊戲列表，顯示給使用者，並回傳 {name: info} 字典。
        如果 action_name 不為空，則在標題中顯示。
        """
        if action_name:
             print(f"\n>> 正在讀取您的遊戲列表 ({action_name})...")
        else:
             print(f"\n>> 正在讀取您的遊戲列表...")
             
        self.core.send_request("get_uploaded_games")
        
        my_games = {}
        while self.core.is_connected:
            res = self._handle_network_messages()
            if isinstance(res, dict) and res.get('status') == 'GAME_LIST_SUCCESS':
                my_games = res.get('data', {})
                break
            elif res == 'DISCONNECTED' or res == 'GAME_LIST_FAIL':
                self.message = f"無法取得列表: {self.message}"
                return None
            time.sleep(0.1)
        
        # 顯示列表 (作為主儀表板或操作選擇清單)
        game_names = list(my_games.keys())
        print(f"\n{'編號':<6} | {'遊戲名稱':<20} | {'目前版本'}")
        print("-" * 40)
        if not my_games:
            print("  (您尚未上架任何遊戲)")
        else:
            for i, name in enumerate(game_names):
                ver = my_games[name].get('version', 'N/A')
                print(f"{i+1:<6} | {name:<20} | {ver}")
        print("-" * 40)
        
        return my_games

    # --- 上傳遊戲邏輯 ---
    def _handle_upload(self):
        print("\n=== 上傳遊戲 ===")
        # 1. 輸入路徑
        path = get_input("請輸入遊戲專案資料夾路徑 (例如 games/Snake): ")
        
        if not os.path.exists(path) or not os.path.isdir(path):
            self.message = "錯誤：路徑不存在或不是資料夾。"
            return

        # 2. 驗證 game_config.json 是否存在
        config_path = os.path.join(path, "game_config.json")
        if not os.path.exists(config_path):
            self.message = "錯誤：資料夾內缺少 game_config.json 設定檔。"
            return

        try:
            # 3. 讀取設定檔
            with open(config_path, 'r', encoding='utf-8') as f:
                game_config = json.load(f)
            
            print(f"正在打包遊戲: {game_config.get('game_name')} (v{game_config.get('version')})...")

            # 4. 壓縮與編碼
            # 建立一個暫存的 zip 檔
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                tmp_zip_path = tmp_file.name
            
            # 壓縮資料夾 (shutil.make_archive 不需要副檔名)
            shutil.make_archive(tmp_zip_path.replace('.zip', ''), 'zip', path)
            
            # 讀取 ZIP 並轉為 Base64
            with open(tmp_zip_path, 'rb') as f:
                zip_data = f.read()
                zip_b64 = base64.b64encode(zip_data).decode('utf-8')
            
            # 刪除暫存檔
            os.remove(tmp_zip_path)

            # 5. 發送請求
            payload = {
                "game_config": game_config,
                "zip_data": zip_b64
            }
            
            self.core.send_request("upload_game", payload)
            
            # === [修正點] 手動印出訊息，不要只存到 self.message ===
            print(">> 上傳請求已發送，正在傳輸資料... (請稍候)") 
            
            # 6. 等待回應
            while self.core.is_connected:
                status = self._handle_network_messages()
                if status == 'UPLOAD_SUCCESS':
                    print(f">> 成功: {self.message}") # 印出成功訊息
                    return
                elif status == 'UPLOAD_FAIL':
                    print(f">> 失敗: {self.message}") # 印出失敗訊息
                    return
                elif status == 'DISCONNECTED':
                    return
                time.sleep(0.1)

        except Exception as e:
            print(f"上傳過程發生錯誤: {e}")

    def _handle_update(self):
        # 1. 取得並顯示列表，讓使用者選擇
        my_games = self._fetch_and_list_games("更新")
        if not my_games:
            return

        game_names = list(my_games.keys())
        choice = get_input("請選擇要更新的遊戲編號 (輸入 '0' 取消): ")
        if choice == '0': return
        
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(game_names):
            print("無效的選擇。")
            return
            
        target_game_name = game_names[int(choice)-1]
        current_version = my_games[target_game_name].get('version')
        print(f"\n>> 您選擇更新: {target_game_name} (目前 v{current_version})")

        # 2. 輸入新路徑並驗證 (後續邏輯不變)
        path = get_input("請輸入 [新版本] 遊戲專案資料夾路徑: ")
        
        # 完整的邏輯請從原本的 _handle_update 複製過來，確保從這裡開始執行：
        if not os.path.exists(path) or not os.path.isdir(path):
            self.message = "錯誤：路徑不存在或不是資料夾。"
            print(f">> {self.message}")
            return
        
        config_path = os.path.join(path, "game_config.json")
        if not os.path.exists(config_path):
            print(">> 錯誤：資料夾內缺少 game_config.json 設定檔。")
            return

        try:
            # 讀取並檢查設定檔
            with open(config_path, 'r', encoding='utf-8') as f:
                game_config = json.load(f)
            
            new_name = game_config.get('game_name')
            new_version = game_config.get('version')

            # 檢查 1: 名稱是否相符
            if new_name != target_game_name:
                print(f"\n[錯誤] 名稱不符！")
                print(f"  您選擇更新: {target_game_name}")
                print(f"  設定檔名稱: {new_name}")
                print("  請確認您選對了遊戲，或是修改 config 檔。")
                return

            # 檢查 2: 版本是否有變 (防止誤傳舊版)
            if new_version == current_version:
                print(f"\n[警告] 新版本號 ({new_version}) 與伺服器上的版本相同。")
                print("  這可能導致玩家無法收到更新通知。")
                confirm = get_input("  是否仍要強制覆蓋? (y/N): ", required=False)
                if confirm.lower() != 'y':
                    print(">> 已取消更新。")
                    return

            print(f">> 準備上傳: {new_name} v{new_version}")

            # 5. 打包與上傳 (同原邏輯)
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                tmp_zip_path = tmp_file.name
            
            shutil.make_archive(tmp_zip_path.replace('.zip', ''), 'zip', path)
            
            with open(tmp_zip_path, 'rb') as f:
                zip_data = f.read()
                zip_b64 = base64.b64encode(zip_data).decode('utf-8')
            
            os.remove(tmp_zip_path)

            payload = {
                "game_config": game_config,
                "zip_data": zip_b64
            }
            
            self.core.send_request("update_game", payload)
            print(">> 更新請求已發送，正在傳輸資料... (請稍候)")
            
            while self.core.is_connected:
                status = self._handle_network_messages()
                if status == 'UPDATE_SUCCESS':
                    print(f">> 成功: {self.message}")
                    return
                elif status == 'UPDATE_FAIL':
                    print(f">> 失敗: {self.message}")
                    return
                elif status == 'DISCONNECTED':
                    return
                time.sleep(0.1)

        except Exception as e:
            print(f"更新過程發生錯誤: {e}")

    def _handle_delete(self):
        print("\n=== 下架遊戲 (Delete Game) ===")
        print("警告：此操作將永久刪除遊戲檔案與紀錄。")
        
        # 1. 取得並顯示列表，讓使用者選擇
        my_games = self._fetch_and_list_games("下架")
        if not my_games:
            return

        game_names = list(my_games.keys())
        choice = get_input("請選擇要下架的遊戲編號 (輸入 '0' 取消): ")
        if choice == '0': return
        
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(game_names):
            print("無效的選擇。")
            return
            
        game_name_to_delete = game_names[int(choice)-1]
        
        # 2. 確認與發送請求 (後續邏輯不變)
        confirm = get_input(f"確認要刪除 '{game_name_to_delete}' 嗎? (y/N): ", required=False)
        if confirm.lower() != 'y':
            self.message = "已取消下架操作。"
            return

        self.core.send_request("delete_game", {"game_name": game_name_to_delete})

        print(f">> 請求下架 {game_name_to_delete} 已發送...")
        
        # 3. 等待回應
        while self.core.is_connected:
            status = self._handle_network_messages()
            if status == 'DELETE_SUCCESS':
                print(f">> 成功: {self.message}")
                return
            elif status == 'DELETE_FAIL':
                print(f">> 失敗: {self.message}")
                return
            elif status == 'DISCONNECTED':
                return
            time.sleep(0.1)

    def _handle_network_messages(self, timeout=0.1):
        """檢查並處理來自 ClientCore 的佇列訊息"""
        messages = self.core.get_received_message()
        if not messages:
            # 讓 CPU 稍微休息，避免在迴圈中全速執行
            time.sleep(timeout)
            return False

        for msg in messages:
            response_type = msg.get('type')
            success = msg.get('success', False)
            
            # 處理連線中斷
            if response_type == 'SERVER_DISCONNECTED':
                self.message = f"\n[錯誤] 連線中斷: {msg.get('message', '與伺服器失去連線')}"
                self.user_info = None # 清除登入狀態
                return 'DISCONNECTED'
            
            # 處理登入/註冊回應 (用於登入/註冊流程)
            elif response_type == 'LOGIN_RESPONSE':
                if success:
                    self.user_info = msg['data']
                    self.message = " 登入成功！"
                    return 'LOGIN_SUCCESS'
                else:
                    self.message = f" 登入失敗: {msg.get('message', '未知錯誤')}"
                    return 'LOGIN_FAIL'
                    
            elif response_type == 'REGISTER_RESPONSE':
                if success:
                    self.message = f" 註冊成功: {msg.get('message', '請使用此帳號登入。')}"
                    return 'REGISTER_SUCCESS'
                else:
                    self.message = f" 註冊失敗: {msg.get('message', '未知錯誤')}"
                    return 'REGISTER_FAIL'
            
            # 處理登出回應 (用於主選單流程)
            elif response_type == 'LOGOUT_RESPONSE':
                if success:
                    self.user_info = None
                    self.message = " 登出成功！"
                    return 'LOGOUT_SUCCESS'
                else:
                    self.message = f" 登出失敗: {msg.get('message', '未知錯誤')}"
                    return 'LOGOUT_FAIL'
            
            # === 新增：上傳回應 ===
            elif response_type == 'UPLOAD_RESPONSE':
                if success:
                    self.message = f" 上傳成功！ {msg.get('message', '')}"
                    return 'UPLOAD_SUCCESS'
                else:
                    self.message = f" 上傳失敗: {msg.get('message', '未知錯誤')}"
                    return 'UPLOAD_FAIL'
            
            elif response_type == 'GAME_LIST_RESPONSE':
                if success:
                    return {'status': 'GAME_LIST_SUCCESS', 'data': msg.get('data')}
                else:
                    self.message = "無法取得遊戲列表"
                    return 'GAME_LIST_FAIL'
            
            elif response_type == 'UPDATE_RESPONSE':
                if success:
                    self.message = f" 更新成功！ {msg.get('message', '')}"
                    return 'UPDATE_SUCCESS'
                else:
                    self.message = f" 更新失敗: {msg.get('message', '未知錯誤')}"
                    return 'UPDATE_FAIL'
            
            elif response_type == 'DELETE_RESPONSE':
                if success:
                    self.message = f" 下架成功！ {msg.get('message', '')}"
                    return 'DELETE_SUCCESS'
                else:
                    self.message = f" 下架失敗: {msg.get('message', '未知錯誤')}"
                    return 'DELETE_FAIL'
            
            
                    
            # 處理其他未處理的訊息
            else:
                 self.message = f"[伺服器回應] {response_type}: {msg}"
                 return 'UNHANDLED_MESSAGE'
                 
        return True # 處理完畢

    # --- CLI 互動方法 ---

    def _cli_login_register(self):
        """處理登入/註冊介面"""
        while not self.user_info and self.core.is_connected:
            print("\n" + "="*30)
            print("  開發者平台 - 登入/註冊")
            print(f"  {self.message}")
            print("-"*30)
            print("1. 登入  2. 註冊  3. 離開 ")

            
            choice = get_input("請選擇功能 (1-3): ")

            if choice == '3':
                return False # 離開

            if choice in ['1', '2']:
                username = get_input("  帳號: ")
                password = get_input("  密碼: ")
                username = username.strip()
                password = password.strip()  #去掉空白
                if choice == '1':
                    self.core.send_request("login", {"username": username, "password": password})
                    self.message = "登入請求已發送..."
                    
                    # 等待回應
                    while self.core.is_connected:
                        status = self._handle_network_messages()
                        if status == 'LOGIN_SUCCESS':
                            return True # 登入成功，進入主選單
                        elif status in ('LOGIN_FAIL', 'DISCONNECTED'):
                            break
                        time.sleep(0.1) # 避免 CPU 佔用過高
                        
                elif choice == '2':
                    self.core.send_request("register", {"username": username, "password": password})
                    self.message = "註冊請求已發送..."
                    
                    # 等待回應
                    while self.core.is_connected:
                        status = self._handle_network_messages()
                        if status in ('REGISTER_SUCCESS', 'REGISTER_FAIL', 'DISCONNECTED'):
                            break
                        time.sleep(0.1)
                        
            else:
                self.message = "無效的選擇，請重新輸入。"
        
        return self.user_info is not None # 返回登入狀態
        

    def _cli_developer_main_menu(self):
        """處理開發者主選單 (Dashboard 風格)"""
        while self.user_info and self.core.is_connected:
            username = self.user_info.get('username', '開發者')
            
            # 1. 取得並顯示遊戲列表 (儀表板視圖)
            self._fetch_and_list_games()
            
            print("\n" + "="*30)
            print(f"   歡迎您，{username}")
            print(f"  {self.message}")
            print("="*30)
            print("1. 上傳新遊戲 (Upload New)")
            print("2. 更新遊戲 (Update Existing)")
            print("3. 刪除遊戲 (Delete)")
            print("4. 登出")
            
            choice = get_input("請選擇功能 (1-4): ")

            if choice == '4':
                self.core.send_request("logout", {"username": username})
                # ... (登出邏輯保持不變) ...
                while self.core.is_connected:
                    status = self._handle_network_messages()
                    if status == 'LOGOUT_SUCCESS':
                        return
                    elif status == 'DISCONNECTED':
                        return
                    time.sleep(0.1)
            elif choice == '1':
                self._handle_upload()
            elif choice == '2':
                self._handle_update() # 進入更新流程
            elif choice == '3':
                self._handle_delete() # 進入刪除流程
            else:
                self.message = "無效的選擇，請重新輸入。"

    # --- 啟動與主迴圈 ---
    
    def start(self):
        print("Starting Developer Client...")
        
        # 1. 嘗試連線
        success, message = self.core.start_connection()
        if not success:
            print(f"Fatal error: {message}")
            return
            
        # 2. 主迴圈：在連線存在時執行
        while self.core.is_connected:
            if not self.user_info:
                # 未登入狀態：進入登入/註冊介面
                if not self._cli_login_register():
                    # 選擇離開
                    break
            else:
                # 已登入狀態：進入主選單
                self._cli_developer_main_menu()
                
        # 3. 結束
        self.core.disconnect()
        print("Client exited.")


if __name__ == '__main__':
    # 執行前的檔案結構提醒：
    # 確保 config.py 和 utils.py 可被導入 
    
    dev_client = DeveloperClient()
    dev_client.start()