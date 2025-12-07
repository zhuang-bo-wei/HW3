# config.py
import os
import sys

# --- 網路配置 ---
SERVER_HOST = '140.113.17.11' 
LOBBY_PORT = 8888
DEVELOPER_PORT = 8889
HEADER_SIZE = 4

# --- 路徑配置 (關鍵修改) ---
# 取得 config.py 所在的資料夾 (即 GameStore_Final 根目錄)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Server 端資料 (存放在 Server/server_data)
SERVER_DATA_DIR = os.path.join(BASE_DIR, 'Server', 'server_data')
USERS_DB_FILE = os.path.join(SERVER_DATA_DIR, 'users.json')
GAMES_DB_FILE = os.path.join(SERVER_DATA_DIR, 'games.json')
UPLOADED_GAMES_DIR = os.path.join(SERVER_DATA_DIR, 'uploaded_games')

# Client 端下載區 (存放在 Client/client_downloads)
CLIENT_DOWNLOADS_BASE_DIR = os.path.join(BASE_DIR, 'Client', 'client_downloads')

# 確保目錄存在
os.makedirs(SERVER_DATA_DIR, exist_ok=True)
os.makedirs(CLIENT_DOWNLOADS_BASE_DIR, exist_ok=True)