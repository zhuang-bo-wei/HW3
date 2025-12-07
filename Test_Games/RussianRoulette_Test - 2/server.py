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
        self.player_names = player_names # [新增]

    def start(self):
        print(f"Game Server starting on port {self.port}...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        while len(self.clients) < self.expected_players:
            conn, addr = self.server_socket.accept()
            try:
                conn.settimeout(5.0)
                name = conn.recv(1024).decode('utf-8').strip()
                conn.settimeout(None)
                if name not in self.player_names:
                    conn.close()
                    continue
                print(f"Player {name} connected")
                self.clients.append({"sock": conn, "name": name})
                self.broadcast(f"目前人數: {len(self.clients)}/{self.expected_players}")
            except:
                conn.close()

        print("Game Starting!")
        self.broadcast("\n=== 遊戲開始! (v2.0) ===\n左輪手槍已上膛\n")
        time.sleep(1)
        self.game_loop()

    def broadcast(self, message, exclude_sock=None):
        for client in self.clients:
            if client["sock"] != exclude_sock:
                try: client["sock"].sendall((message + "\n").encode('utf-8'))
                except: pass

    def handle_disconnect(self, disconnected_player):
        print(f"Player {disconnected_player['name']} disconnected.")
        self.broadcast(f"\n>>> 玩家 [{disconnected_player['name']}] 斷線！判負。 <<<")
        winner = None
        for c in self.clients:
            if c['name'] != disconnected_player['name']:
                winner = c
                break
        winner_name = winner['name'] if winner else "None"
        self.end_game(winner_name)

    def game_loop(self):
        turn_idx = 0
        
        while self.is_running:
            current_player = self.clients[turn_idx]
            next_player_idx = (turn_idx + 1) % len(self.clients)
            next_player = self.clients[next_player_idx]
            
            self.broadcast(f"\n輪到 [{current_player['name']}] 了，請選擇目標...")
            try:
                current_player["sock"].sendall("ACTION:YOUR_TURN\n".encode('utf-8'))
                # 等待回應
                data = current_player["sock"].recv(1024)
                if not data: raise Exception("Disconnected")
                action = data.decode('utf-8').strip()
            except:
                self.handle_disconnect(current_player)
                return

            target_is_self = (action != "2")

            if target_is_self:
                self.broadcast(f"[{current_player['name']}] 顫抖著將槍口抵住 **自己的太陽穴**...")
            else:
                self.broadcast(f"[{current_player['name']}] 眼神一冷，將槍口指向 **[{next_player['name']}]**...")
            
            time.sleep(1.5)
            fired = self.revolver.pull_trigger()

            if fired:
                self.broadcast(">>> 【 砰! 】 <<<")
                if target_is_self:
                    self.broadcast(f"[{current_player['name']}] 不幸倒地。")
                    self.end_game(next_player['name']) # 射死自己，對手贏
                else:
                    self.broadcast(f"[{next_player['name']}] 被擊中倒地!")
                    self.end_game(current_player['name']) # 射死對手，自己贏
                return
            else:
                self.broadcast("... 卡嗒。(空包彈)")
                if target_is_self:
                    self.broadcast(f"[{current_player['name']}] 存活下來！獲得額外一回合。")
                else:
                    self.broadcast(f"[{next_player['name']}] 毫髮無傷。換人。")
                    turn_idx = next_player_idx
                time.sleep(1)

    def end_game(self, winner_name):
        print("Game Over.")
        self.broadcast(f"\n=== 遊戲結束 ===\n獲勝者是: [{winner_name}]!")
        for client in self.clients:
            try: client["sock"].close()
            except: pass
        if self.server_socket: self.server_socket.close()

        result = {
            "winner": winner_name,
            "players": self.player_names # [修正]
        }
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--player_count', type=int, default=2)
    parser.add_argument('--players', nargs='+', required=True) # [新增]
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count, args.players)
    server.start()