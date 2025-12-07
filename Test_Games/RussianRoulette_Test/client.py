import socket
import argparse
import threading
import sys

class GameClient:
    def __init__(self, connect_addr, username):
        self.server_ip, self.server_port = connect_addr.split(':')
        self.server_port = int(self.server_port)
        self.username = username
        self.sock = None
        self.is_running = True

    def start(self):
        try:
            print(f"Connecting to server at {self.server_ip}:{self.server_port}...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))
            
            # 1. 發送使用者名稱 (協議第一步)
            self.sock.sendall(self.username.encode('utf-8'))
            
            # 2. 啟動接收執行緒 (負責顯示伺服器訊息)
            recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
            recv_thread.start()
            
            # 3. 主執行緒處理輸入
            self.input_loop()
            
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.cleanup()

    def receive_loop(self):
        """持續接收伺服器訊息並顯示"""
        while self.is_running:
            try:
                data = self.sock.recv(4096)
                if not data: break
                message = data.decode('utf-8').strip()
                
                # 檢查是否為特殊指令
                if message == "ACTION:YOUR_TURN":
                    print("\n>>> 輪到你了! 請按 [Enter] 鍵扣下板機 <<<")
                else:
                    # 普通訊息直接印出
                    print(message)
                    
            except:
                break
        self.is_running = False
        print("\nDisconnected from server. Press Enter to exit.")

    def input_loop(self):
        """等待使用者輸入"""
        print("Waiting for game to start...")
        while self.is_running:
            try:
                # 這裡的 input 會阻塞，直到使用者按下 Enter
                user_input = input()
                
                if not self.is_running: break

                # 只有在輪到自己時發送的資料才有意義，
                # 但為了簡化，我們任何時候按 Enter 都發送一個訊號給 Server
                self.sock.sendall(b"FIRE") 
                
            except EOFError:
                break
                
    def cleanup(self):
        self.is_running = False
        if self.sock:
            self.sock.close()
        sys.exit(0)

if __name__ == "__main__":
    # 使用標準參數解析
    parser = argparse.ArgumentParser(description="Russian Roulette Game Client")
    parser.add_argument('--connect', type=str, required=True, help='Server IP:Port (e.g., 127.0.0.1:9001)')
    parser.add_argument('--username', type=str, required=True, help='Player username')
    args = parser.parse_args()

    client = GameClient(args.connect, args.username)
    client.start()