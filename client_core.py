# client/client_core.py
import socket
import threading
import queue
import time
import sys
import os
# 取得目前檔案 (t2.py) 的絕對路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得上一層目錄 (project_root)
parent_dir = os.path.dirname(current_dir)
# 將上一層目錄加入系統搜尋路徑
sys.path.append(parent_dir)
from config import SERVER_HOST, DEVELOPER_PORT
from utils import send_message, receive_message 

class ClientCore:
    def __init__(self, host, port, user_type='developer'):
        self.host = host
        self.port = port
        self.user_type = user_type # 儲存身分
        self.sock = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self.rx_queue = queue.Queue()
        self.network_thread = threading.Thread(target=self._run_network, daemon=True)

    def start_connection(self):
        """嘗試連線並啟動網路線程"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.is_connected = True
            print(f"Connected to Server at {self.host}:{self.port}")
            
            self.network_thread.start()
            return True, "Connection successful."
        except ConnectionRefusedError:
            print(f"Connection failed: Server at {self.host}:{self.port} is offline.")
            return False, "Connection failed."
        except Exception as e:
            print(f"An unexpected error occurred during connection: {e}")
            return False, f"Error: {e}"

    def disconnect(self):
        """關閉連線和線程"""
        self.stop_event.set()
        if self.sock:
            self.sock.close()
        self.is_connected = False
        print("Disconnected from server.")

    def _run_network(self):
        """網路線程的主迴圈，負責持續接收資料"""
        while not self.stop_event.is_set() and self.is_connected:
            try:
                # 接收訊息 (這裡可能會阻塞)
                message = receive_message(self.sock)
                
                # print(f"Received message: {message}")

                if message is None:
                    # Server 關閉或接收錯誤
                    print("Server disconnected or receive error.")
                    break 
                
                # 將收到的訊息放入佇列
                self.rx_queue.put(message)
                
            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"Network thread error: {e}")
                break
        
        # 結束處理
        self.is_connected = False
        self.sock = None
        # 如果線程意外終止，發送一個特殊訊息通知主程式
        if not self.stop_event.is_set():
             self.rx_queue.put({'type': 'SERVER_DISCONNECTED', 'message': 'Lost connection to server.'})


    def send_request(self, action, data=None):
        if not self.is_connected or not self.sock:
            return False, "Not connected to server."
        
        request = {
            "action": action,
            "user_type": self.user_type, # 2. 修改這裡：使用 self.user_type
            "data": data if data is not None else {}
        }
        
        success = send_message(self.sock, request)
        if not success:
             self.disconnect()
        return success, "Request sent."
        
    def get_received_message(self):
        """主線程從接收佇列中取得訊息"""
        messages = []
        while not self.rx_queue.empty():
            messages.append(self.rx_queue.get_nowait())
        return messages

# 開發者專用的 ClientCore 實例 (使用 DeveloperClientCore 名稱更符合舊程式碼結構)
class DeveloperClientCore(ClientCore):
    def __init__(self):
        super().__init__(SERVER_HOST, DEVELOPER_PORT, user_type='developer')

class PlayerClientCore(ClientCore):
    def __init__(self):
        from config import LOBBY_PORT # 確保有導入 LOBBY_PORT
        super().__init__(SERVER_HOST, LOBBY_PORT, user_type='player')