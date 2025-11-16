"""
URP Sender Implementation
实现基于UDP的可靠传输协议发送方
"""
import socket
import sys
import time
import threading
import struct
import segment
import plc

# 段类型
SEGMENT_DATA = segment.SEGMENT_DATA
SEGMENT_ACK = segment.SEGMENT_ACK
SEGMENT_SYN = segment.SEGMENT_SYN
SEGMENT_FIN = segment.SEGMENT_FIN

# 状态常量
STATE_CLOSED = 0
STATE_SYN_SENT = 1
STATE_ESTABLISHED = 2
STATE_FIN_SENT = 3


class URPSender:
    """URP发送方实现"""
    
    def __init__(self, sender_port, receiver_port, filename, max_win, rto, 
                 flp, rlp, fcp, rcp):
        """
        初始化发送方
        
        Args:
            sender_port: 发送方端口
            receiver_port: 接收方端口
            filename: 要发送的文件名
            max_win: 最大窗口大小（字节）
            rto: 超时重传时间（秒）
            flp: forward loss probability
            rlp: reverse loss probability
            fcp: forward corruption probability
            rcp: reverse corruption probability
        """
        self.sender_port = sender_port
        self.receiver_port = receiver_port
        self.filename = filename
        self.max_win = max_win
        self.rto = rto
        
        # PLC模块
        self.plc = plc.PLC(flp, rlp, fcp, rcp)
        
        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', sender_port))
        self.sock.settimeout(0.1)  # 用于接收时的超时
        
        # 协议状态
        self.state = STATE_CLOSED
        self.isn = None  # Initial Sequence Number
        self.next_seq = None  # 下一个要发送的序列号
        self.base = None  # 窗口左边界（最小的未确认序列号）
        
        # 滑动窗口
        self.window = {}  # {seq_num: (segment_data, payload_len, send_time)}
        self.unacked_bytes = 0  # 未确认的字节数
        
        # 文件读取
        self.file = None
        self.file_size = 0
        self.file_pos = 0  # 已读取的文件位置
        
        # 计时器
        self.timer = None
        self.timer_lock = threading.Lock()
        self.timer_running = False
        self.oldest_unacked_seq = None
        
        # 快速重传
        self.dup_ack_count = {}  # {ack_num: count}
        self.last_ack = None
        
        # 日志
        self.log_entries = []
        self.start_time = None
        
        # 统计信息
        self.stats = {
            'original_data_sent': 0,
            'total_data_sent': 0,
            'original_segments_sent': 0,
            'total_segments_sent': 0,
            'timeout_retransmissions': 0,
            'fast_retransmissions': 0,
            'duplicate_acks_received': 0,
            'corrupted_acks_discarded': 0,
            'plc_forward_segments_dropped': 0,
            'plc_forward_segments_corrupted': 0,
            'plc_reverse_segments_dropped': 0,
            'plc_reverse_segments_corrupted': 0
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
    
    def send_segment(self, seq_num, segment_type, payload=b''):
        """
        发送段（通过PLC处理）
        
        Returns:
            tuple: (sent, status) - sent表示是否实际发送，status是状态
        """
        seg = segment.create_segment(seq_num, segment_type, payload)
        
        # 通过PLC处理
        processed_seg, status = self.plc.process_forward(seg)
        
        if status == 'drp':
            # 丢包，不发送
            self.stats['plc_forward_segments_dropped'] += 1
            self.log('snd', 'drp', segment_type, seq_num, len(payload))
            return (False, 'drp')
        
        # 发送（可能已损坏）
        if processed_seg:
            try:
                self.sock.sendto(processed_seg, ('localhost', self.receiver_port))
                self.log('snd', status, segment_type, seq_num, len(payload))
                
                if segment_type == SEGMENT_DATA:
                    self.stats['original_data_sent'] += len(payload)
                    self.stats['total_data_sent'] += len(payload)
                    self.stats['original_segments_sent'] += 1
                    self.stats['total_segments_sent'] += 1
                else:
                    self.stats['total_segments_sent'] += 1
                
                if status == 'cor':
                    self.stats['plc_forward_segments_corrupted'] += 1
                
                return (True, status)
            except Exception as e:
                print(f"Send error: {e}")
                return (False, 'drp')
        
        return (False, 'drp')
    
    def start_timer(self, seq_num):
        """启动计时器（单计时器，只跟踪oldest unacked）"""
        with self.timer_lock:
            if not self.timer_running:
                self.oldest_unacked_seq = seq_num
                self.timer_running = True
                threading.Thread(target=self._timer_thread, daemon=True).start()
    
    def stop_timer(self):
        """停止计时器"""
        with self.timer_lock:
            self.timer_running = False
    
    def _timer_thread(self):
        """计时器线程"""
        while self.timer_running:
            time.sleep(self.rto)
            with self.timer_lock:
                if not self.timer_running:
                    break
                if self.oldest_unacked_seq is not None and self.oldest_unacked_seq in self.window:
                    # 超时重传
                    seg_data, payload_len, _ = self.window[self.oldest_unacked_seq]
                    seq_num, seg_type, payload, _ = segment.parse_segment(seg_data)
                    
                    # 重传
                    self.send_segment(seq_num, seg_type, payload)
                    self.stats['timeout_retransmissions'] += 1
                    self.stats['total_segments_sent'] += 1
                    if seg_type == SEGMENT_DATA:
                        self.stats['total_data_sent'] += len(payload)
                    
                    # 更新发送时间
                    self.window[self.oldest_unacked_seq] = (
                        seg_data, payload_len, time.time()
                    )
    
    def handle_ack(self, ack_num):
        """处理ACK"""
        if ack_num <= self.base:
            # 旧的或重复的ACK
            if ack_num == self.base:
                self.stats['duplicate_acks_received'] += 1
                # 快速重传检测
                self.dup_ack_count[ack_num] = self.dup_ack_count.get(ack_num, 0) + 1
                if self.dup_ack_count[ack_num] == 3:
                    # 快速重传
                    if self.base in self.window:
                        seg_data, payload_len, _ = self.window[self.base]
                        seq_num, seg_type, payload, _ = segment.parse_segment(seg_data)
                        self.send_segment(seq_num, seg_type, payload)
                        self.stats['fast_retransmissions'] += 1
                        self.stats['total_segments_sent'] += 1
                        if seg_type == SEGMENT_DATA:
                            self.stats['total_data_sent'] += len(payload)
                        self.window[self.base] = (seg_data, payload_len, time.time())
            return
        
        # 新的ACK，更新窗口
        acked_seqs = []
        for seq in sorted(self.window.keys()):
            seg_data, payload_len, _ = self.window[seq]
            parsed = segment.parse_segment(seg_data)
            if parsed:
                seg_seq, seg_type, _, _ = parsed
                # 计算该段的结束序列号
                if seg_type == SEGMENT_DATA:
                    end_seq = seg_seq + payload_len
                else:
                    end_seq = seg_seq + 1  # SYN/FIN消耗1个序列号
                
                if end_seq <= ack_num:
                    acked_seqs.append(seq)
                    if seg_type == SEGMENT_DATA:
                        self.unacked_bytes -= payload_len
                    # SYN/FIN不占用unacked_bytes（因为它们没有payload）
        
        # 移除已确认的段
        for seq in acked_seqs:
            del self.window[seq]
        
        # 更新base
        if acked_seqs:
            self.base = ack_num
            # 清除旧的重复ACK计数
            self.dup_ack_count.clear()
            # 更新oldest unacked
            if self.window:
                self.oldest_unacked_seq = min(self.window.keys())
                # 重启计时器
                if not self.timer_running:
                    self.start_timer(self.oldest_unacked_seq)
            else:
                self.oldest_unacked_seq = None
                self.stop_timer()
        
        self.last_ack = ack_num
    
    def receive_loop(self):
        """接收循环"""
        while self.state != STATE_CLOSED:
            try:
                data, addr = self.sock.recvfrom(2048)
                
                # 通过PLC处理反向段
                processed_data, status = self.plc.process_reverse(data)
                
                if status == 'drp':
                    self.stats['plc_reverse_segments_dropped'] += 1
                    continue
                
                if not processed_data:
                    continue
                
                # 解析段
                parsed = segment.parse_segment(processed_data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    # 校验失败
                    self.stats['corrupted_acks_discarded'] += 1
                    self.log('rcv', 'cor', seg_type, seq_num, 0)
                    continue
                
                # 记录日志
                self.log('rcv', status, seg_type, seq_num, 0)
                if status == 'cor':
                    self.stats['plc_reverse_segments_corrupted'] += 1
                
                # 处理ACK
                if seg_type == SEGMENT_ACK:
                    if self.state == STATE_SYN_SENT:
                        # 连接建立ACK
                        if seq_num == self.isn + 1:
                            self.state = STATE_ESTABLISHED
                            self.base = self.isn + 1
                            self.next_seq = self.isn + 1
                            self.stop_timer()
                    elif self.state == STATE_ESTABLISHED:
                        # 数据ACK
                        self.handle_ack(seq_num)
                    elif self.state == STATE_FIN_SENT:
                        # FIN的ACK
                        if seq_num == self.next_seq:
                            self.state = STATE_CLOSED
                            self.stop_timer()
                            break
            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receive error: {e}")
                break
    
    def send_data(self):
        """发送数据（在ESTABLISHED状态下）"""
        while self.state == STATE_ESTABLISHED:
            # 检查是否所有数据已发送且已确认
            if self.file_pos >= self.file_size and len(self.window) == 0:
                # 所有数据已确认，发送FIN
                self.state = STATE_FIN_SENT
                fin_seq = self.next_seq
                self.send_segment(fin_seq, SEGMENT_FIN)
                self.window[fin_seq] = (
                    segment.create_segment(fin_seq, SEGMENT_FIN),
                    0, time.time()
                )
                self.next_seq += 1
                self.start_timer(fin_seq)
                break
            
            # 检查窗口空间
            available_win = self.max_win - self.unacked_bytes
            
            if available_win > 0 and self.file_pos < self.file_size:
                # 可以发送数据
                payload_size = min(segment.MSS, available_win, self.file_size - self.file_pos)
                
                if payload_size > 0:
                    # 读取数据
                    self.file.seek(self.file_pos)
                    payload = self.file.read(payload_size)
                    
                    if len(payload) > 0:
                        # 发送DATA段
                        seq_num = self.next_seq
                        seg = segment.create_segment(seq_num, SEGMENT_DATA, payload)
                        
                        # 保存到窗口
                        self.window[seq_num] = (seg, len(payload), time.time())
                        self.unacked_bytes += len(payload)
                        
                        # 发送
                        self.send_segment(seq_num, SEGMENT_DATA, payload)
                        
                        # 更新序列号和文件位置
                        self.next_seq += len(payload)
                        self.file_pos += len(payload)
                        
                        # 启动计时器（如果还没有）
                        if not self.timer_running:
                            self.start_timer(seq_num)
                        elif self.oldest_unacked_seq is None or seq_num < self.oldest_unacked_seq:
                            self.oldest_unacked_seq = seq_num
                    else:
                        # 文件读取结束
                        break
                else:
                    # 窗口满，等待ACK
                    time.sleep(0.01)
            else:
                # 窗口满或文件已读完，等待ACK
                time.sleep(0.01)
    
    def run(self):
        """运行发送方"""
        # 打开文件
        try:
            self.file = open(self.filename, 'rb')
            self.file.seek(0, 2)  # 移动到文件末尾
            self.file_size = self.file.tell()
            self.file.seek(0)  # 回到开头
        except Exception as e:
            print(f"Error opening file: {e}")
            return
        
        # 启动接收线程
        recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        recv_thread.start()
        
        # 连接建立
        self.state = STATE_SYN_SENT
        self.isn = 1000  # 简单的ISN选择
        self.base = self.isn
        self.next_seq = self.isn
        
        self.start_time = time.time()
        
        # 发送SYN
        self.send_segment(self.isn, SEGMENT_SYN)
        self.window[self.isn] = (
            segment.create_segment(self.isn, SEGMENT_SYN),
            0, time.time()
        )
        self.next_seq = self.isn + 1
        self.start_timer(self.isn)
        
        # 等待连接建立
        while self.state == STATE_SYN_SENT:
            time.sleep(0.01)
        
        if self.state != STATE_ESTABLISHED:
            print("Connection establishment failed")
            return
        
        # 发送数据
        self.send_data()
        
        # 等待连接终止
        while self.state == STATE_FIN_SENT:
            time.sleep(0.01)
        
        # 关闭文件
        if self.file:
            self.file.close()
        
        # 关闭socket
        self.sock.close()
        
        # 写入日志
        self.write_log()
    
    def write_log(self):
        """写入日志文件"""
        with open('sender_log.txt', 'w') as f:
            for entry in self.log_entries:
                f.write(entry)
            
            # 写入统计信息
            f.write(f"Original data sent:            {self.stats['original_data_sent']:5d}\n")
            f.write(f"Total data sent:               {self.stats['total_data_sent']:5d}\n")
            f.write(f"Original segments sent:        {self.stats['original_segments_sent']:5d}\n")
            f.write(f"Total segments sent:           {self.stats['total_segments_sent']:5d}\n")
            f.write(f"Timeout retransmissions:       {self.stats['timeout_retransmissions']:5d}\n")
            f.write(f"Fast retransmissions:          {self.stats['fast_retransmissions']:5d}\n")
            f.write(f"Duplicate acks received:       {self.stats['duplicate_acks_received']:5d}\n")
            f.write(f"Corrupted acks discarded:      {self.stats['corrupted_acks_discarded']:5d}\n")
            f.write(f"PLC forward segments dropped:  {self.stats['plc_forward_segments_dropped']:5d}\n")
            f.write(f"PLC forward segments corrupted: {self.stats['plc_forward_segments_corrupted']:5d}\n")
            f.write(f"PLC reverse segments dropped:  {self.stats['plc_reverse_segments_dropped']:5d}\n")
            f.write(f"PLC reverse segments corrupted: {self.stats['plc_reverse_segments_corrupted']:5d}\n")


def main():
    if len(sys.argv) != 10:
        print("Usage: python3 sender.py sender_port receiver_port filename max_win rto flp rlp fcp rcp")
        sys.exit(1)
    
    sender_port = int(sys.argv[1])
    receiver_port = int(sys.argv[2])
    filename = sys.argv[3]
    max_win = int(sys.argv[4])
    rto = float(sys.argv[5])
    flp = float(sys.argv[6])
    rlp = float(sys.argv[7])
    fcp = float(sys.argv[8])
    rcp = float(sys.argv[9])
    
    sender = URPSender(sender_port, receiver_port, filename, max_win, rto,
                       flp, rlp, fcp, rcp)
    sender.run()


if __name__ == '__main__':
    main()

