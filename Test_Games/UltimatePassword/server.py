import socket
import threading
import argparse
import json
import random
import time
import sys

class GameServer:
    def __init__(self, port, expected_players):
        self.port = port
        self.expected_players = expected_players
        self.server_socket = None
        self.clients = [] # [{'sock':..., 'name':...}]
        self.running = True
        
        # 遊戲狀態
        self.min_val = 1
        self.max_val = 100
        self.target = random.randint(self.min_val , self.max_val )

    def start(self):
        print(f"UltimatePassword Server starting on port {self.port}...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        # 等待玩家
        print(f"Waiting for {self.expected_players} players...")
        while len(self.clients) < self.expected_players:
            conn, addr = self.server_socket.accept()
            try:
                # 簡單協議：連線後第一條訊息是名字
                conn.settimeout(5.0)
                name = conn.recv(1024).decode().strip()
                conn.settimeout(None)
                print(f"Player {name} connected from {addr}")
                self.clients.append({'sock': conn, 'name': name})
                self.broadcast(f"[系統] 玩家 {name} 加入了遊戲 ({len(self.clients)}/{self.expected_players})")
            except Exception as e:
                print(f"Connection error: {e}")
                conn.close()

        print("Game Starting!")
        time.sleep(1)
        self.broadcast("\n=== 終極密碼 遊戲開始! ===")
        self.broadcast(f"目標範圍: {self.min_val} ~ {self.max_val}")
        self.broadcast("猜中密碼的人就輸了 (爆炸)！\n")
        
        self.game_loop()

    def broadcast(self, message, exclude_sock=None):
        for c in self.clients:
            if c['sock'] != exclude_sock:
                try:
                    c['sock'].sendall((message + "\n").encode())
                except: pass

    def send_private(self, player_idx, message):
        try:
            self.clients[player_idx]['sock'].sendall((message + "\n").encode())
        except: pass

    def game_loop(self):
        turn_idx = 0
        
        while self.running:
            current_player = self.clients[turn_idx]
            player_name = current_player['name']
            
            # 1. 廣播當前狀態
            self.broadcast(f"--------------------------------")
            self.broadcast(f"當前範圍: [{self.min_val} ~ {self.max_val}]")
            self.broadcast(f"輪到玩家: {player_name}")
            
            # 2. 通知當前玩家輸入
            # 發送特殊前綴 "INPUT:" 讓 Client 知道要解鎖輸入
            self.send_private(turn_idx, "INPUT:請輸入一個數字: ")
            
            # 3. 接收並驗證輸入
            valid_guess = False
            guess = -1
            
            while not valid_guess:
                try:
                    data = current_player['sock'].recv(1024).decode().strip()
                    if not data: # 斷線
                        self.broadcast(f"玩家 {player_name} 斷線了！遊戲結束。")
                        self.end_game(winner="Nobody")
                        return

                    if not data.isdigit():
                        self.send_private(turn_idx, "INPUT:[錯誤] 請輸入純數字: ")
                        continue
                        
                    guess = int(data)
                    
                    # 檢查範圍
                    if guess < self.min_val or guess > self.max_val:
                        self.send_private(turn_idx, f"INPUT:[錯誤] 數字必須在 {self.min_val} 到 {self.max_val} 之間: ")
                        continue
                        
                    valid_guess = True
                    
                except Exception as e:
                    print(f"Error receiving data: {e}")
                    break

            # 4. 廣播玩家的猜測
            self.broadcast(f"玩家 {player_name} 猜了: {guess}")
            time.sleep(0.5)

            # 5. 判定結果
            if guess == self.target:
                # 猜中 -> 爆炸 (輸)
                self.broadcast("\n" + "="*30)
                self.broadcast(f"BOOM!!! 密碼就是 {self.target}！")
                self.broadcast(f"玩家 {player_name} 爆炸了！")
                self.broadcast("="*30)
                
                # 決定贏家 (除了輸家以外的所有人)
                winners = [c['name'] for c in self.clients if c['name'] != player_name]
                if len(winners) == 1:
                    self.end_game(winners[0])
                else:
                    self.end_game(", ".join(winners)) # 多人獲勝
                break
            
            else:
                # 沒猜中 -> 更新範圍
                if guess < self.target:
                    self.min_val = guess + 1
                else:
                    self.max_val = guess - 1
                
                # 換下一位
                turn_idx = (turn_idx + 1) % len(self.clients)

    def end_game(self, winner):
        print(f"Game Over. Winner: {winner}")
        time.sleep(1)
        # 輸出標準結果供 Lobby 讀取
        result = {
            "winner": winner,
            "players": [c['name'] for c in self.clients]
        }
        # 這裡必須使用 print 並確保格式正確
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--player_count', type=int, default=2)
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count)
    server.start()