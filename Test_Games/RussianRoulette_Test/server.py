import socket
import threading
import argparse
import json
import random
import time
import sys

# === 遊戲邏輯類別 (Model) ===
class Revolver:
    def __init__(self):
        self.chamber = [False] * 6
        # 隨機放入一顆子彈
        bullet_pos = random.randint(0, 5)
        self.chamber[bullet_pos] = True
        self.current_pos = 0

    def pull_trigger(self):
        """扣下板機，回傳是否擊發 (True/False)"""
        fired = self.chamber[self.current_pos]
        # 轉動彈倉到下一個位置
        self.current_pos = (self.current_pos + 1) % 6
        return fired

class GameServer:
    def __init__(self, port, expected_players):
        self.port = port
        self.expected_players = expected_players
        self.server_socket = None
        # 用來儲存已連線的客戶端資料: [{"sock": socket, "name": username}, ...]
        self.clients = [] 
        self.revolver = Revolver()
        self.is_running = True

    def start(self):
        """啟動伺服器並等待玩家連線"""
        print(f"Game Server starting on port {self.port}, waiting for {self.expected_players} players...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 允許 Port 重複使用，避免快速重啟時被佔用
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        # 等待所有玩家連線
        while len(self.clients) < self.expected_players:
            client_sock, addr = self.server_socket.accept()
            print(f"Player connected from {addr}")
            
            # 1. 接收玩家名稱 (簡單協議：連線後第一條訊息是名稱)
            username = client_sock.recv(1024).decode('utf-8').strip()
            print(f"Player registered as: {username}")
            
            self.clients.append({"sock": client_sock, "name": username})
            self.broadcast(f"目前人數: {len(self.clients)}/{self.expected_players}")

        print("All players connected. Game Starting!")
        self.broadcast("\n=== 遊戲開始! ===\n左輪手槍已上膛 (1發子彈, 6個彈倉)\n")
        time.sleep(1)
        self.game_loop()

    def broadcast(self, message, exclude_sock=None):
        """發送訊息給所有玩家"""
        for client in self.clients:
            if client["sock"] != exclude_sock:
                try:
                    client["sock"].sendall((message + "\n").encode('utf-8'))
                except:
                    pass

    def game_loop(self):
        """主遊戲迴圈 (回合制)"""
        turn_idx = 0
        loser = None
        winner = None

        while self.is_running:
            current_player = self.clients[turn_idx]
            next_player = self.clients[(turn_idx + 1) % len(self.clients)]
            
            print(f"Turn: {current_player['name']}")

            # 1. 通知玩家輪到他了
            self.broadcast(f"\n輪到 [{current_player['name']}] 了...")
            current_player["sock"].sendall("ACTION:YOUR_TURN\n".encode('utf-8'))

            # 2. 等待玩家動作 (這裡簡單等待客戶端傳送任何資料，代表扣板機)
            try:
                # 阻塞式接收，等待玩家按 Enter
                data = current_player["sock"].recv(1024)
                if not data: break # 玩家斷線
            except:
                break # 連線錯誤

            self.broadcast(f"[{current_player['name']}] 拿起槍，抵住太陽穴，扣下板機...")
            time.sleep(1.5) # 製造緊張感

            # 3. 執行遊戲邏輯
            fired = self.revolver.pull_trigger()

            # 4. 廣播結果
            if fired:
                self.broadcast(">>> 【 砰! 】 <<<")
                self.broadcast(f"[{current_player['name']}] 不幸倒地。")
                loser = current_player
                winner = next_player
                self.is_running = False # 遊戲結束
            else:
                self.broadcast("... 卡嗒。(空包彈)")
                self.broadcast(f"[{current_player['name']}] 鬆了一口氣，將槍傳給下一個人。")
                time.sleep(1)
                # 換下一個人
                turn_idx = (turn_idx + 1) % len(self.clients)

        self.end_game(winner, loser)

    def end_game(self, winner_data, loser_data):
        """遊戲結束處理"""
        print("Game Over.")
        self.broadcast(f"\n=== 遊戲結束 ===\n獲勝者是: [{winner_data['name']}]!")
        
        # 關閉所有連線
        for client in self.clients:
            client["sock"].close()
        self.server_socket.close()

        # === 關鍵：印出標準格式的遊戲結果供 Lobby Server 讀取 ===
        result = {
            "winner": winner_data['name'],
            "players": [c['name'] for c in self.clients]
        }
        # 這裡必須使用 print 並確保格式正確
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    # 使用標準參數解析
    parser = argparse.ArgumentParser(description="Russian Roulette Game Server")
    parser.add_argument('--port', type=int, required=True, help='Port to listen on')
    parser.add_argument('--player_count', type=int, default=2, help='Number of players expected')
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count)
    server.start()