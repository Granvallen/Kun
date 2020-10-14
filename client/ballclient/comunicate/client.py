"""
    by Granvallen
"""

import socket
import json
from ballclient.service import service
import ballclient.service.constants as constants

_socket = None

SOCKET_CACHE = 1024 * 10

def try_again(func):
    def wraper(*args, **kwargs):
        connect_time = 1
        while connect_time <= 30:
            try:
                # print('func=',func(*args, **kwargs))
                return func(*args, **kwargs)
            except Exception:
                print ("connect server failed...connect_time: %s" % connect_time)
                connect_time += 1
        print ("can not connect with server. %s, %s" % args)
        exit(1)
    return wraper



# 初始化 socket 建立连接
@try_again
def connect_socket(ip=None, port=None):
    global _socket
    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _socket.connect((ip, port))

# 入口函数
def start(ip=None, port=None):
    global _socket
    try:
        connect_socket(ip, port) # 连接
        register() # 注册
        # 进入比赛循环
        while True:
            data = _receive()
            if data['msg_name'] == "round":
                message = service.round(data)
                send_dict(message)
            elif data['msg_name'] == "leg_start":
                service.leg_start(data)
            elif data['msg_name'] == "leg_end":
                service.leg_end(data)
            elif data['msg_name'] == "game_over":
                service.game_over(data)
                return
            else:
                print ("invalid msg_name.")
    except socket.error:
        print ("can not connect with server. %s,%s" % (ip, port))
    except Exception as e:
        print ("some error happend. the receive data: ", data, type(data))
    finally:
        if _socket:
            _socket.close()

# 注册参赛队伍信息
def register():
    data = {
        "msg_name": "registration",
        "msg_data": {
            "team_name": constants.team_name,
            "team_id": constants.team_id
        }
    }

    send_dict(data)

# 将python字典转成json字符串发送
def send_dict(data):
    data_str = json.dumps(data)

    _socket.sendall(add_str_len(data_str).encode())

# 用来解析收到json字符串的类
class Receiver(object):
    def __init__(self):
        self._cach = ""

    def __call__(self, *args, **kwargs):
        while True:
            d = _socket.recv(SOCKET_CACHE)
            try:
                if d[:5].isdigit() and d[5] == 123: # 123 是 "{"
                    # print(d)
                    self._cach = ""
                    data = remove_json_num(d)
                    return json.loads(data)
                else: # 如果读取第一次没传完 继续读
                    data = remove_json_num(self._cach + d)
                    return json.loads(data)
            except Exception: # 如果 json.loads发生异常 说明数据还没传完
                self._cach += d


_receive = Receiver()


# 对发送的json字符串进行加工  加上5位字符串长度前缀
def add_str_len(msg_data):
    length = str(len(msg_data))
    index = 5 - len(length)
    if index < 0:
        raise Exception("the return msg data is too long. the length > 99999.")
    return '0' * index + length + msg_data

# 去掉传过来字符串前5个表示长度的字符
def remove_json_num(msg):
    return msg[5:]
