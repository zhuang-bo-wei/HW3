import socket
import threading
import argparse
import json
import random
import time
import sys

# === 遊戲參數 ===
WIDTH = 10
HEIGHT = 20
GRAVITY_MS = 800      # 方塊自動下落速度 (毫秒)
BROADCAST_MS = 100    # 狀態廣播間隔 (毫秒，0.1秒更新一次，確保看得到對手動態)
WIN_LINES = 3         # 勝利條件：消除行數

# 方塊形狀定義 (4x4 矩陣索引)
BRICK_SHAPES = {
    1: [(4, 8, 9, 13), (9, 10, 12, 13)], # S (Green)
    2: [(5, 8, 9, 12), (8, 9, 13, 14)],  # Z (Red)
    3: [(8, 12, 13, 14), (4, 5, 8, 12), (8, 9, 10, 14), (5, 9, 12, 13)], # L (Orange)
    4: [(10, 12, 13, 14), (4, 8, 12, 13), (8, 9, 10, 12), (4, 5, 9, 13)], # J (Blue)
    5: [(9, 12, 13, 14), (4, 8, 9, 12), (8, 9, 10, 13), (5, 8, 9, 13)],   # T (Purple)
    6: [(8, 9, 12, 13)], # O (Yellow)
    7: [(12, 13, 14, 15), (1, 5, 9, 13)] # I (Cyan)
}

# === 輔助函式: RLE 壓縮 (減少傳輸量) ===
def board_to_rle(board):
    parts = []
    for row in board:
        if not row:
            parts.append("")
            continue
        cur = row[0]
        cnt = 1
        out = []
        for cell in row[1:]:
            if cell == cur:
                cnt += 1
            else:
                out.append(f"{cnt}{cur}" if cnt > 1 else f"{cur}")
                cur = cell
                cnt = 1
        out.append(f"{cnt}{cur}" if cnt > 1 else f"{cur}")
        parts.append('.'.join(out))
    return '|'.join(parts)

