# db_manager.py
import json
import os
import datetime
from config import USERS_DB_FILE, GAMES_DB_FILE, SERVER_DATA_DIR

class DBManager:
    """管理所有 JSON 資料庫的單例 (Singleton) 類別。"""
    
    def __init__(self):
        # 確保資料存放目錄存在
        os.makedirs(SERVER_DATA_DIR, exist_ok=True)
        
        self.user_data = self._load_data(USERS_DB_FILE, default_data={'developers': {}, 'players': {}})
        self.game_data = self._load_data(GAMES_DB_FILE, default_data={})
        
        # 紀錄已登入用戶 (非持久化，Server 重啟清空)
        self.logged_in_users = {} # {session_token: username} 或 {username: socket}

    def _load_data(self, filename, default_data):
        """從 JSON 檔案載入資料，若檔案不存在則創建預設值。"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {filename} is corrupt. Starting with default data.")
        
        # 初始化檔案
        self._save_data(filename, default_data)
        return default_data

    def _save_data(self, filename, data):
        """將資料寫回 JSON 檔案。"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving to {filename}: {e}")
            return False

    # --- 遊戲相關操作 ---
    
    def create_game(self, game_name, version, author, config):
        """D1 上架新遊戲 (扁平化結構)"""
        
        # 1. 檢查遊戲是否已存在
        if game_name in self.game_data:
            return False, f"Game '{game_name}' already exists. Please use Update function."
            
        # 2. 建立新遊戲條目 (直接將 version 放在第一層)
        self.game_data[game_name] = {
            "author": author,
            "description": config.get('description', ''),
            "type": "GUI" if config.get('is_gui') else "CLI",
            "min_players": config.get('min_players', 1),
            "max_players": config.get('max_players', 2),
            
            # --- 扁平化版本資訊 ---
            "version": version,
            "server_cmd": config.get('server_cmd'), # 新增
            "client_cmd": config.get('client_cmd'), # 新增
            "is_gui": config.get('is_gui'),
            "upload_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            "reviews": []
        }

        # 3. 儲存
        if self._save_data(GAMES_DB_FILE, self.game_data):
            return True, "Game created successfully."
        else:
            return False, "Failed to write to DB."

    def update_game(self, game_name, version, author, config):
        """D2 更新遊戲 (直接覆蓋欄位)"""
        
        # 1. 檢查遊戲是否存在
        if game_name not in self.game_data:
            return False, "Game does not exist."
        
        game_entry = self.game_data[game_name]
        
        # 2. 檢查權限
        if game_entry['author'] != author:
            return False, "Permission denied."

        # 3. 更新所有欄位
        game_entry['description'] = config.get('description', game_entry['description'])
        game_entry['min_players'] = config.get('min_players', game_entry['min_players'])
        game_entry['max_players'] = config.get('max_players', game_entry['max_players'])
        game_entry['type'] = "GUI" if config.get('is_gui') else "CLI"
        
        # --- 更新版本資訊 (直接覆蓋) ---
        game_entry['version'] = version
        game_entry['server_cmd'] = config.get('server_cmd') # 新增
        game_entry['client_cmd'] = config.get('client_cmd') # 新增
        game_entry['is_gui'] = config.get('is_gui')
        game_entry['upload_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 4. 儲存
        if self._save_data(GAMES_DB_FILE, self.game_data):
            return True, f"Game updated to version {version}."
        else:
            return False, "Failed to write to DB."

    def delete_game(self, game_name, author):
        """D3 下架遊戲"""
        
        # 1. 檢查遊戲是否存在
        if game_name not in self.game_data:
            return False, "Game does not exist."
        
        # 2. 檢查權限
        if self.game_data[game_name]['author'] != author:
            return False, "Permission denied: You are not the author."

        # 3. 刪除條目
        del self.game_data[game_name]

        # 4. 儲存
        if self._save_data(GAMES_DB_FILE, self.game_data):
            return True, f"Game '{game_name}' deleted successfully."
        else:
            return False, "Failed to write to DB."

    # --- 用戶相關操作 ---
    def get_user(self, username, user_type):
        """取得特定用戶資料 (Player 或 Developer)。"""
        return self.user_data.get(user_type, {}).get(username)

    # db_manager.py (簡化後的 add_user 範例)

    def add_user(self, username, password, user_type):
        """註冊新用戶"""
        if username in self.user_data.get(user_type, {}):
            return False, "Account already exists."
        
        #儲存密碼
        initial_data = {"password": password} 
        
        if user_type == 'developers':
            initial_data["games"] = []
        elif user_type == 'players':
            initial_data["play_history"] = []
            
        self.user_data[user_type][username] = initial_data
        self._save_data(USERS_DB_FILE, self.user_data)
        return True, "Registration successful."

    # 登入驗證
    def authenticate_user(self, username, password, user_type):
        """驗證用戶登入。"""
        user = self.get_user(username, user_type)
        if not user:
            return False, "Account not found."
        
        stored_password = user.get('password')
        
        if stored_password is None:
            # 如果資料庫裡這筆資料沒有密碼欄位 (資料損毀)
            return False, "Data corruption: Password missing. Please re-register."

        if stored_password == password:
            return True, user
        else:
            return False, "Incorrect password."

    # --- 遊戲相關操作  ---
    def get_all_games(self):
        """取得所有已上架遊戲的列表。"""
        return self.game_data

    def get_games_by_author(self, author):
        """取得特定作者的上架遊戲列表 (開發者後台用)"""
        my_games = {}
        for name, info in self.game_data.items():
            if info.get('author') == author:
                my_games[name] = info
        return my_games

    def save_game_data(self):
        """儲存遊戲資料變更。"""
        self._save_data(GAMES_DB_FILE, self.game_data)
        
    def save_user_data(self):
        """儲存用戶資料變更。"""
        self._save_data(USERS_DB_FILE, self.user_data)
    
    def add_review(self, game_name, username, rating, comment):
        """新增遊戲評論與評分"""
        if game_name not in self.game_data:
            return False, "Game not found."
        
        # 確保 reviews 欄位存在 (舊資料可能沒有)
        if "reviews" not in self.game_data[game_name]:
            self.game_data[game_name]["reviews"] = []

        # 檢查玩家是否已經評論過 (選擇性：避免洗頻)
        for r in self.game_data[game_name]["reviews"]:
            if r['user'] == username:
                # 這裡選擇覆蓋舊評論，或者你可以 return False 拒絕
                r['rating'] = rating
                r['comment'] = comment
                r['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_data(GAMES_DB_FILE, self.game_data)
                return True, "Review updated."

        new_review = {
            "user": username,
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.game_data[game_name]["reviews"].append(new_review)
        
        if self._save_data(GAMES_DB_FILE, self.game_data):
            return True, "Review added successfully."
        else:
            return False, "Database save error."

    # --- 對戰紀錄操作 ---

    def add_match_record(self, game_name, players, winner):
        """記錄對戰結果到所有參與玩家的歷史中"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        record = {
            "game": game_name,
            "timestamp": timestamp,
            "players": players,
            "winner": winner,
            "result": "WIN" if winner else "DRAW" # 簡單判定
        }

        # 更新所有參與者的紀錄
        for player in players:
            if player in self.user_data['players']:
                if 'play_history' not in self.user_data['players'][player]:
                    self.user_data['players'][player]['play_history'] = []
                
                # 為了節省空間，我們可以針對該玩家客製化 "result" 欄位
                # 例如對 player1 來說是 "WIN"，對 player2 是 "LOSE"
                player_record = record.copy()
                if winner:
                    player_record['result'] = "WIN" if player == winner else "LOSE"
                else:
                    player_record['result'] = "DRAW"

                self.user_data['players'][player]['play_history'].append(player_record)

        # 儲存
        self._save_data(USERS_DB_FILE, self.user_data)
        return True

    def get_user_history(self, username):
        """取得特定玩家的對戰紀錄"""
        user = self.get_user(username, 'players')
        if user:
            return user.get('play_history', [])
        return []

# 實例化 DBManager 以供 Server 模組使用
db_manager = DBManager()