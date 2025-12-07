# Server/developer_server.py
import socket
import threading
import sys
import os
import base64
import shutil
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得上一層目錄 (project_root)
parent_dir = os.path.dirname(current_dir)
# 將上一層目錄加入系統搜尋路徑
sys.path.append(parent_dir)
from utils import send_message, receive_message
from db_manager import db_manager
from config import SERVER_HOST, DEVELOPER_PORT, UPLOADED_GAMES_DIR

class DeveloperServer:
    def __init__(self):
        self.host = SERVER_HOST
        self.port = DEVELOPER_PORT
        self.server_socket = None
        self.is_running = False
        # 儲存已登入的開發者 (username: client_socket)
        # 用於防止重複登入以及驗證請求來源
        self.logged_in_developers = {} 

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 設置 SO_REUSEADDR 允許 Server 重啟後立即使用同一 Port
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.is_running = True
            print(f"Developer Server listening on {self.host}:{self.port}...")
            
            # 主線程負責接受新連線
            while self.is_running:
                try:
                    client_sock, client_addr = self.server_socket.accept()
                    print(f"New connection from {client_addr}")
                    # 為每個新連線啟動一個獨立線程處理
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
                        print(f"Error accepting connection: {e}")
                    break
        except Exception as e:
            print(f"Failed to start Developer Server: {e}")
            self.is_running = False

    def stop(self):
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        print("Developer Server stopped.")

    def handle_client(self, client_sock, client_addr):
        """處理單一 Client 連線的線程邏輯"""
        current_user = None # 用於該線程記錄當前服務的用戶
        
        while self.is_running:
            try:
                # 接收 Client 請求
                request = receive_message(client_sock)
                if request is None:
                    break # 連線斷開

                action = request.get('action')
                data = request.get('data', {})
                
                # 路由請求並取得回應
                response = self.route_request(action, data, current_user, client_sock)
                
                # 特殊邏輯：如果是登入成功，更新當前線程的用戶狀態
                if action == 'login' and response.get('success'):
                    current_user = data.get('username')
                
                # 特殊邏輯：如果是登出成功，清除當前線程的用戶狀態
                if action == 'logout' and response.get('success'):
                    current_user = None

                # 發送回應給 Client
                send_message(client_sock, response)
                
            except Exception as e:
                print(f"Client handler error for {client_addr}: {e}")
                break
        
        # 線程結束時的清理工作
        if current_user and current_user in self.logged_in_developers:
            print(f"Cleaning up session for {current_user}")
            del self.logged_in_developers[current_user]
        
        client_sock.close()
        print(f"Connection closed for {client_addr}")

    # Server/developer_server.py

    def route_request(self, action, data, current_user, client_sock):
        """根據 action 分發請求到對應的業務邏輯函式"""
        
        if action == 'register':
            return self._handle_register(data)
        elif action == 'login':
            return self._handle_login(data, client_sock)
        
        # --- 以下操作需要登入權限 ---
        
        if not current_user:
            return {'type': 'ERROR', 'success': False, 'message': 'Permission denied. Please log in first.'}

        if action == 'logout':
            return self._handle_logout(data)
        elif action == 'upload_game':
            return self._handle_upload_game(data, current_user)
        elif action == 'update_game':
            return self._handle_update_game(data, current_user)
        elif action == 'delete_game':
            return self._handle_delete_game(data, current_user)
        elif action == 'get_uploaded_games':
            return self._handle_get_uploaded_games(current_user)
            
        return {'type': 'ERROR', 'success': False, 'message': f'Unknown action: {action}'}

    # --- 業務邏輯實作 ---

    def _handle_register(self, data):
        """處理開發者註冊"""
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return {'type': 'REGISTER_RESPONSE', 'success': False, 'message': 'Missing credentials.'}

        # 呼叫 DB Manager 進行註冊
        success, message = db_manager.add_user(username, password, 'developers')
        
        return {'type': 'REGISTER_RESPONSE', 'success': success, 'message': message}

    def _handle_login(self, data, client_sock):
        """處理開發者登入"""
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return {'type': 'LOGIN_RESPONSE', 'success': False, 'message': 'Missing credentials.'}

        # 1. 檢查是否重複登入
        if username in self.logged_in_developers:
            return {'type': 'LOGIN_RESPONSE', 'success': False, 'message': 'Account already logged in.'}
        
        # 2. 驗證帳號密碼
        success, user_data_or_msg = db_manager.authenticate_user(username, password, 'developers')
        
        if success:
            # 3. 登入成功，記錄 Session
            self.logged_in_developers[username] = client_sock
            
            # 移除密碼欄位再回傳
            safe_data = {k: v for k, v in user_data_or_msg.items() if k != 'password'}
            # 補上 username 方便 Client 端顯示
            safe_data['username'] = username 
            
            return {'type': 'LOGIN_RESPONSE', 'success': True, 'data': safe_data}
        else:
            return {'type': 'LOGIN_RESPONSE', 'success': False, 'message': user_data_or_msg}

    def _handle_logout(self, data):
        """處理開發者登出"""
        username = data.get('username')
        
        if username and username in self.logged_in_developers:
            del self.logged_in_developers[username]
            return {'type': 'LOGOUT_RESPONSE', 'success': True, 'message': 'Logged out successfully.'}
        
        return {'type': 'LOGOUT_RESPONSE', 'success': False, 'message': 'User not logged in or invalid session.'}

    # --- D1: 上架新遊戲 (Create) ---
    def _handle_upload_game(self, data, current_user):
        """處理上架新遊戲請求"""
        try:
            game_config = data.get('game_config')
            zip_b64 = data.get('zip_data')
            
            # 基本資料檢查
            if not game_config or not zip_b64:
                return {'type': 'UPLOAD_RESPONSE', 'success': False, 'message': 'Incomplete data.'}

            game_name = game_config.get('game_name')
            version = game_config.get('version')
            
            # 1. 設定儲存路徑
            save_dir = os.path.join(UPLOADED_GAMES_DIR, game_name)
            
            # 2. 檢查是否已存在 (實體資料夾檢查)
            # 如果資料夾存在且不為空，通常代表遊戲已上架，應引導使用 Update
            if os.path.exists(save_dir) and os.listdir(save_dir):
                 return {'type': 'UPLOAD_RESPONSE', 'success': False, 'message': f"Game '{game_name}' already exists. Please use 'Update Game'."}

            # 3. 建立資料夾
            os.makedirs(save_dir, exist_ok=True)
            
            # 4. 解碼 Base64 並寫入 ZIP 檔
            file_path = os.path.join(save_dir, f"{version}.zip")
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(zip_b64))

            # 5. 更新資料庫 (呼叫 db_manager.create_game)
            success, msg = db_manager.create_game(game_name, version, current_user, game_config)
            
            if success:
                 print(f"New game uploaded: {game_name} v{version} by {current_user}")
                 return {'type': 'UPLOAD_RESPONSE', 'success': True, 'message': 'Game created successfully.'}
            else:
                 # 若 DB 寫入失敗，進行檔案回滾 (刪除剛建立的資料夾)
                 try:
                     shutil.rmtree(save_dir)
                 except Exception:
                     pass
                 return {'type': 'UPLOAD_RESPONSE', 'success': False, 'message': f'DB Error: {msg}'}

        except Exception as e:
            print(f"Upload error: {e}")
            return {'type': 'UPLOAD_RESPONSE', 'success': False, 'message': f'Server error: {e}'}

    # --- D2: 更新遊戲 (Update & Overwrite) ---
    def _handle_update_game(self, data, current_user):
        """處理更新遊戲請求 (刪除舊檔模式)"""
        try:
            game_config = data.get('game_config')
            zip_b64 = data.get('zip_data')
            
            if not game_config or not zip_b64:
                return {'type': 'UPDATE_RESPONSE', 'success': False, 'message': 'Incomplete data.'}

            game_name = game_config.get('game_name')
            version = game_config.get('version')
            
            save_dir = os.path.join(UPLOADED_GAMES_DIR, game_name)
            
            # 1. 檢查遊戲資料夾是否存在 (確保是更新而非新上架)
            if not os.path.exists(save_dir):
                return {'type': 'UPDATE_RESPONSE', 'success': False, 'message': 'Game not found on server. Please use Upload first.'}

            # 2. === 關鍵邏輯：清空舊檔案 ===
            # 遍歷資料夾內容並刪除，保留資料夾本身
            for filename in os.listdir(save_dir):
                file_path = os.path.join(save_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path) # 刪除檔案
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path) # 刪除子資料夾
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")

            # 3. 儲存新版本檔案
            new_file_path = os.path.join(save_dir, f"{version}.zip")
            with open(new_file_path, 'wb') as f:
                f.write(base64.b64decode(zip_b64))

            # 4. 更新資料庫 (呼叫 db_manager.update_game)
            success, msg = db_manager.update_game(game_name, version, current_user, game_config)
            
            if success:
                 print(f"Game updated: {game_name} -> v{version}")
                 return {'type': 'UPDATE_RESPONSE', 'success': True, 'message': f'Updated to v{version}.'}
            else:
                 return {'type': 'UPDATE_RESPONSE', 'success': False, 'message': f'DB Error: {msg}'}

        except Exception as e:
            print(f"Update error: {e}")
            return {'type': 'UPDATE_RESPONSE', 'success': False, 'message': f'Server error: {e}'}
        
    def _handle_delete_game(self, data, current_user):
        """處理下架遊戲請求"""
        try:
            game_name = data.get('game_name')
            if not game_name:
                return {'type': 'DELETE_RESPONSE', 'success': False, 'message': 'Game name required.'}

            # 1. 呼叫 DB 進行刪除
            # (注意：我們先刪 DB，成功後再刪檔案，避免檔案刪了但 DB 還留著)
            success, msg = db_manager.delete_game(game_name, current_user)
            
            if not success:
                return {'type': 'DELETE_RESPONSE', 'success': False, 'message': msg}

            # 2. 刪除實體檔案資料夾
            save_dir = os.path.join(UPLOADED_GAMES_DIR, game_name)
            if os.path.exists(save_dir):
                try:
                    shutil.rmtree(save_dir) # 遞迴刪除資料夾
                except Exception as e:
                    print(f"Warning: Failed to delete folder {save_dir}: {e}")
                    # 雖然檔案刪除失敗，但 DB 已經刪除了，所以對用戶來說算是成功下架
            
            print(f"Game deleted: {game_name} by {current_user}")
            return {'type': 'DELETE_RESPONSE', 'success': True, 'message': 'Game deleted successfully.'}

        except Exception as e:
            print(f"Delete error: {e}")
            return {'type': 'DELETE_RESPONSE', 'success': False, 'message': f'Server error: {e}'}

    def _handle_get_uploaded_games(self, current_user):
        """回傳開發者已上架的遊戲"""
        games = db_manager.get_games_by_author(current_user)
        return {'type': 'GAME_LIST_RESPONSE', 'success': True, 'data': games}

if __name__ == '__main__':
    print("=== Independent Developer Server Launch ===")
    
    server = DeveloperServer()
    
    try:
        # start() 裡面有 while 迴圈，會卡住主程式直到伺服器停止
        server.start()
    except KeyboardInterrupt:
        print("\nStopping Developer Server...")
        server.stop()
    except Exception as e:
        print(f"\nServer crashed: {e}")
        import traceback
        traceback.print_exc()
        server.stop()