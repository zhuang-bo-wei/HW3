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
        self.running = True
        
        # 用於控制輸入的 Event
        self.input_event = threading.Event()
        self.prompt_text = ""

    def start(self):
        try:
            print(f"Connecting to server at {self.server_ip}:{self.server_port}...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))
            
            # 1. 發送名字
            self.sock.sendall(self.username.encode())
            
            # 2. 啟動接收執行緒
            recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
            recv_thread.start()
            
            # 3. 主執行緒負責處理輸入
            self.input_loop()
            
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.cleanup()

    def receive_loop(self):
        """持續接收伺服器訊息"""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data: break
                
                # 處理黏包 (簡單用換行分割)
                messages = data.decode().split('\n')
                for msg in messages:
                    if not msg: continue
                    
                    # 檢查特殊指令
                    if msg.startswith("INPUT:"):
                        # Server 要求輸入，設定提示文字並解鎖輸入執行緒
                        self.prompt_text = msg[6:] # 去掉 "INPUT:"
                        self.input_event.set()
                    else:
                        # 普通訊息直接印出
                        print(msg)
                        
            except:
                break
        
        self.running = False
        print("\nDisconnected from server. Press Enter to exit.")
        self.input_event.set() # 確保主執行緒能退出

    def input_loop(self):
        """等待輸入訊號"""
        while self.running:
            # 等待 Server 叫我輸入
            self.input_event.wait()
            
            if not self.running: break
            
            # 顯示提示並讀取輸入
            try:
                user_input = input(f"{self.prompt_text}").strip()
                
                if self.sock:
                    self.sock.sendall(user_input.encode())
            except EOFError:
                break
                
            # 輸入完畢，重置 Event，繼續等待下次叫號
            self.input_event.clear()

    def cleanup(self):
        self.running = False
        if self.sock:
            self.sock.close()
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--connect', type=str, required=True)
    parser.add_argument('--username', type=str, required=True)
    args = parser.parse_args()

    client = GameClient(args.connect, args.username)
    client.start()