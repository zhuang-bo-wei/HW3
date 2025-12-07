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
        bullet_pos = random.randint(0, 5)
        self.chamber[bullet_pos] = True
        self.current_pos = 0

    def pull_trigger(self):
        fired = self.chamber[self.current_pos]
        self.current_pos = (self.current_pos + 1) % 6
        return fired

class GameServer:
    def __init__(self, port, expected_players, player_names):
        self.port = port
        self.expected_players = expected_players
        self.server_socket = None
        self.clients = [] 
        self.revolver = Revolver()
        self.is_running = True
        
        # [新增] 保存完整玩家名單 (用於戰績紀錄)
        self.player_names = player_names 

    def start(self):
        print(f"Game Server starting on port {self.port}...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        # 等待玩家連線
        while len(self.clients) < self.expected_players:
            conn, addr = self.server_socket.accept()
            try:
                conn.settimeout(5.0)
                name = conn.recv(1024).decode('utf-8').strip()
                conn.settimeout(None)
                
                # 驗證身分 (選用)
                if name not in self.player_names:
                    print(f"Rejected unknown player: {name}")
                    conn.close()
                    continue
                    
                print(f"Player {name} connected")
                self.clients.append({"sock": conn, "name": name})
                self.broadcast(f"目前人數: {len(self.clients)}/{self.expected_players}")
            except Exception as e:
                print(f"Connection error: {e}")
                conn.close()

        print("All players connected. Game Starting!")
        self.broadcast("\n=== 遊戲開始! ===\n左輪手槍已上膛 (1發子彈, 6個彈倉)\n")
        time.sleep(1)
        self.game_loop()

    def broadcast(self, message, exclude_sock=None):
        for client in self.clients:
            if client["sock"] != exclude_sock:
                try:
                    client["sock"].sendall((message + "\n").encode('utf-8'))
                except:
                    pass

    def handle_disconnect(self, disconnected_player):
        """處理斷線：視為該玩家輸了"""
        print(f"Player {disconnected_player['name']} disconnected.")
        self.broadcast(f"\n>>> 玩家 [{disconnected_player['name']}] 斷線！判負。 <<<")
        
        # 找出贏家 (另一個沒斷線的人)
        winner = None
        for c in self.clients:
            if c['name'] != disconnected_player['name']:
                winner = c
                break
        
        # 如果因為某種原因找不到贏家 (例如都斷了)，就隨便指定或 None
        winner_name = winner['name'] if winner else "None"
        self.end_game(winner_name)

    def game_loop(self):
        turn_idx = 0
        
        while self.is_running:
            current_player = self.clients[turn_idx]
            next_player_idx = (turn_idx + 1) % len(self.clients)
            next_player = self.clients[next_player_idx]
            
            print(f"Turn: {current_player['name']}")

            # 1. 通知玩家
            self.broadcast(f"\n輪到 [{current_player['name']}] 了...")
            try:
                current_player["sock"].sendall("ACTION:YOUR_TURN\n".encode('utf-8'))
            except:
                self.handle_disconnect(current_player)
                return

            # 2. 等待動作
            try:
                data = current_player["sock"].recv(1024)
                if not data: raise Exception("Disconnected")
            except:
                self.handle_disconnect(current_player)
                return

            self.broadcast(f"[{current_player['name']}] 拿起槍，抵住太陽穴，扣下板機...")
            time.sleep(1.5)

            # 3. 執行邏輯
            fired = self.revolver.pull_trigger()

            # 4. 處理結果
            if fired:
                self.broadcast(">>> 【 砰! 】 <<<")
                self.broadcast(f"[{current_player['name']}] 不幸倒地。")
                
                # 輸家是 current，贏家是 next
                self.end_game(next_player['name'])
                return
            else:
                self.broadcast("... 卡嗒。(空包彈)")
                self.broadcast(f"[{current_player['name']}] 鬆了一口氣，將槍傳給下一個人。")
                time.sleep(1)
                turn_idx = next_player_idx

    def end_game(self, winner_name):
        print("Game Over.")
        self.broadcast(f"\n=== 遊戲結束 ===\n獲勝者是: [{winner_name}]!")
        
        for client in self.clients:
            try: client["sock"].close()
            except: pass
        
        if self.server_socket:
            self.server_socket.close()

        # 使用啟動時傳入的完整玩家名單，確保斷線者也有紀錄
        result = {
            "winner": winner_name,
            "players": self.player_names 
        }
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--player_count', type=int, default=2)
    # [新增] 接收完整玩家名單
    parser.add_argument('--players', nargs='+', required=True)
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count, args.players)
    server.start()