def get_brick_coords(brick_id, state, offset_x, offset_y):
    shapes = BRICK_SHAPES.get(brick_id, [(0, 1, 2, 3)])
    current_shape = shapes[state % len(shapes)]
    coords = []
    for idx in current_shape:
        x = (idx % 4) + offset_x
        y = (idx // 4) + offset_y
        coords.append((x, y))
    return coords

# === 核心邏輯: 單人俄羅斯方塊引擎 ===
class TetrisEngine:
    def __init__(self, seed):
        self.board = [[0] * WIDTH for _ in range(HEIGHT)]
        self.score = 0
        self.total_lines = 0 # 累計消除行數
        self.game_over = False
        self.win = False     # 是否達成勝利條件
        
        # 7-bag 隨機生成器
        self.rng = random.Random(seed)
        self.bag = []
        
        self.active_piece = None
        self.next_piece = self._get_next_piece()
        self.spawn_piece()

    def _fill_bag(self):
        self.bag = [1, 2, 3, 4, 5, 6, 7]
        self.rng.shuffle(self.bag)

    def _get_next_piece(self):
        if not self.bag:
            self._fill_bag()
        return self.bag.pop(0)

    def spawn_piece(self):
        self.active_piece = {
            'id': self.next_piece,
            'state': 0,
            'x': 3,
            'y': 0
        }
        self.next_piece = self._get_next_piece()
        # 生成即碰撞 -> Game Over
        if self.check_collision():
            self.game_over = True

    def check_collision(self, dx=0, dy=0, rotate=0):
        if not self.active_piece: return False
        
        new_x = self.active_piece['x'] + dx
        new_y = self.active_piece['y'] + dy
        new_state = self.active_piece['state'] + rotate
        
        coords = get_brick_coords(self.active_piece['id'], new_state, new_x, new_y)
        
        for cx, cy in coords:
            if cx < 0 or cx >= WIDTH or cy >= HEIGHT:
                return True
            if cy >= 0 and self.board[cy][cx] != 0:
                return True
        return False

    def lock_piece(self):
        coords = get_brick_coords(self.active_piece['id'], self.active_piece['state'], 
                                  self.active_piece['x'], self.active_piece['y'])
        for cx, cy in coords:
            if 0 <= cy < HEIGHT and 0 <= cx < WIDTH:
                self.board[cy][cx] = self.active_piece['id']
        
        self.check_lines()
        self.spawn_piece()

    def check_lines(self):
        lines_to_clear = []
        for y in range(HEIGHT):
            if all(self.board[y]):
                lines_to_clear.append(y)
        
        count = len(lines_to_clear)
        if count > 0:
            # 移除滿行
            for y in sorted(lines_to_clear, reverse=True):
                del self.board[y]
                self.board.insert(0, [0] * WIDTH)
            
            self.total_lines += count
            self.score += count * 100 * count
            
            # [關鍵修改] 檢查勝利條件：先消 3 行者勝
            if self.total_lines >= WIN_LINES:
                self.win = True
                self.game_over = True

    def move(self, action):
        if self.game_over: return
        
        if action == 'LEFT':
            if not self.check_collision(dx=-1): self.active_piece['x'] -= 1
        elif action == 'RIGHT':
            if not self.check_collision(dx=1): self.active_piece['x'] += 1
        elif action == 'ROTATE':
            if not self.check_collision(rotate=1): self.active_piece['state'] += 1
        elif action == 'DOWN':
            if not self.check_collision(dy=1):
                self.active_piece['y'] += 1
            else:
                self.lock_piece()
        elif action == 'DROP':
            while not self.check_collision(dy=1):
                self.active_piece['y'] += 1
            self.lock_piece()

# === 遊戲伺服器 ===
class GameServer:
    def __init__(self, port, expected_players):
        self.port = port
        self.expected_players = expected_players
        self.server_socket = None
        self.clients = [] # [{'sock':..., 'engine':..., 'name':...}]
        self.running = True
        self.seed = random.randint(0, 999999) # 共用種子確保方塊序列相同

    def start(self):
        print(f"Tetris Server starting on port {self.port}...")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(self.expected_players)

        # 等待玩家
        while len(self.clients) < self.expected_players:
            conn, addr = self.server_socket.accept()
            name = conn.recv(1024).decode().strip()
            print(f"Player {name} connected")
            
            engine = TetrisEngine(self.seed)
            self.clients.append({'sock': conn, 'engine': engine, 'name': name})
            
            self.broadcast_system(f"Waiting: {len(self.clients)}/{self.expected_players}")

        print("Game Starting!")
        self.game_loop()

    def broadcast_system(self, msg):
        payload = json.dumps({'type': 'SYSTEM', 'msg': msg}) + '\n'
        for c in self.clients:
            try: c['sock'].sendall(payload.encode())
            except: pass

    def broadcast_state(self):
        """廣播所有玩家的狀態"""
        states = []
        for c in self.clients:
            engine = c['engine']
            state = {
                'name': c['name'],
                'board': board_to_rle(engine.board), # 壓縮棋盤
                'lines': engine.total_lines,
                'target': WIN_LINES,
                'game_over': engine.game_over,
                'win': engine.win,
                'active': engine.active_piece
            }
            states.append(state)
        
        payload = json.dumps({'type': 'STATE', 'players': states}) + '\n'
        for c in self.clients:
            try: c['sock'].sendall(payload.encode())
            except: pass

    def game_loop(self):
        # 啟動輸入監聽
        for idx, client in enumerate(self.clients):
            t = threading.Thread(target=self.handle_input, args=(idx,))
            t.daemon = True
            t.start()

        last_tick = time.time()
        last_broadcast = time.time()
        
        while self.running:
            current_time = time.time()
            
            # 1. 處理重力 (自然下落)
            if current_time - last_tick > (GRAVITY_MS / 1000.0):
                for c in self.clients:
                    if not c['engine'].game_over:
                        c['engine'].move('DOWN')
                last_tick = current_time
            
            # 2. 定期廣播狀態 (實現每秒更新對手狀態)
            if current_time - last_broadcast > (BROADCAST_MS / 1000.0):
                self.broadcast_state()
                last_broadcast = current_time
            
            # 3. 檢查勝負條件
            # 條件 A: 有人達到目標行數 -> 獲勝
            winner = None
            for c in self.clients:
                if c['engine'].win:
                    winner = c['name']
                    break
            
            # 條件 B: 有人堆到頂死掉 -> 對手獲勝
            if not winner:
                alive = [c for c in self.clients if not c['engine'].game_over]
                if len(alive) < len(self.clients): # 有人死掉了
                    if len(alive) == 1:
                        winner = alive[0]['name'] # 活著的人贏
                    elif len(alive) == 0:
                        winner = "Draw" # 都死了
            
            if winner:
                self.end_game(winner)
                break
            
            time.sleep(0.01) # 避免 CPU 滿載

    def handle_input(self, player_idx):
        conn = self.clients[player_idx]['sock']
        engine = self.clients[player_idx]['engine']
        while self.running:
            try:
                data = conn.recv(1024).decode()
                if not data: break
                for line in data.split('\n'):
                    if not line: continue
                    try:
                        cmd = json.loads(line)
                        if cmd['type'] == 'INPUT':
                            engine.move(cmd['action'])
                    except: pass
            except: break

    def end_game(self, winner):
        print(f"Game Over. Winner: {winner}")
        self.broadcast_state() # 發送最後狀態
        payload = json.dumps({'type': 'GAME_OVER', 'winner': winner}) + '\n'
        for c in self.clients:
            try:
                c['sock'].sendall(payload.encode())
                c['sock'].close()
            except: pass
        
        # [關鍵] 輸出標準結果供 Lobby 讀取
        result = {
            "winner": winner,
            "players": [c['name'] for c in self.clients]
        }
        print(f"GAME_RESULT: {json.dumps(result)}")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--player_count', type=int, default=2)
    args = parser.parse_args()

    server = GameServer(args.port, args.player_count)
    server.start()