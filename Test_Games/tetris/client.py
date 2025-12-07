import pygame
import socket
import argparse
import threading
import json
import sys

# === UI 設定 ===
CELL_SIZE = 30
BOARD_W, BOARD_H = 10, 20
PADDING = 20
WINDOW_W = (BOARD_W * CELL_SIZE * 2) + (PADDING * 3)
WINDOW_H = (BOARD_H * CELL_SIZE) + (PADDING * 2)+ 60

COLORS = {
    0: (20, 20, 30),      # 背景 (Empty)
    1: (0, 255, 0),       # S
    2: (255, 0, 0),       # Z
    3: (255, 165, 0),     # L
    4: (0, 0, 255),       # J
    5: (128, 0, 128),     # T
    6: (255, 255, 0),     # O
    7: (0, 255, 255),     # I
    'GRID': (40, 40, 50),
    'BORDER': (200, 200, 200),
    'ACTIVE': (200, 200, 200) # 活動方塊邊框
}

# 形狀定義 (用於客戶端繪製)
BRICK_SHAPES = {
    1: [(4, 8, 9, 13), (9, 10, 12, 13)], 
    2: [(5, 8, 9, 12), (8, 9, 13, 14)], 
    3: [(8, 12, 13, 14), (4, 5, 8, 12), (8, 9, 10, 14), (5, 9, 12, 13)], 
    4: [(10, 12, 13, 14), (4, 8, 12, 13), (8, 9, 10, 12), (4, 5, 9, 13)], 
    5: [(9, 12, 13, 14), (4, 8, 9, 12), (8, 9, 10, 13), (5, 8, 9, 13)], 
    6: [(8, 9, 12, 13)], 
    7: [(12, 13, 14, 15), (1, 5, 9, 13)] 
}

class TetrisClient:
    def __init__(self, connect_str, username):
        ip, port = connect_str.split(':')
        self.server_addr = (ip, int(port))
        self.username = username
        self.sock = None
        self.running = True
        
        self.players_state = [] 
        self.winner = None
        
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption(f"Tetris Sprint - {username}")
        self.font = pygame.font.SysFont("Arial", 24)
        self.big_font = pygame.font.SysFont("Arial", 48)

    def connect(self):
        try:
            print(f"Connecting to {self.server_addr}...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(self.server_addr)
            self.sock.sendall(self.username.encode())
            
            t = threading.Thread(target=self.network_loop, daemon=True)
            t.start()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def network_loop(self):
        buf = ""
        while self.running:
            try:
                data = self.sock.recv(4096).decode()
                if not data: break
                
                buf += data
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line: continue
                    self.handle_packet(json.loads(line))
            except Exception as e:
                print(f"Network error: {e}")
                break
        self.running = False

    def handle_packet(self, data):
        ptype = data.get('type')
        if ptype == 'STATE':
            self.players_state = data.get('players', [])
        elif ptype == 'GAME_OVER':
            self.winner = data.get('winner')
            print(f"Game Over! Winner: {self.winner}")

    def send_input(self, action):
        if not self.sock: return
        try:
            payload = json.dumps({'type': 'INPUT', 'action': action}) + '\n'
            self.sock.sendall(payload.encode())
        except: pass

    def parse_rle(self, rle_str):
        board = []
        rows = rle_str.split('|')
        for r_str in rows:
            row = []
            if not r_str: 
                board.append([0]*10)
                continue
            parts = r_str.split('.')
            for p in parts:
                val = int(p[-1])
                count = int(p[:-1]) if len(p) > 1 else 1
                row.extend([val] * count)
            if len(row) < 10: row.extend([0] * (10-len(row)))
            board.append(row[:10])
        return board

    def draw_board(self, offset_x, offset_y, state):
        # 邊框
        color_border = (255, 215, 0) if state.get('win') else COLORS['BORDER']
        pygame.draw.rect(self.screen, color_border, 
                         (offset_x-2, offset_y-2, BOARD_W*CELL_SIZE+4, BOARD_H*CELL_SIZE+4), 2)
        
        # 棋盤
        board = self.parse_rle(state['board'])
        for y in range(BOARD_H):
            for x in range(BOARD_W):
                val = board[y][x]
                color = COLORS.get(val, COLORS[0])
                rect = (offset_x + x*CELL_SIZE, offset_y + y*CELL_SIZE, CELL_SIZE-1, CELL_SIZE-1)
                pygame.draw.rect(self.screen, color, rect)
                if val == 0: 
                    pygame.draw.rect(self.screen, COLORS['GRID'], rect, 1)

        # 活動方塊
        active = state.get('active')
        if active:
            bid = active['id']
            shapes = BRICK_SHAPES.get(bid)
            if shapes:
                shape = shapes[active['state'] % len(shapes)]
                for idx in shape:
                    bx = (idx % 4) + active['x']
                    by = (idx // 4) + active['y']
                    if 0 <= by < BOARD_H and 0 <= bx < BOARD_W:
                        rect = (offset_x + bx*CELL_SIZE, offset_y + by*CELL_SIZE, CELL_SIZE-1, CELL_SIZE-1)
                        # 繪製方塊
                        pygame.draw.rect(self.screen, COLORS.get(bid), rect)
                        # 繪製活動框線 (強調)
                        pygame.draw.rect(self.screen, COLORS['ACTIVE'], rect, 1)

        # 資訊顯示
        name = state['name']
        lines = state['lines']
        target = state['target']
        
        # 名字
        name_surf = self.font.render(f"{name}", True, (255, 255, 255))
        self.screen.blit(name_surf, (offset_x, offset_y - 30))
        
        # 進度 (3/3)
        progress_text = f"Lines: {lines}/{target}"
        color = (0, 255, 0) if lines >= target else (200, 200, 200)
        prog_surf = self.font.render(progress_text, True, color)
        self.screen.blit(prog_surf, (offset_x, offset_y + BOARD_H*CELL_SIZE + 10))

        if state['game_over']:
            status = "WINNER" if state['win'] else "GAME OVER"
            color = (0, 255, 0) if state['win'] else (255, 0, 0)
            text = self.big_font.render(status, True, color)
            self.screen.blit(text, (offset_x + 20, offset_y + 200))

    def run(self):
        if not self.connect(): return

        clock = pygame.time.Clock()
        while self.running:
            self.screen.fill((0, 0, 0))
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and not self.winner:
                    if event.key == pygame.K_LEFT: self.send_input('LEFT')
                    elif event.key == pygame.K_RIGHT: self.send_input('RIGHT')
                    elif event.key == pygame.K_UP: self.send_input('ROTATE')
                    elif event.key == pygame.K_DOWN: self.send_input('DOWN')
                    elif event.key == pygame.K_SPACE: self.send_input('DROP')

            # 繪製所有玩家
            for idx, p_state in enumerate(self.players_state):
                off_x = PADDING + (idx * (BOARD_W * CELL_SIZE + PADDING))
                self.draw_board(off_x, PADDING + 40, p_state)

            if self.winner:
                # 可以在中間顯示大大的 Winner 文字
                pass

            pygame.display.flip()
            clock.tick(60)
        
        self.sock.close()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--connect', required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()

    client = TetrisClient(args.connect, args.username)
    client.run()