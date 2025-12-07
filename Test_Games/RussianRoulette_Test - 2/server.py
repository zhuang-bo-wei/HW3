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
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        # 等待所有玩家連線
        while len(self.clients) < self.expected_players:
            client_sock, addr = self.server_socket.accept()
            print(f"Player connected from {addr}")
            
            # 1. 接收玩家名稱
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
            # 計算下一個玩家 (對手)
            next_player_idx = (turn_idx + 1) % len(self.clients)
            next_player = self.clients[next_player_idx]
            
            print(f"Turn: {current_player['name']}")

            # 1. 通知玩家輪到他了
            self.broadcast(f"\n輪到 [{current_player['name']}] 了，請選擇目標...")
            current_player["sock"].sendall("ACTION:YOUR_TURN\n".encode('utf-8'))

            # 2. 等待玩家動作 (接收選擇：1=自己, 2=對方)
            try:
                data = current_player["sock"].recv(1024)
                if not data: break 
                action = data.decode('utf-8').strip()
            except:
                break 

            # 3. 判斷目標
            # 如果輸入 '2' 代表射對方，否則預設射自己
            target_is_self = (action != "2")

            if target_is_self:
                self.broadcast(f"[{current_player['name']}] 顫抖著將槍口抵住 **自己的太陽穴**...")
            else:
                self.broadcast(f"[{current_player['name']}] 眼神一冷，將槍口指向 **[{next_player['name']}]**...")
            
            time.sleep(1.5) # 製造緊張感

            # 4. 執行遊戲邏輯
            fired = self.revolver.pull_trigger()

            # 5. 處理結果
            if fired:
                self.broadcast(">>> 【 砰! 】 <<<")
                if target_is_self:
                    # 射自己爆炸 -> 自己輸
                    self.broadcast(f"[{current_player['name']}] 不幸倒地。")
                    loser = current_player
                    winner = next_player
                else:
                    # 射對方爆炸 -> 對方輸 (自己贏)
                    self.broadcast(f"[{next_player['name']}] 被擊中倒地!")
                    loser = next_player
                    winner = current_player
                
                self.is_running = False # 遊戲結束
            else:
                self.broadcast("... 卡嗒。(空包彈)")
                
                if target_is_self:
                    # 射自己且沒死 -> 保留回合 (不切換 turn_idx)
                    self.broadcast(f"[{current_player['name']}] 存活下來！因為是對自己開槍，獲得 **額外一回合**。")
                    time.sleep(1)
                    # turn_idx 不變，直接進入下一次迴圈
                else:
                    # 射對方且沒死 -> 換人
                    self.broadcast(f"[{next_player['name']}] 毫髮無傷。槍權移交給對方。")
                    time.sleep(1)
                    turn_idx = next_player_idx

        self.end_game(winner, loser)

    def end_game(self, winner_data, loser_data):
        """遊戲結束處理"""
        print("Game Over.")
        self.broadcast(f"\n=== 遊戲結束 ===\n獲勝者是: [{winner_data['name']}]!")
        
        for client in self.clients:
            client["sock"].close()
        self.server_socket.close()

        result = {
            "winner": winner_data['name'],
            "players": [c['name'] for c in self.clients]
        }
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Russian Roulette Game Server")
    parser.add_argument('--port', type=int, required=True, help='Port to listen on')
    parser.add_argument('--player_count', type=int, default=2, help='Number of players expected')
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count)
    server.start()