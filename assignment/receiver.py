"""
URP Receiver Implementation
实现基于UDP的可靠传输协议接收方
"""
import socket
import sys
import time
import threading
import segment

# 段类型
SEGMENT_DATA = segment.SEGMENT_DATA
SEGMENT_ACK = segment.SEGMENT_ACK
SEGMENT_SYN = segment.SEGMENT_SYN
SEGMENT_FIN = segment.SEGMENT_FIN

# 状态常量
STATE_CLOSED = 0
STATE_ESTABLISHED = 1
STATE_TIME_WAIT = 2


class URPReceiver:
    """URP接收方实现"""
    
    def __init__(self, receiver_port, sender_port, output_filename, max_win):
        """
        初始化接收方
        
        Args:
            receiver_port: 接收方端口
            sender_port: 发送方端口
            output_filename: 输出文件名
            max_win: 最大窗口大小（未使用，但保留参数）
        """
        self.receiver_port = receiver_port
        self.sender_port = sender_port
        self.output_filename = output_filename
        self.max_win = max_win
        
        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', receiver_port))
        self.sock.settimeout(0.1)
        
        # 协议状态
        self.state = STATE_CLOSED
        self.expected_seq = None  # 期望的下一个序列号
        self.isn = None  # 初始序列号
        
        # 接收缓冲区（用于乱序段）
        self.buffer = {}  # {seq_num: payload}
        self.received_bytes = set()  # 已接收的字节范围（用于去重）
        
        # 文件写入
        self.file = None
        
        # 日志
        self.log_entries = []
        self.start_time = None
        
        # 统计信息
        self.stats = {
            'original_data_received': 0,
            'total_data_received': 0,
            'original_segments_received': 0,
            'total_segments_received': 0,
            'corrupted_segments_discarded': 0,
            'duplicate_segments_received': 0,
            'total_acks_sent': 0,
            'duplicate_acks_sent': 0
        }
    
    def log(self, direction, status, segment_type, seq_num, payload_len):
        """记录日志"""
        if self.start_time is None:
            return
        elapsed = (time.time() - self.start_time) * 1000  # 转换为毫秒
        type_name = segment.get_segment_type_name(segment_type)
        self.log_entries.append(
            f"{direction}  {status:3s}  {elapsed:7.2f}  {type_name:4s}  {seq_num:5d}  {payload_len:5d}\n"
        )
    
    def send_ack(self, ack_num):
        """
        发送ACK
        
        Args:
            ack_num: 确认号
        """
        seg = segment.create_segment(ack_num, SEGMENT_ACK)
        try:
            self.sock.sendto(seg, ('localhost', self.sender_port))
            self.log('snd', 'ok', SEGMENT_ACK, ack_num, 0)
            self.stats['total_acks_sent'] += 1
        except Exception as e:
            print(f"Send ACK error: {e}")
    
    def is_duplicate(self, seq_num, payload_len):
        """检查是否是重复段"""
        for i in range(seq_num, seq_num + payload_len):
            if i in self.received_bytes:
                return True
        return False
    
    def mark_received(self, seq_num, payload_len):
        """标记字节为已接收"""
        for i in range(seq_num, seq_num + payload_len):
            self.received_bytes.add(i)
    
    def write_continuous_data(self):
        """写入连续的可用数据到文件"""
        while self.expected_seq in self.buffer:
            payload = self.buffer[self.expected_seq]
            del self.buffer[self.expected_seq]
            
            # 写入文件
            if self.file:
                self.file.write(payload)
                self.file.flush()
            
            # 更新期望序列号
            self.expected_seq += len(payload)
    
    def handle_data_segment(self, seq_num, payload):
        """处理DATA段"""
        payload_len = len(payload)
        
        # 检查是否是重复段（在标记之前检查）
        is_dup = self.is_duplicate(seq_num, payload_len)
        
        if is_dup:
            self.stats['duplicate_segments_received'] += 1
            # 发送重复ACK
            self.send_ack(self.expected_seq)
            self.stats['duplicate_acks_sent'] += 1
            return
        
        # 标记为已接收
        self.mark_received(seq_num, payload_len)
        
        if seq_num == self.expected_seq:
            # 按序到达
            if self.file:
                self.file.write(payload)
                self.file.flush()
            
            self.stats['original_data_received'] += len(payload)
            self.stats['total_data_received'] += len(payload)
            self.stats['original_segments_received'] += 1
            self.stats['total_segments_received'] += 1
            
            # 更新期望序列号
            self.expected_seq += payload_len
            
            # 发送ACK
            self.send_ack(self.expected_seq)
            
            # 检查缓冲区中是否有连续的数据
            self.write_continuous_data()
        else:
            # 乱序到达
            if seq_num > self.expected_seq:
                # 未来的段，缓存
                self.buffer[seq_num] = payload
                self.stats['total_data_received'] += len(payload)
                self.stats['total_segments_received'] += 1
            # 发送重复ACK（期望的序列号）
            self.send_ack(self.expected_seq)
            self.stats['duplicate_acks_sent'] += 1
    
    def run(self):
        """运行接收方"""
        # 打开输出文件
        try:
            self.file = open(self.output_filename, 'wb')
        except Exception as e:
            print(f"Error opening output file: {e}")
            return
        
        # 等待SYN
        syn_received = False
        while not syn_received:
            try:
                data, addr = self.sock.recvfrom(2048)
                
                # 解析段
                parsed = segment.parse_segment(data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    # 校验失败，丢弃
                    self.stats['corrupted_segments_discarded'] += 1
                    self.log('rcv', 'cor', seg_type, seq_num, 0)
                    continue
                
                if seg_type == SEGMENT_SYN:
                    # 收到SYN
                    self.isn = seq_num
                    self.expected_seq = seq_num + 1
                    self.state = STATE_ESTABLISHED
                    syn_received = True
                    self.start_time = time.time()
                    
                    # 记录日志
                    self.log('rcv', 'ok', SEGMENT_SYN, seq_num, 0)
                    
                    # 发送ACK
                    self.send_ack(self.expected_seq)
                    break
            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving SYN: {e}")
                return
        
        # 接收数据
        while self.state == STATE_ESTABLISHED:
            try:
                data, addr = self.sock.recvfrom(2048)
                
                # 解析段
                parsed = segment.parse_segment(data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    # 校验失败，丢弃
                    self.stats['corrupted_segments_discarded'] += 1
                    self.log('rcv', 'cor', seg_type, seq_num, len(payload) if seg_type == SEGMENT_DATA else 0)
                    continue
                
                # 记录日志
                if seg_type == SEGMENT_DATA:
                    self.log('rcv', 'ok', SEGMENT_DATA, seq_num, len(payload))
                elif seg_type == SEGMENT_FIN:
                    self.log('rcv', 'ok', SEGMENT_FIN, seq_num, 0)
                
                if seg_type == SEGMENT_DATA:
                    # 处理DATA段
                    self.handle_data_segment(seq_num, payload)
                elif seg_type == SEGMENT_FIN:
                    # 收到FIN
                    # 发送ACK
                    fin_ack = seq_num + 1
                    self.send_ack(fin_ack)
                    
                    # 进入TIME_WAIT状态
                    self.state = STATE_TIME_WAIT
                    time.sleep(2.0)  # TIME_WAIT 2秒
                    self.state = STATE_CLOSED
                    break
            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")
                break
        
        # 关闭文件
        if self.file:
            self.file.close()
        
        # 关闭socket
        self.sock.close()
        
        # 写入日志
        self.write_log()
    
    def write_log(self):
        """写入日志文件"""
        with open('receiver_log.txt', 'w') as f:
            for entry in self.log_entries:
                f.write(entry)
            
            # 写入统计信息
            f.write(f"Original data received:         {self.stats['original_data_received']:5d}\n")
            f.write(f"Total data received:           {self.stats['total_data_received']:5d}\n")
            f.write(f"Original segments received:    {self.stats['original_segments_received']:5d}\n")
            f.write(f"Total segments received:       {self.stats['total_segments_received']:5d}\n")
            f.write(f"Corrupted segments discarded:  {self.stats['corrupted_segments_discarded']:5d}\n")
            f.write(f"Duplicate segments received:   {self.stats['duplicate_segments_received']:5d}\n")
            f.write(f"Total acks sent:              {self.stats['total_acks_sent']:5d}\n")
            f.write(f"Duplicate acks sent:          {self.stats['duplicate_acks_sent']:5d}\n")


def main():
    if len(sys.argv) != 5:
        print("Usage: python3 receiver.py receiver_port sender_port output_filename max_win")
        sys.exit(1)
    
    receiver_port = int(sys.argv[1])
    sender_port = int(sys.argv[2])
    output_filename = sys.argv[3]
    max_win = int(sys.argv[4])
    
    receiver = URPReceiver(receiver_port, sender_port, output_filename, max_win)
    receiver.run()


if __name__ == '__main__':
    main()

