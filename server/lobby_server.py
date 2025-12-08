# Server/lobby_server.py
import socket
import threading
import sys
import os
import base64
import uuid
import subprocess
import json
import time
import zipfile
import traceback

# 路徑設定 (與 developer_server.py 相同)
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import SERVER_HOST, LOBBY_PORT, UPLOADED_GAMES_DIR
from utils import send_message, receive_message
from db_manager import db_manager

class LobbyServer:
    def __init__(self):
        self.host = SERVER_HOST
        self.port = LOBBY_PORT
        self.server_socket = None
        self.is_running = False
        self.logged_in_players = {} # 記錄線上玩家
        self.rooms = {} # {room_id: {info...}}
        self.invitations = {} # {username: [room_id_1, room_id_2]}
        self.active_game_servers = {} # {room_id: subprocess.Popen}

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10) 
            self.is_running = True
            print(f"Lobby Server listening on {self.host}:{self.port}...")
            
            while self.is_running:
                try:
                    client_sock, client_addr = self.server_socket.accept()
                    handler = threading.Thread(
                        target=self.handle_client, 
                        args=(client_sock, client_addr)
                    )
                    handler.daemon = True
                    handler.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"Lobby accept error: {e}")
                    break
        except Exception as e:
            print(f"Failed to start Lobby Server: {e}")
            self.is_running = False

    def stop(self):
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        print("Lobby Server stopped.")

    def handle_client(self, client_sock, client_addr):
        """處理單一 Client 連線的線程邏輯 (Debug 版)"""
        current_user = None
        print(f"[Debug] Client 連線成功: {client_addr}")  # <--- 新增：顯示連線來源

        while self.is_running:
            try:
                # 接收封包
                request = receive_message(client_sock)
                
                # 1. 檢查是否斷線
                if request is None:
                    print(f"[Debug] Client {client_addr} 主動斷線或傳輸中斷 (收到 None)")
                    break

                # 2. 印出收到的內容 (這就是您要的)
                print(f"[Debug] 收到來自 {client_addr} 的封包: {request}") 

                action = request.get('action')
                data = request.get('data', {})
                
                # 處理請求
                response = self.route_request(action, data, current_user, client_sock)
                
                # 3. 印出 Server 回傳的內容
                print(f"[Debug] 回傳給 {client_addr}: {response}")

                # 處理登入/登出狀態
                if action == 'login' and response.get('success'):
                    current_user = data.get('username')
                elif action == 'logout' and response.get('success'):
                    current_user = None

                # 發送回應
                send_message(client_sock, response)
            
            except Exception as e:
                # 4. 捕捉並印出所有錯誤 (關鍵！)
                print(f"[Error] 處理 Client {client_addr} 時發生錯誤: {e}")
                print("--- 錯誤追蹤 (Traceback) ---")
                traceback.print_exc()
                print("---------------------------")
                break
        
        # 清理連線
        if current_user and current_user in self.logged_in_players:
            del self.logged_in_players[current_user]
        client_sock.close()
        print(f"[Debug] 與 {client_addr} 的連線已關閉")


    def route_request(self, action, data, current_user, client_sock):
        if action == 'register':
            return self._handle_register(data)
        elif action == 'login':
            return self._handle_login(data, client_sock)
            
        if not current_user:
            return {'type': 'ERROR', 'success': False, 'message': 'Please log in first.'}
            
        if action == 'logout':
            return self._handle_logout(data)
        
        elif action == 'get_game_list':
            return self._handle_get_game_list()
        elif action == 'download_game':
            return self._handle_download_game(data)
        elif action == 'create_room':
            return self._handle_create_room(data, current_user)
        elif action == 'get_room_list':
            return self._handle_get_room_list()
        elif action == 'join_room':
            return self._handle_join_room(data, current_user)
        elif action == 'leave_room':
            return self._handle_leave_room(current_user)
        elif action == 'get_room_info':
            return self._handle_get_room_info(current_user)
        elif action == 'invite_user':
            return self._handle_invite_user(data, current_user)
        elif action == 'get_invitations':
            return self._handle_get_invitations(current_user)
        elif action == 'start_game':
            return self._handle_start_game(current_user)
        elif action == 'get_history':
            return self._handle_get_history(current_user)
        elif action == 'add_review':
            return self._handle_add_review(data, current_user)
        elif action == 'get_online_players': 
            return self._handle_get_online_players(current_user)
        
        return {'type': 'ERROR', 'success': False, 'message': f'Unknown action: {action}'}

    # --- 業務邏輯 (針對 players) ---

    def _handle_register(self, data):
        # 注意 user_type 是 'players'
        success, res = db_manager.add_user(data.get('username'), data.get('password'), 'players')
        if success:
            return {'type': 'REGISTER_RESPONSE', 'success': True, 'data': {'username': data.get('username')}}
        return {'type': 'REGISTER_RESPONSE', 'success': False, 'message': res}

    def _handle_login(self, data, client_sock):
        username = data.get('username')
        password = data.get('password')

        if username in self.logged_in_players:
            return {'type': 'LOGIN_RESPONSE', 'success': False, 'message': 'Already logged in.'}
            
        # 1. 驗證帳密
        success, user_data = db_manager.authenticate_user(username, password, 'players')
        
        if success:
            # 2. 記錄連線
            print(f"User {username} log in successfully.")
            self.logged_in_players[username] = client_sock
            
            # 3. [安全版] 建立全新的回應字典，絕對不要修改 user_data
            response_data = {
                "username": username,
                # 使用 .get() 防止 play_history 不存在時報錯
                "play_history": user_data.get('play_history', [])
            }
                
            return {'type': 'LOGIN_RESPONSE', 'success': True, 'data': response_data}
            
        return {'type': 'LOGIN_RESPONSE', 'success': False, 'message': user_data}

    def _handle_logout(self, data):
        username = data.get('username')
        room_id = self._get_player_room_id(username)
        if room_id:
            self._handle_leave_room(username)
        if username in self.logged_in_players:
            del self.logged_in_players[username]
        return {'type': 'LOGOUT_RESPONSE', 'success': True}

    def _handle_get_game_list(self):
        """P1 回傳所有遊戲資料"""
        # 直接從 db_manager 取得完整字典
        games = db_manager.get_all_games()
        
        # 這裡直接回傳整個 games 字典
        # 實務上如果資料量大，通常會只回傳簡表 (ID, Name, Author)，詳情再另外查
        # 但為了作業簡單，我們一次回傳全部
        return {'type': 'GAME_LIST_RESPONSE', 'success': True, 'data': games}
    
    def _handle_download_game(self, data):
        """P2 處理下載請求"""
        game_name = data.get('game_name')
        
        # 1. 查詢遊戲資訊
        game_info = db_manager.game_data.get(game_name)
        if not game_info:
            return {'type': 'DOWNLOAD_RESPONSE', 'success': False, 'message': 'Game not found.'}
            
        version = game_info.get('version') # 假設扁平化結構
        
        # 2. 組合檔案路徑
        # server_data/uploaded_games/{game_name}/{version}.zip
        file_path = os.path.join(UPLOADED_GAMES_DIR, game_name, f"{version}.zip")
        
        if not os.path.exists(file_path):
            return {'type': 'DOWNLOAD_RESPONSE', 'success': False, 'message': 'Game file missing on server.'}
            
        try:
            # 3. 讀取檔案並轉 Base64
            with open(file_path, 'rb') as f:
                zip_data = f.read()
                zip_b64 = base64.b64encode(zip_data).decode('utf-8')
                
            return {
                'type': 'DOWNLOAD_RESPONSE', 
                'success': True, 
                'data': {
                    'game_name': game_name,
                    'version': version,
                    'zip_data': zip_b64,
                    'client_cmd': game_info.get('client_cmd'), 
                    'is_gui': game_info.get('is_gui')
                }
            }
        except Exception as e:
            print(f"Download error: {e}")
            return {'type': 'DOWNLOAD_RESPONSE', 'success': False, 'message': f'Server error: {e}'}
        
    def _handle_create_room(self, data, current_user):
        game_name = data.get('game_name')
        client_version = data.get('version')
        
        # 1. 檢查玩家是否已經在房間內
        if self._get_player_room_id(current_user):
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'You are already in a room.'}

        # 2. 檢查遊戲與版本 (Server-side Version Check)
        game_info = db_manager.game_data.get(game_name)
        if not game_info:
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Game not found.'}
        
        # 強制要求最新版本
        if game_info.get('version') != client_version:
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': f'Version mismatch. Server: {game_info.get("version")}, Yours: {client_version}. Please update.'}

        # 3. 建立房間
        room_id = str(len(self.rooms) + 1) # 簡單用數字當 ID，實務可用 uuid
        self.rooms[room_id] = {
            "id": room_id,
            "host": current_user,
            "game_name": game_name,
            "version": client_version,
            "max_players": game_info.get('max_players', 2),
            "players": [current_user],
            "status": "WAITING" # WAITING, PLAYING
        }
        
        print(f"Room created: {room_id} by {current_user} ({game_name})")
        return {'type': 'ROOM_RESPONSE', 'success': True, 'data': {'room_id': room_id}}

    def _handle_get_room_list(self):
        # 回傳簡化的房間列表
        room_list = []
        for r_id, r in self.rooms.items():
            if r['status'] == 'WAITING':
                room_list.append({
                    "id": r_id, 
                    "game_name": r['game_name'], 
                    "host": r['host'], 
                    "players": len(r['players']), 
                    "max": r['max_players']
                })
        return {'type': 'ROOM_LIST_RESPONSE', 'success': True, 'data': room_list}

    def _handle_join_room(self, data, current_user):
        room_id = data.get('room_id')
        client_version = data.get('version')

        # 1. 檢查玩家狀態
        if self._get_player_room_id(current_user):
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Already in a room.'}
            
        # 2. 檢查房間是否存在
        room = self.rooms.get(room_id)
        if not room:
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Room not found.'}
            
        if room['status'] != 'WAITING':
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Game already started.'}
            
        if len(room['players']) >= room['max_players']:
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Room is full.'}

        # 3. 檢查版本 (進房玩家也必須是最新版)
        if room['version'] != client_version:
             return {'type': 'ROOM_RESPONSE', 'success': False, 'message': f'Version mismatch. Room: {room["version"]}, Yours: {client_version}.'}

        # 4. 加入
        room['players'].append(current_user)
        # 如果有邀請函，順便移除
        if current_user in self.invitations and room_id in self.invitations[current_user]:
            self.invitations[current_user].remove(room_id)
            
        return {'type': 'ROOM_RESPONSE', 'success': True, 'message': 'Joined room.'}

    def _handle_leave_room(self, current_user):
        room_id = self._get_player_room_id(current_user)
        if not room_id:
            return {'type': 'ROOM_RESPONSE', 'success': False, 'message': 'Not in a room.'}
            
        room = self.rooms[room_id]
        if current_user in room['players']:
            room['players'].remove(current_user)
            
        # 如果房間沒人了，刪除房間
        if not room['players']:
            del self.rooms[room_id]
        # 如果房主離開了，轉讓房主 (簡單實作：轉給下一個人)
        elif room['host'] == current_user:
            room['host'] = room['players'][0]
            
        return {'type': 'ROOM_RESPONSE', 'success': True, 'message': 'Left room.'}

    def _handle_get_room_info(self, current_user):
        """讓在房間內的玩家持續輪詢(Polling)房間狀態"""
        room_id = self._get_player_room_id(current_user)
        if not room_id:
            return {'type': 'ROOM_INFO_RESPONSE', 'success': False, 'data': None}
        
        return {'type': 'ROOM_INFO_RESPONSE', 'success': True, 'data': self.rooms[room_id]}

    def _handle_invite_user(self, data, current_user):
        target_user = data.get('target_user')
        room_id = self._get_player_room_id(current_user)
        
        if not room_id or self.rooms[room_id]['host'] != current_user:
            return {'type': 'INVITE_RESPONSE', 'success': False, 'message': 'Only host can invite.'}

        # 簡單檢查目標是否在線上 (選用)
        # if target_user not in self.logged_in_players: ...
        
        if target_user not in self.invitations:
            self.invitations[target_user] = []
        
        if room_id not in self.invitations[target_user]:
            self.invitations[target_user].append(room_id)
            
        return {'type': 'INVITE_RESPONSE', 'success': True, 'message': f'Invited {target_user}.'}

    def _handle_get_invitations(self, current_user):
        invites = self.invitations.get(current_user, [])
        details = []
        for rid in invites:
            if rid in self.rooms:
                r = self.rooms[rid]
                # 修改：回傳字典結構
                details.append({
                    "id": rid,
                    "game_name": r['game_name'],
                    "host": r['host']
                })
        return {'type': 'INVITE_LIST_RESPONSE', 'success': True, 'data': details}

    def _handle_add_review(self, data, current_user):
        game_name = data.get('game_name')
        try:
            rating = int(data.get('rating'))
            if not (1 <= rating <= 5):
                raise ValueError
        except:
            return {'type': 'REVIEW_RESPONSE', 'success': False, 'message': 'Rating must be integer 1-5.'}
            
        comment = data.get('comment', '')
        
        # 呼叫 db_manager
        success, msg = db_manager.add_review(game_name, current_user, rating, comment)
        
        return {'type': 'REVIEW_RESPONSE', 'success': success, 'message': msg}

    def _handle_get_online_players(self, current_user):
        """回傳目前所有在線的玩家名稱，排除請求者本人。"""
        online_users = []
        for username in self.logged_in_players.keys():
            if username != current_user:
                online_users.append(username)
        
        return {'type': 'ONLINE_USERS_RESPONSE', 'success': True, 'data': online_users}

    # 輔助：查詢玩家所在的 Room ID
    def _get_player_room_id(self, username):
        for r_id, room in self.rooms.items():
            if username in room['players']:
                return r_id
        return None

    def _handle_start_game(self, current_user):
        """房主啟動遊戲"""
        room_id = self._get_player_room_id(current_user)
        if not room_id:
            return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': 'Not in a room.'}
            
        room = self.rooms[room_id]
        if room['host'] != current_user:
            return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': 'Only host can start game.'}

        # 1. 準備啟動參數
        game_name = room['game_name']
        version = room['version']
        
        # 查詢遊戲設定檔中的啟動指令
        game_info = db_manager.game_data.get(game_name)
        if not game_info:
             return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': 'Game data not found.'}
             
        server_cmd = game_info.get('server_cmd') 
        # 如果是方案 B (game_config 有區分 server_cmd)
        # server_cmd = game_info.get('server_cmd') 

        if not server_cmd:
            return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': 'Server command not defined.'}

        # 2. 尋找空閒 Port
        game_port = self._find_free_port()
        
        #1. 定義 ZIP 路徑與解壓目標路徑
        zip_path = os.path.join(UPLOADED_GAMES_DIR, game_name, f"{version}.zip")
        # 為了避免跟 zip 檔混淆，我們解壓到一個專屬資料夾，例如 .../{version}_extracted/
        extract_dir = os.path.join(UPLOADED_GAMES_DIR, game_name, f"{version}_extracted")
        
        # 2. 如果解壓目錄不存在，進行解壓
        if not os.path.exists(extract_dir):
            if not os.path.exists(zip_path):
                return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': 'Game file zip not found.'}
            
            try:
                print(f"Extracting game server files to {extract_dir}...")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
            except Exception as e:
                return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': f'Failed to extract server files: {e}'}
        
        # 3. 組合完整指令 (server_cmd + port + players)
        # 路徑: server_data/uploaded_games/{game}/{ver}/
        game_dir = extract_dir # 使用解壓後的目錄
        
        # 為了作業順利，我們假設: uploaded_games/TestSnake/server.py 存在
        # 指令: python server.py --port 9001 --player_count 2
        
        full_cmd = server_cmd + [
            '--port', str(game_port), 
            '--player_count', str(len(room['players'])),
            '--players' # 新增參數旗標
        ] + room['players'] 


        print(f"Starting Game Server: {full_cmd} at {game_dir}")

        try:
            # 4. 啟動子程序
            # cwd=game_dir 確保程式在正確目錄執行
            process = subprocess.Popen(
                full_cmd, 
                cwd=game_dir,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1 # Line buffered
            )
            
            self.active_game_servers[room_id] = process
            room['status'] = 'PLAYING'
            
            # 5. 啟動監控執行緒 (負責收屍與紀錄結果)
            monitor_thread = threading.Thread(
                target=self._monitor_game_process,
                args=(room_id, process, game_name, room['players'])
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # 6. 通知房間內所有人 "GAME_STARTED"
            # 這裡我們不直接回傳 socket response，而是回傳成功，
            # 並依賴 "get_room_info" 輪詢，或者如果您有實作廣播機制(Broadcast)。
            # 鑑於目前的輪詢架構，我們更新 room['status'] = 'PLAYING' 並將 ip/port 寫入 room info
            
            room['server_ip'] = self.host # 或是 Public IP
            room['server_port'] = game_port
            
            return {'type': 'START_GAME_RESPONSE', 'success': True, 'message': 'Game server started.'}
            
        except Exception as e:
            print(f"Start game error: {e}")
            return {'type': 'START_GAME_RESPONSE', 'success': False, 'message': f'Failed to start process: {e}'}

    def _find_free_port(self):
        """尋找一個空閒的 Port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def _monitor_game_process(self, room_id, process, game_name, players):
        """(簡化版) 等待遊戲結束後再一次性讀取結果"""
        print(f"Monitor started for Room {room_id} (Waiting for exit...)")
        
        try:
            # 1. 這裡會「阻塞」直到遊戲程序完全結束
            # communicate 會自動讀取所有 stdout 和 stderr，避免卡死
            stdout_data, stderr_data = process.communicate()
            
            print(f"Game Server for Room {room_id} finished.")
            
            # 2. 解析輸出內容
            winner = None
            if stdout_data:
                # 將所有輸出按行分割
                lines = stdout_data.splitlines()
                for line in lines:
                    # 您可以選擇是否要印出所有 Log
                    # print(f"[GameServer {room_id}] {line}") 
                    
                    if line.startswith("GAME_RESULT:"):
                        try:
                            json_str = line.split("GAME_RESULT:", 1)[1].strip()
                            result_data = json.loads(json_str)
                            winner = result_data.get('winner')
                            print(f"Found Result: {winner}")
                        except Exception as e:
                            print(f"Failed to parse result: {e}")

            # 3. 記錄到 DB (邏輯不變)
            if winner:
                db_manager.add_match_record(game_name, players, winner)
                print(f"Match recorded: {winner} won.")
            else:
                print(f"Match finished without valid result.")

            # 4. 清理房間狀態 (邏輯不變)
            if room_id in self.rooms:
                self.rooms[room_id]['status'] = 'WAITING'
                if 'server_ip' in self.rooms[room_id]: del self.rooms[room_id]['server_ip']
                if 'server_port' in self.rooms[room_id]: del self.rooms[room_id]['server_port']
                
            if room_id in self.active_game_servers:
                del self.active_game_servers[room_id]

        except Exception as e:
            print(f"Monitor error: {e}")

    def _handle_get_history(self, current_user):
        history = db_manager.get_user_history(current_user)
        return {'type': 'HISTORY_RESPONSE', 'success': True, 'data': history}

if __name__ == '__main__':
    # 這是為了讓 lobby_server.py 可以被單獨執行
    print("=== Independent Lobby Server Launch ===")
    
    server = LobbyServer()
    
    try:
        # start() 裡面有 while 迴圈，會卡住主程式直到伺服器停止
        server.start()
    except KeyboardInterrupt:
        print("\nStopping Lobby Server...")
        server.stop()
    except Exception as e:
        print(f"\nServer crashed: {e}")
        import traceback
        traceback.print_exc()
        server.stop()