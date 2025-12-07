# utils.py
import json
import struct
from config import HEADER_SIZE

# --- 網路通訊工具 ---

def send_message(sock, data):
    """
    使用 Length-Prefixed 協定發送 JSON 訊息。
    """
    try:
        # 1. 序列化 JSON 數據
        json_string = json.dumps(data)
        message = json_string.encode('utf-8')
        
        # 2. 計算長度並創建標頭 (4 bytes, Network Byte Order)
        length = len(message)
        header = struct.pack('!I', length) # '!I' 表示 4-byte unsigned integer, Network Endian
        
        # 3. 發送標頭和訊息
        sock.sendall(header)
        sock.sendall(message)
    except Exception as e:
        print(f"Error sending message: {e}")
        return False
    return True

def receive_message(sock):
    """
    使用 Length-Prefixed 協定接收 JSON 訊息。
    """
    try:
        # 1. 接收標頭 (固定長度)
        header = b''
        while len(header) < HEADER_SIZE:
            chunk = sock.recv(HEADER_SIZE - len(header))
            if not chunk:
                # 連線已關閉
                return None 
            header += chunk

        # 2. 解析長度
        msg_len = struct.unpack('!I', header)[0]
        
        # 3. 接收 Payload 數據
        chunks = []
        bytes_recd = 0
        while bytes_recd < msg_len:
            # 確保不會接收超過所需長度
            chunk = sock.recv(min(msg_len - bytes_recd, 2048)) 
            if not chunk:
                # 資料不足或連線已關閉
                return None 
            chunks.append(chunk)
            bytes_recd += len(chunk)
            
        message = b"".join(chunks)
        
        # 4. 反序列化 JSON
        json_data = json.loads(message.decode('utf-8'))
        return json_data

    except struct.error:
        print("Error: Malformed header received.")
        return None
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON payload.")
        return None
    except Exception as e:
        print(f"Error receiving message: {e}") # 可能是連線被遠端關閉，不一定要印
        return None

# --- 密碼 (待完善) ---

def verify_password(stored_hash, provided_password):
    """驗證密碼。"""
    # 實際實作應使用 password hashing 函式庫
    return stored_hash == provided_password # 暫時比對明碼，待您實作