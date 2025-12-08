# Player/lobby_client.py
import sys
import os
import time
import base64
import shutil
import zipfile
import io
import json
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import CLIENT_DOWNLOADS_BASE_DIR 
from client_core import PlayerClientCore

def get_input(prompt):
    return input(prompt).strip()

class LobbyClient:
    def __init__(self):
        self.user_info = None
        self.message = ""
        self.core = PlayerClientCore() # 使用 Player 版核心
        self.msg_buffer = []

    def _handle_network_messages(self, timeout=0.1):
        # 1. 從 Core 撈取新訊息，加入緩衝區
        new_messages = self.core.get_received_message()
        if new_messages:
            self.msg_buffer.extend(new_messages)
        
        # 2. 如果緩衝區是空的，稍微等待
        if not self.msg_buffer:
            time.sleep(timeout)
            return False
            
        # 3. 從緩衝區取出「第一則」訊息處理 (使用 pop(0))
        msg = self.msg_buffer.pop(0)
        
        response_type = msg.get('type')
        success = msg.get('success')
        
        # ... (原本的判斷邏輯保持不變) ...
        if response_type == 'LOGIN_RESPONSE':
            if success:
                self.user_info = msg['data']
                self.message = "登入成功！"
                return 'LOGIN_SUCCESS'
            else:
                self.message = f"登入失敗: {msg.get('message')}"
                return 'LOGIN_FAIL'
        elif response_type == 'REGISTER_RESPONSE':
            self.message = f"註冊結果: {msg.get('message')}"
            return 'REGISTER_DONE'
        elif response_type == 'LOGOUT_RESPONSE':
            self.user_info = None
            return 'LOGOUT_SUCCESS'
        elif response_type == 'GAME_LIST_RESPONSE':
            if success:
                return {'status': 'GAME_LIST_SUCCESS', 'data': msg.get('data')}
            else:
                self.message = "無法取得遊戲列表"
                return {'status': 'GAME_LIST_FAIL'}
        elif response_type == 'DOWNLOAD_RESPONSE':
            if success:
                return {'status': 'DOWNLOAD_SUCCESS', 'data': msg.get('data')}
            else:
                self.message = f"下載失敗: {msg.get('message')}"
                return {'status': 'DOWNLOAD_FAIL'}
        
        # 4. 回傳該訊息 (給其他特定邏輯處理，如 START_GAME, ROOM_INFO 等)
        return msg

    def _get_local_game_version(self, game_name):
        try:
            username = self.user_info['username']
            meta_path = os.path.join(CLIENT_DOWNLOADS_BASE_DIR, username, game_name, 'metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('version')
        except Exception:
            pass
        return None

    def _my_games_menu(self):
        while self.core.is_connected:
            print("\n=== 我的遊戲 (已下載) ===")
            username = self.user_info['username']
            user_dir = os.path.join(CLIENT_DOWNLOADS_BASE_DIR, username)
            
            if not os.path.exists(user_dir):
                print("  (尚未下載任何遊戲)")
                downloaded_games = []
            else:
                downloaded_games = [d for d in os.listdir(user_dir) if os.path.isdir(os.path.join(user_dir, d))]

            for idx, g_name in enumerate(downloaded_games):
                ver = self._get_local_game_version(g_name)
                print(f"  {idx+1}. {g_name} (v{ver})")
            
            print("-" * 30)
            print("請輸入編號選擇遊戲，或 '0' 返回")
            choice = get_input("> ")
            
            if choice == '0': break
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(downloaded_games):
                    game_name = downloaded_games[idx]
                    
                    # === 次級選單 ===
                    print(f"\n>> 已選擇: {game_name}")
                    print("1. 建立房間 (Create Room)")
                    print("2. 評分留言 (Rate & Review)")
                    print("3. 取消 (Cancel)")
                    sub_choice = get_input("> ")
                    
                    if sub_choice == '1':
                        # 原本的建立房間邏輯
                        version = self._get_local_game_version(game_name)
                        print(f">> 請求建立 '{game_name}' 房間...")
                        self.core.send_request("create_room", {"game_name": game_name, "version": version})
                        while True:
                            res = self._handle_network_messages()
                            if not res: continue
                            if res.get('type') == 'ROOM_RESPONSE':
                                if res['success']:
                                    room_id = res.get('data', {}).get('room_id', 'Unknown')
                                    if( room_id == 'Unknown' ):
                                        print(">> 伺服器未回傳房間 ID。")
                                    else:
                                        print(f">> 房間建立成功！ID: {room_id}")
                                        self._wait_in_room()
                                else:
                                    print(f">> 建立失敗: {res['message']}")
                                break
                    
                    elif sub_choice == '2':
                        # === 新增：評分邏輯 ===
                        self._handle_review_ui(game_name)
                    
                else:
                    print("無效編號。")

    def _room_menu(self):
        while self.core.is_connected:
            print("\n=== 房間大廳 ===")
            print("  1. 房間列表 (Room List)")
            print("  2. 邀請列表 (My Invitations)")
            print("  3. 返回 (Back)")
            choice = get_input("> ")
            
            if choice == '3': break
            
            elif choice == '1':
                # 3-1 房間列表
                self.core.send_request("get_room_list")
                # 等待列表回應... (簡化略，邏輯同 P1)
                # 若加入成功 -> self._wait_in_room()
                self._handle_room_list_ui()

            elif choice == '2':
                # 3-2 邀請列表
                self.core.send_request("get_invitations")
                self._handle_invitation_list_ui()

    def _handle_room_list_ui(self):
        """顯示房間列表並處理加入邏輯"""
        print(">> 正在讀取房間列表...")
        
        # 1. 等待 Server 回傳 ROOM_LIST_RESPONSE
        room_list = []
        while self.core.is_connected:
            res = self._handle_network_messages()
            if not res: continue
            
            if isinstance(res, dict) and res.get('type') == 'ROOM_LIST_RESPONSE':
                room_list = res.get('data', [])
                break
            # 處理其他突發訊息 (如登出)
            elif res == 'LOGOUT_SUCCESS': return

        # 2. 顯示列表迴圈
        while True:
            print("\n" + "="*30)
            print("  🏠 房間列表 (Room List)")
            print("="*30)
            
            if not room_list:
                print("  (目前沒有開放的房間)")
            else:
                # data format: [{'id': '1', 'game_name': 'Snake', 'host': 'P1', 'players': 1, 'max': 2}]
                for r in room_list:
                    print(f"  [ID: {r['id']}] {r['game_name']} (Host: {r['host']}) - {r['players']}/{r['max']} 人")
            
            print("-" * 30)
            print("請輸入 [Room ID] 加入房間，或 'b' 返回")
            choice = get_input("> ")
            
            if choice.lower() == 'b':
                break
            
            # 3. 嘗試加入房間
            # 搜尋使用者輸入的 ID 是否存在於列表中
            target_room = next((r for r in room_list if r['id'] == choice), None)
            
            if target_room:
                game_name = target_room['game_name']
                
                # 4. === 關鍵：本地版本檢查 ===
                local_version = self._get_local_game_version(game_name)
                if not local_version:
                    print(f"  [錯誤] 您尚未下載遊戲 '{game_name}'，無法加入。")
                    print("  請先至 '1. 瀏覽商城' 下載遊戲。")
                    input("按 Enter 繼續...")
                    continue
                
                # (Server 端也會檢查版本，但 Client 先檢查可以省一次來回)
                
                # 5. 發送加入請求
                print(f">> 請求加入房間 {choice} (Ver: {local_version})...")
                self.core.send_request("join_room", {
                    "room_id": choice, 
                    "version": local_version
                })
                
                # 6. 等待加入結果
                while self.core.is_connected:
                    res = self._handle_network_messages()
                    if not res: continue
                    
                    if isinstance(res, dict) and res.get('type') == 'ROOM_RESPONSE':
                        if res['success']:
                            print(f">> 加入成功！")
                            self._wait_in_room() # 成功後，切換到等待室畫面
                            return # 離開房間列表選單
                        else:
                            print(f">> 加入失敗: {res.get('message')}")
                            input("按 Enter 繼續...")
                            break # 回到列表顯示
            else:
                print("無效的 Room ID。")

    def _handle_review_ui(self, game_name):
        print(f"\n=== 評論遊戲: {game_name} ===")
        print("(若要取消，請在評分時輸入 '0' 或 'q')")
        while True:
            r_input = get_input("請給予評分 (1-5): ")
            if r_input.lower() in ['0', 'q']:
                print(">> 已取消評論。")
                return
            if r_input.isdigit() and 1 <= int(r_input) <= 5:
                rating = int(r_input)
                break
            print("輸入錯誤，請輸入 1 到 5 的數字。")
            
        comment = get_input("請輸入留言 (可選): ")
        
        self.core.send_request("add_review", {
            "game_name": game_name,
            "rating": rating,
            "comment": comment
        })
        
        print(">> 評論發送中...")
        while self.core.is_connected:
            res = self._handle_network_messages()
            if isinstance(res, dict) and res.get('type') == 'REVIEW_RESPONSE':
                if res['success']:
                    print(f">> {res['message']}")
                else:
                    print(f">> 評論失敗: {res['message']}")
                break
        input("按 Enter 繼續...")

    def _handle_invitation_list_ui(self):
        """顯示邀請列表並處理加入邏輯 (配合 Server 回傳結構化資料版本)"""
        print(">> 正在讀取邀請函...")
        
        # 1. 發送請求並等待 Server 回傳 INVITE_LIST_RESPONSE
        self.core.send_request("get_invitations")
        
        invite_list = []
        while self.core.is_connected:
            res = self._handle_network_messages()
            if not res: continue
            
            if isinstance(res, dict) and res.get('type') == 'INVITE_LIST_RESPONSE':
                invite_list = res.get('data', [])
                break
            # 處理突發登出
            elif res == 'LOGOUT_SUCCESS': return

        # 2. 顯示 UI 互動迴圈
        while True:
            print("\n" + "="*30)
            print("  📩 我的邀請 (Invitations)")
            print("="*30)
            
            if not invite_list:
                print("  (沒有收到任何邀請)")
            else:
                for invite in invite_list:
                    # 預期結構: {'id': '1', 'game_name': 'Snake', 'host': 'Alice'}
                    print(f"  [Room {invite['id']}] {invite['game_name']} (Host: {invite['host']})")
            
            print("-" * 30)
            print("請輸入 [Room ID] 接受邀請，或 'b' 返回")
            choice = get_input("> ")
            
            if choice.lower() == 'b':
                break
                
            # 3. 處理接受邀請
            # 搜尋使用者輸入的 ID 是否在邀請列表中
            target_invite = next((i for i in invite_list if i['id'] == choice), None)
            
            if target_invite:
                game_name = target_invite['game_name']
                
                # 4. === 關鍵：本地版本檢查 ===
                local_version = self._get_local_game_version(game_name)
                
                if not local_version:
                    print(f"  [錯誤] 您尚未下載遊戲 '{game_name}'，無法加入。")
                    print("  請先至 '1. 瀏覽商城' 下載遊戲。")
                    input("按 Enter 繼續...")
                    continue
                
                # 5. 發送加入請求
                print(f">> 接受邀請，正在加入 Room {choice} (Ver: {local_version})...")
                self.core.send_request("join_room", {
                    "room_id": choice, 
                    "version": local_version
                })
                
                # 6. 等待加入結果
                while self.core.is_connected:
                    res = self._handle_network_messages()
                    if not res: continue
                    
                    if isinstance(res, dict) and res.get('type') == 'ROOM_RESPONSE':
                        if res['success']:
                            print(f">> 加入成功！")
                            self._wait_in_room() # 成功後，切換到等待室畫面
                            return # 離開邀請列表選單
                        else:
                            print(f">> 加入失敗: {res.get('message')}")
                            input("按 Enter 繼續...")
                            break # 回到列表顯示
            else:
                print("無效的 Room ID，或該邀請不存在。")

    def _wait_in_room(self):
        """進入房間後的等待迴圈 (修正版)"""
        print("\n>> 進入房間等待室...")
        
        while self.core.is_connected:
            # 1. 輪詢房間狀態
            self.core.send_request("get_room_info")
            
            room_info = None
            start_wait = time.time()
            while time.time() - start_wait < 2:
                res = self._handle_network_messages()
                if isinstance(res, dict) and res.get('type') == 'ROOM_INFO_RESPONSE':
                    room_info = res.get('data')
                    break
                elif res == 'LOGOUT_SUCCESS': return
            
            if not room_info:
                print(">> 房間已關閉或連線錯誤，返回大廳。")
                return

            # === [修正] 遊戲進行中的鎖定邏輯 ===
            if room_info['status'] == 'PLAYING':
                if 'server_ip' in room_info and 'server_port' in room_info:
                    print("\n>> 遊戲開始！正在啟動客戶端...")
                    
                    self._launch_game_client(
                        room_info['game_name'], 
                        room_info['server_ip'], 
                        room_info['server_port']
                    )
                    
                    print(">> (遊戲進行中... 請等待遊戲結束)")
                    
                    # --- 進入鎖定迴圈 ---
                    while self.core.is_connected:
                        time.sleep(1) # 每秒檢查一次
                        self.core.send_request("get_room_info")
                        
                        new_status = None
                        # 等待回應 (最多等 2 秒)
                        poll_end = time.time() + 2
                        while time.time() < poll_end:
                            res = self._handle_network_messages()
                            if isinstance(res, dict) and res.get('type') == 'ROOM_INFO_RESPONSE':
                                if res.get('data'):
                                    new_status = res['data']['status']
                                break
                            elif res == 'LOGOUT_SUCCESS': return
                        
                        # 如果狀態變回 WAITING，代表遊戲結束
                        if new_status == 'WAITING':
                            print("\n>> 遊戲結束，解除鎖定。")
                            break # 跳出鎖定迴圈
                        
                    # 重新開始外層迴圈，以刷新 UI
                    continue 
            # =================================

            # 2. 顯示房間狀態
            print(f"\n=== Room {room_info['id']}: {room_info['game_name']} ===")
            print(f"Host: {room_info['host']}")
            print(f"Players: {len(room_info['players'])}/{room_info['max_players']}")
            for p in room_info['players']:
                role = "(Host)" if p == room_info['host'] else ""
                print(f"  - {p} {role}")
            print("-" * 30)
            
            is_host = (self.user_info['username'] == room_info['host'])
            
            if is_host:
                print("1. 開始遊戲 (Start Game)")
                print("2. 邀請玩家 (Invite)")
                print("3. 離開房間 (Leave)")
                print("(按 Enter 刷新)")
            else:
                print("1. 離開房間 (Leave)")
                print(">>> 房主開始後，請務必按 [Enter] 進入遊戲 <<<")
            
            cmd = input("> ").strip()
            
            if cmd == '1':
                if is_host:
                    print(">> 正在請求伺服器啟動遊戲...")
                    self.core.send_request("start_game")
                    # 這裡不需要等待 START_GAME_RESPONSE，因為外層迴圈會輪詢到 PLAYING
                    # 但為了使用者體驗，可以簡單讀一下回應確認沒報錯
                    t_end = time.time() + 2
                    while time.time() < t_end:
                        res = self._handle_network_messages()
                        if isinstance(res, dict) and res.get('type') == 'START_GAME_RESPONSE':
                            if not res['success']:
                                print(f">> 啟動失敗: {res['message']}")
                            break
                else:
                    self.core.send_request("leave_room")
                    return

            elif cmd == '2' and is_host:
                # === [修正] 邀請玩家：先列出在線用戶 ===
                print(">> 正在獲取在線玩家列表...")
                self.core.send_request("get_online_players")
                
                online_list = []
                while self.core.is_connected:
                    res = self._handle_network_messages()
                    
                    if isinstance(res, dict):
                        if res.get('type') == 'ONLINE_USERS_RESPONSE':
                            online_list = res.get('data', [])
                            break
                        # [新增] 如果收到 ERROR，也要跳出迴圈，不要傻等
                        elif res.get('type') == 'ERROR':
                            print(f">> 獲取列表失敗: {res.get('message')}")
                            break
                            
                    elif res == 'DISCONNECTED': return
                    time.sleep(0.1)

                if not online_list:
                    print("  (目前沒有其他玩家在線)")
                    continue
                
                # 顯示列表
                print("\n=== 在線玩家列表 ===")
                for idx, name in enumerate(online_list):
                    print(f"  {idx+1}. {name}")
                print("-" * 30)

                choice = get_input("請選擇編號或輸入名稱邀請 (輸入 '0' 取消): ")
                if choice == '0': continue
                
                if choice.isdigit() and 0 < int(choice) <= len(online_list):
                    target = online_list[int(choice) - 1]
                else:
                    target = choice # 允許直接輸入不在列表中的名稱

                print(f">> 邀請玩家 ID: {target}")
                self.core.send_request("invite_user", {"target_user": target})
                # ===============================================
            elif cmd == '3': 
                self.core.send_request("leave_room")
                return 
            else:
                pass

    def _login_menu(self):
        while not self.user_info and self.core.is_connected:
            print("\n" + "="*30)
            print("   玩家大廳 - 登入/註冊") 
            print(f"  {self.message}")
            print("-"*30)
            print("1. 登入  2. 註冊  3. 離開")
            choice = get_input("> ")
            
            if choice == '3': return False
            if choice in ['1', '2']:
                u = get_input("帳號: ").strip()
                p = get_input("密碼: ").strip()
                action = "login" if choice == '1' else "register"
                self.core.send_request(action, {"username": u, "password": p})
                
                # 等待回應
                while self.core.is_connected:
                    status = self._handle_network_messages()
                    if status == 'LOGIN_SUCCESS': break
                    
                    if status == 'REGISTER_DONE':
                        print(f">> {self.message}") 
                        break
                        
                    elif status in ('LOGIN_FAIL', 'REGISTER_FAIL', 'DISCONNECTED'):
                        break
        return True

    def _browse_store(self):
        self.message = "正在載入商城..."
        print(f"\n>> {self.message}")
        
        # 1. 發送請求
        self.core.send_request("get_game_list")
        
        # 2. 等待資料
        games_data = {}
        while self.core.is_connected:
            result = self._handle_network_messages()
            # 注意：這裡 result 可能是 dict (成功時) 或字串 (其他狀態)
            if isinstance(result, dict) and result['status'] == 'GAME_LIST_SUCCESS':
                games_data = result['data']
                break
            elif isinstance(result, dict) and result['status'] == 'GAME_LIST_FAIL':
                print("載入失敗。")
                return
            elif result == 'DISCONNECTED':
                return
        
        # 3. 顯示列表迴圈
        while True:
            print("\n" + "="*30)
            print("  🛒 遊戲商城 (Game Store)")
            print("="*30)
            
            # 將字典轉為列表以便用數字選擇
            # games_data = {'Snake': {...}, 'Tetris': {...}}
            game_list = list(games_data.items()) # [('Snake', {...}), ('Tetris', {...})]
            
            if not game_list:
                print("  (目前沒有任何遊戲上架)")
            else:
                for idx, (name, info) in enumerate(game_list):
                    # 顯示格式: 1. Snake (v1.0) - by Alice
                    print(f"  {idx+1}. {name} (v{info.get('version', '?.?')}) - by {info.get('author')}")
            
            print("-" * 30)
            print("請輸入編號查看詳情，或 'b' 返回大廳")
            choice = get_input("> ")
            
            if choice.lower() == 'b':
                break
                
            # 檢查輸入是否為數字且有效
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(game_list):
                    target_game_name = game_list[idx][0]
                    target_game_info = game_list[idx][1]
                    # 進入詳情頁面
                    self._show_game_details(target_game_name, target_game_info)
                else:
                    print("無效的編號。")
            else:
                print("請輸入數字或 'b'。")

    def _handle_download(self, game_name):
        print(f"\n>> 正在下載 '{game_name}' ...")
        self.core.send_request("download_game", {"game_name": game_name})
        
        while self.core.is_connected:
            result = self._handle_network_messages()
            
            if isinstance(result, dict) and result['status'] == 'DOWNLOAD_SUCCESS':
                data = result['data']
                self._save_game_files(data)
                print(f">> 下載完成！版本: {data.get('version')}")
                input("按 Enter 繼續...")
                break
                
            elif isinstance(result, dict) and result['status'] == 'DOWNLOAD_FAIL':
                print(f">> {self.message}")
                input("按 Enter 繼續...")
                break
                
            elif result == 'DISCONNECTED':
                break

    def _save_game_files(self, data):
        """將下載的資料解壓縮到玩家專屬目錄"""
        try:
            game_name = data['game_name']
            version = data['version']
            zip_b64 = data['zip_data']
            username = self.user_info['username']
            
            # 1. 設定目標路徑: client_downloads/{username}/{game_name}
            # 這樣不同玩家登入同一台電腦，檔案也是分開的
            target_dir = os.path.join(CLIENT_DOWNLOADS_BASE_DIR, username, game_name)
            
            # 2. 如果是更新，先清空舊檔案
            if os.path.exists(target_dir):
                print(">> 偵測到舊版本，正在移除...")
                shutil.rmtree(target_dir)
            
            os.makedirs(target_dir, exist_ok=True)
            
            # 3. 解碼並解壓縮
            zip_data = base64.b64decode(zip_b64)
            
            # 使用 io.BytesIO 將二進位資料轉為類似檔案的物件，直接解壓
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                zf.extractall(target_dir)
                
            # 4. (選用) 寫入一個 metadata.json 紀錄目前安裝的版本，方便 P3 啟動時檢查
            import json
            meta_path = os.path.join(target_dir, 'metadata.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "version": version,
                    # === [修改] 儲存 client_cmd ===
                    # "exe_cmd": data.get('exe_cmd'), 
                    "client_cmd": data.get('client_cmd'),
                    # ============================
                    "is_gui": data.get('is_gui')
                }, f)
                
        except Exception as e:
            print(f">> 檔案寫入錯誤: {e}")

    def _show_game_details(self, name, info):
        """顯示單一遊戲詳情 (含評論)"""
        
        # 計算平均評分
        reviews = info.get('reviews', [])
        avg_score = "N/A"
        if reviews:
            total = sum(r.get('rating', 0) for r in reviews)
            avg_score = f"{total / len(reviews):.1f} ⭐"

        while True:
            print("\n" + "*"*40)
            print(f"  遊戲詳情: {name}")
            print("*"*40)
            print(f"  作者: {info.get('author')}")
            print(f"  版本: {info.get('version')}")
            print(f"  類型: {info.get('type')}")
            print(f"  人數: {info.get('min_players')} - {info.get('max_players')} 人")
            print(f"  評分: {avg_score} ({len(reviews)} 則評論)")
            print(f"  上架: {info.get('upload_time')}")
            print("-" * 40)
            print(f"  簡介:\n  {info.get('description')}")
            print("-" * 40)
            print("  [最新評論]")
            if not reviews:
                print("  (尚無評論)")
            else:
                # 只顯示最近 3 則
                for r in reviews[-3:]:
                    print(f"  - {r['user']} ({r['rating']}⭐): {r.get('comment', '')}")
            print("-" * 40)
            print("  1. 下載 / 更新遊戲")
            print("  2. 返回列表")
            
            choice = get_input("> ")
            
            if choice == '2':
                break
            elif choice == '1':
                self._handle_download(name)
            else:
                print("無效的選擇。")

    def _show_history_ui(self):
        print("\n>> 正在讀取對戰紀錄...")
        self.core.send_request("get_history")
        
        history = []
        # 等待 Server 回傳 HISTORY_RESPONSE
        while self.core.is_connected:
            res = self._handle_network_messages()
            if isinstance(res, dict) and res.get('type') == 'HISTORY_RESPONSE':
                history = res.get('data', [])
                break
            elif res == 'LOGOUT_SUCCESS': return

        print("\n" + "="*45)
        print(f"  {self.user_info['username']} 的對戰紀錄")
        print("="*45)
        print(f"  {'時間':<20} | {'遊戲':<15} | {'結果':<6} | {'對手'}")
        print("-" * 45)
        
        if not history:
            print("  (尚無對戰紀錄)")
        else:
            for h in history:
                # 判斷對手是誰 (排除自己)
                opponents = [p for p in h['players'] if p != self.user_info['username']]
                opp_str = ", ".join(opponents) if opponents else "你的對手很神祕"
                
                # 簡單的對齊顯示
                print(f"  {h['timestamp']:<20} | {h['game']:<15} | {h['result']:<6} | {opp_str}")
        
        print("-" * 45)
        input("按 Enter 返回大廳...")

    def _launch_game_client(self, game_name, server_ip, server_port):
        """啟動本地遊戲視窗"""
        print(f"\n>> 正在啟動遊戲 '{game_name}' 連線至 {server_ip}:{server_port} ...")
        
        username = self.user_info['username']
        game_dir = os.path.join(CLIENT_DOWNLOADS_BASE_DIR, username, game_name)
        meta_path = os.path.join(game_dir, 'metadata.json')
        
        try:
            # 1. 讀取啟動指令
            client_cmd = []
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    client_cmd = meta.get('client_cmd', []) # 例如 ["python", "client.py"]

            if not client_cmd:
                print(">> [錯誤] 找不到啟動指令 (metadata.json 損毀或舊版本)")
                return
            
            if client_cmd and client_cmd[0] == 'python':
                client_cmd = list(client_cmd)
                client_cmd[0] = sys.executable

            # 2. 組合完整指令
            # 格式: python client.py --connect IP:PORT --username NAME
            full_cmd = client_cmd + ["--connect", f"{server_ip}:{server_port}", "--username", username]
            
            print(f">> 執行指令: {' '.join(full_cmd)}")

            # 3. 啟動子程序
            # cwd=game_dir 確保遊戲程式能找到它自己的圖片/音效
            subprocess.Popen(full_cmd, cwd=game_dir)
            
            print(">> 遊戲視窗已開啟。")
            
        except Exception as e:
            print(f">> 啟動失敗: {e}")

    def _main_menu(self):
        while self.user_info and self.core.is_connected:
            print(f"\n=== 遊戲大廳: {self.user_info['username']} ===")
            print("1. 瀏覽商城 (Browser)")
            print("2. 我的遊戲 (Library) -> 建立房間 / 評分") # 修改文字
            print("3. 房間 (Room) -> 加入/邀請")
            print("4. 對戰紀錄 (History)") # 新增選項
            print("5. 登出 (Logout)")      # 順延編號
            choice = get_input("> ")
            
            if choice == '5':
                # ... (原本的登出邏輯)
                self.core.send_request("logout", {"username": self.user_info['username']})
                while True:
                    res = self._handle_network_messages()
                    if res == 'LOGOUT_SUCCESS': break
                self.user_info = None
            elif choice == '1':
                self._browse_store()
            elif choice == '2':
                self._my_games_menu()
            elif choice == '3':
                self._room_menu()
            elif choice == '4':
                self._show_history_ui()

    def start(self):
        if self.core.start_connection()[0]:
            while self.core.is_connected:
                if not self.user_info:
                    if not self._login_menu(): break
                else:
                    self._main_menu()
            self.core.disconnect()

if __name__ == '__main__':
    LobbyClient().start()