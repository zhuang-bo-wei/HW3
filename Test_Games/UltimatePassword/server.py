import socket
import threading
import argparse
import json
import random
import time
import sys

class GameServer:
    def __init__(self, port, expected_players, player_names):
        self.port = port
        self.expected_players = expected_players
        self.server_socket = None
        self.clients = [] # [{'sock':..., 'name':...}]
        self.running = True
        
        # 保存完整玩家名單 (用於戰績紀錄，不管中途誰斷線)
        self.player_names = player_names
        
        # 遊戲狀態
        self.min_val = 1
        self.max_val = 100
        self.target = random.randint(self.min_val + 1, self.max_val - 1)
        if self.target == self.min_val: self.target += 1
        if self.target == self.max_val: self.target -= 1

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
                conn.settimeout(5.0)
                name = conn.recv(1024).decode().strip()
                conn.settimeout(None)
                
                # 驗證是否在名單內 (選用)
                if name not in self.player_names:
                    print(f"Rejected unknown player: {name}")
                    conn.close()
                    continue

                print(f"Player {name} connected")
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
            return True
        except: 
            return False

    def handle_disconnect(self, idx):
        """處理玩家斷線：移除玩家，檢查是否結束"""
        if idx < 0 or idx >= len(self.clients): return False
        
        p = self.clients[idx]
        print(f"Player {p['name']} disconnected.")
        self.broadcast(f"\n[系統] 玩家 {p['name']} 斷線離開了遊戲！")
        
        try: p['sock'].close()
        except: pass
        
        # 移除該玩家
        self.clients.pop(idx)
        
        # 檢查剩餘人數
        if len(self.clients) < 2:
            # 只剩一人 (或沒人)，遊戲結束
            if self.clients:
                winner = self.clients[0]['name']
                self.broadcast(f"\n[系統] 存活者是 {winner}！遊戲結束。")
                self.end_game(winner)
            else:
                self.end_game("None")
            return False # 指示遊戲迴圈應該結束
            
        self.broadcast(f"[系統] 遊戲繼續，剩餘玩家: {len(self.clients)} 人")
        return True # 指示遊戲迴圈繼續

    def game_loop(self):
        turn_idx = 0
        
        while self.running:
            # 確保索引不越界 (因為 clients 長度可能變短)
            if turn_idx >= len(self.clients):
                turn_idx = 0
                
            current_player = self.clients[turn_idx]
            player_name = current_player['name']
            
            # 1. 廣播狀態
            self.broadcast(f"--------------------------------")
            self.broadcast(f"當前範圍: [{self.min_val} ~ {self.max_val}]")
            self.broadcast(f"輪到玩家: {player_name}")
            
            # 2. 通知輸入 (若發送失敗則視為斷線)
            if not self.send_private(turn_idx, "INPUT:請輸入一個數字: "):
                if not self.handle_disconnect(turn_idx): return
                continue # 移除後，同一索引指向下一位，直接重跑迴圈
            
            # 3. 接收輸入
            valid_guess = False
            guess = -1
            
            while not valid_guess:
                try:
                    data = current_player['sock'].recv(1024).decode().strip()
                    if not data: raise Exception("Empty data")

                    if not data.isdigit():
                        self.send_private(turn_idx, "INPUT:[錯誤] 請輸入純數字: ")
                        continue
                    
                    guess = int(data)
                    if guess < self.min_val or guess > self.max_val:
                        self.send_private(turn_idx, f"INPUT:[錯誤] 必須在 {self.min_val}-{self.max_val} 之間: ")
                        continue
                        
                    valid_guess = True
                    
                except Exception:
                    # 發生斷線
                    if not self.handle_disconnect(turn_idx): return
                    # 斷線後，不需要 increment turn_idx，直接 continue 會換下一位
                    valid_guess = False 
                    break 

            # 如果是因為斷線跳出的，直接進入下一輪
            if not valid_guess:
                continue

            # 4. 廣播猜測
            self.broadcast(f"玩家 {player_name} 猜了: {guess}")
            time.sleep(0.5)

            # 5. 判定結果
            if guess == self.target:
                self.broadcast("\n" + "="*30)
                self.broadcast(f"BOOM!!! 密碼就是 {self.target}！")
                self.broadcast(f"玩家 {player_name} 爆炸了！")
                self.broadcast("="*30)
                
                # 決定贏家：所有活著的人都算贏 (除了爆炸的那位)
                winners = [c['name'] for c in self.clients if c['name'] != player_name]
                
                # 雖然爆炸的人還在 clients 列表裡，但邏輯上他輸了
                if not winners:
                    self.end_game("None")
                elif len(winners) == 1:
                    self.end_game(winners[0])
                else:
                    self.end_game(", ".join(winners))
                break
            
            else:
                # 更新範圍
                if guess < self.target:
                    self.min_val = guess + 1
                else:
                    self.max_val = guess - 1
                
                # 換下一位
                turn_idx = (turn_idx + 1) % len(self.clients)

    def end_game(self, winner):
        print(f"Game Over. Winner: {winner}")
        time.sleep(1)
        
        # 回傳完整名單 (包含中途斷線的人)
        result = {
            "winner": winner,
            "players": self.player_names
        }
        print(f"GAME_RESULT: {json.dumps(result)}")
        
        for c in self.clients:
            try: c['sock'].close()
            except: pass
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