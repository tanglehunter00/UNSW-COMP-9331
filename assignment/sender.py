
import socket
import sys
import time
import threading
import struct
import random



def CalculateChecksum(data):
    
    checksum = 0
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            word = (data[i] << 8) + data[i + 1]
        else:
            word = (data[i] << 8)
        checksum += word
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
    return (~checksum) & 0xFFFF


def CreateSegment(seq_num, segment_type, payload=b''):
    
    seq_bytes = struct.pack('>H', seq_num)
    
    flags = 0
    if segment_type == 1:
        flags = 0x2000
    elif segment_type == 2:
        flags = 0x4000
    elif segment_type == 3:
        flags = 0x8000
    
    flags_bytes = struct.pack('>H', flags)
    
    temp_segment = seq_bytes + flags_bytes + b'\x00\x00' + payload
    
    checksum = CalculateChecksum(temp_segment)
    checksum_bytes = struct.pack('>H', checksum)
    
    segment_data = seq_bytes + flags_bytes + checksum_bytes + payload
    
    return segment_data


def ParseSegment(segment_data):
    
    if len(segment_data) < 6:
        return None
    
    seq_num = struct.unpack('>H', segment_data[0:2])[0]
    flags_field = struct.unpack('>H', segment_data[2:4])[0]
    received_checksum = struct.unpack('>H', segment_data[4:6])[0]
    
    payload = segment_data[6:]
    
    if flags_field & 0x2000:
        segment_type = 1
    elif flags_field & 0x4000:
        segment_type = 2
    elif flags_field & 0x8000:
        segment_type = 3
    else:
        segment_type = 0
    
    temp_segment = segment_data[0:4] + b'\x00\x00' + payload
    calculated_checksum = CalculateChecksum(temp_segment)
    
    is_valid = (calculated_checksum == received_checksum)
    
    return (seq_num, segment_type, payload, is_valid)


def CorruptSegment(segment_data):
    
    if len(segment_data) <= 4:
        byte_idx = random.randint(0, len(segment_data) - 1)
    else:
        byte_idx = random.randint(4, len(segment_data) - 1)
    
    bit_idx = random.randint(0, 7)
    corrupted = bytearray(segment_data)
    corrupted[byte_idx] ^= (1 << bit_idx)
    
    return bytes(corrupted)


def GetSegmentTypeName(segment_type):
    
    if segment_type == 0:
        return "DATA"
    elif segment_type == 1:
        return "ACK"
    elif segment_type == 2:
        return "SYN"
    elif segment_type == 3:
        return "FIN"
    return "UNKNOWN"


class Plc:
    
    
    def __init__(self, flp, rlp, fcp, rcp):
        
        self.flp = flp
        self.rlp = rlp
        self.fcp = fcp
        self.rcp = rcp
    
    def ProcessForward(self, segment_data):
        
        rand = random.random()
        
        if rand < self.flp:
            return (None, 'drp')
        elif rand < self.flp + self.fcp:
            corrupted = CorruptSegment(segment_data)
            return (corrupted, 'cor')
        else:
            return (segment_data, 'ok')
    
    def ProcessReverse(self, segment_data):
        
        rand = random.random()
        
        if rand < self.rlp:
            return (None, 'drp')
        elif rand < self.rlp + self.rcp:
            corrupted = CorruptSegment(segment_data)
            return (corrupted, 'cor')
        else:
            return (segment_data, 'ok')



class UrpSender:
    
    
    def __init__(self, sender_port, receiver_port, filename, max_win, rto, 
                 flp, rlp, fcp, rcp):
        
        self.sender_port = sender_port
        self.receiver_port = receiver_port
        self.filename = filename
        self.max_win = max_win
        self.rto = rto
        
        self.plc = Plc(flp, rlp, fcp, rcp)
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[Sender] Binding socket to localhost:{sender_port}")
        self.sock.bind(('localhost', sender_port))
        self.sock.settimeout(0.1)
        print(f"[Sender] Socket bound successfully")
        
        self.state = 0
        self.isn = None
        self.next_seq = None
        self.base = None
        
        self.window = {}
        self.unacked_bytes = 0
        
        self.file = None
        self.file_size = 0
        self.file_pos = 0
        
        self.timer = None
        self.timer_lock = threading.Lock()
        self.timer_running = False
        self.oldest_unacked_seq = None
        
        self.dup_ack_count = {}
        self.last_ack = None
        
        self.log_entries = []
        self.start_time = None
        
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
    
    def Log(self, direction, status, segment_type, seq_num, payload_len):
        
        if self.start_time is None:
            return
        elapsed = (time.time() - self.start_time) * 1000
        type_name = GetSegmentTypeName(segment_type)
        self.log_entries.append(
            f"{direction}  {status:3s}  {elapsed:7.2f}  {type_name:4s}  {seq_num:5d}  {payload_len:5d}\n"
        )
    
    def SendSegment(self, seq_num, segment_type, payload=b'', is_retransmission=False):
        
        seg = CreateSegment(seq_num, segment_type, payload)
        
        processed_seg, status = self.plc.ProcessForward(seg)
        
        if status == 'drp':
            self.stats['plc_forward_segments_dropped'] += 1
            self.Log('snd', 'drp', segment_type, seq_num, len(payload))
            return (False, 'drp')
        
        if processed_seg:
            try:
                self.sock.sendto(processed_seg, ('localhost', self.receiver_port))
                self.Log('snd', status, segment_type, seq_num, len(payload))
                
                if segment_type == 0:
                    if not is_retransmission:
                        self.stats['original_data_sent'] += len(payload)
                        self.stats['original_segments_sent'] += 1
                    self.stats['total_data_sent'] += len(payload)
                    self.stats['total_segments_sent'] += 1
                else:
                    self.stats['total_segments_sent'] += 1
                
                if status == 'cor':
                    self.stats['plc_forward_segments_corrupted'] += 1
                
                return (True, status)
            except Exception as e:
                return (False, 'drp')
        
        return (False, 'drp')
    
    def StartTimer(self, seq_num):
        
        with self.timer_lock:
            if not self.timer_running:
                self.oldest_unacked_seq = seq_num
                self.timer_running = True
                threading.Thread(target=self._TimerThread, daemon=True).start()
    
    def StopTimer(self):
        
        with self.timer_lock:
            self.timer_running = False
    
    def _TimerThread(self):
        
        while self.timer_running:
            time.sleep(self.rto)
            with self.timer_lock:
                if not self.timer_running:
                    break
                if self.oldest_unacked_seq is not None and self.oldest_unacked_seq in self.window:
                    seg_data, payload_len, _ = self.window[self.oldest_unacked_seq]
                    parsed = ParseSegment(seg_data)
                    if parsed:
                        seq_num, seg_type, payload, _ = parsed
                        print(f"[Sender] Timeout! Retransmitting segment: type={GetSegmentTypeName(seg_type)}, seq={seq_num}")
                        self.SendSegment(seq_num, seg_type, payload, is_retransmission=True)
                        self.stats['timeout_retransmissions'] += 1
                        
                        self.window[self.oldest_unacked_seq] = (
                            seg_data, payload_len, time.time()
                        )
    
    def HandleAck(self, ack_num):
        
        if ack_num <= self.base:
            if ack_num == self.base:
                self.stats['duplicate_acks_received'] += 1
                self.dup_ack_count[ack_num] = self.dup_ack_count.get(ack_num, 0) + 1
                if self.dup_ack_count[ack_num] == 3:
                    if self.base in self.window:
                        seg_data, payload_len, _ = self.window[self.base]
                        parsed = ParseSegment(seg_data)
                        if parsed:
                            seq_num, seg_type, payload, _ = parsed
                            self.SendSegment(seq_num, seg_type, payload, is_retransmission=True)
                            self.stats['fast_retransmissions'] += 1
                            self.window[self.base] = (seg_data, payload_len, time.time())
            return
        
        acked_seqs = []
        for seq in sorted(self.window.keys()):
            seg_data, payload_len, _ = self.window[seq]
            parsed = ParseSegment(seg_data)
            if parsed:
                seg_seq, seg_type, _, _ = parsed
                if seg_type == 0:
                    end_seq = seg_seq + payload_len
                else:
                    end_seq = seg_seq + 1
                
                if end_seq <= ack_num:
                    acked_seqs.append(seq)
                    if seg_type == 0:
                        self.unacked_bytes -= payload_len
        
        for seq in acked_seqs:
            del self.window[seq]
        
        if acked_seqs:
            print(f"[Sender] Received ACK: {ack_num}, acknowledged {len(acked_seqs)} segments, window_size={len(self.window)}, unacked_bytes={self.unacked_bytes}")
            self.base = ack_num
            self.dup_ack_count.clear()
            if self.window:
                self.oldest_unacked_seq = min(self.window.keys())
                if not self.timer_running:
                    self.StartTimer(self.oldest_unacked_seq)
            else:
                self.oldest_unacked_seq = None
                self.StopTimer()
        
        self.last_ack = ack_num
    
    def ReceiveLoop(self):
        
        print(f"[Sender] Receive loop started, listening on port {self.sender_port}")
        while self.state != 0:
            try:
                data, addr = self.sock.recvfrom(2048)
                print(f"[Sender] Received UDP packet from {addr}, size={len(data)}")
                
                processed_data, status = self.plc.ProcessReverse(data)
                
                if status == 'drp':
                    print(f"[Sender] ACK dropped by PLC (reverse loss)")
                    self.stats['plc_reverse_segments_dropped'] += 1
                    continue
                
                if not processed_data:
                    continue
                
                if status == 'cor':
                    print(f"[Sender] ACK corrupted by PLC (reverse corruption)")
                
                parsed = ParseSegment(processed_data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    print(f"[Sender] Received corrupted ACK: seq={seq_num}, discarding...")
                    self.stats['corrupted_acks_discarded'] += 1
                    self.Log('rcv', 'cor', seg_type, seq_num, 0)
                    continue
                
                self.Log('rcv', status, seg_type, seq_num, 0)
                if status == 'cor':
                    self.stats['plc_reverse_segments_corrupted'] += 1
                    print(f"[Sender] Received corrupted ACK (after PLC): seq={seq_num}")
                else:
                    print(f"[Sender] Received ACK (status={status}): seq={seq_num}, state={self.state}")
                
                if seg_type == 1:
                    if self.state == 1:
                        print(f"[Sender] Received ACK in SYN_SENT state: seq={seq_num}, expected={self.isn + 1}")
                        if seq_num == self.isn + 1:
                            print(f"[Sender] Received SYN ACK, connection established!")
                            self.state = 2
                            self.base = self.isn + 1
                            self.next_seq = self.isn + 1
                            self.StopTimer()
                        else:
                            print(f"[Sender] ACK seq mismatch: got {seq_num}, expected {self.isn + 1}")
                    elif self.state == 2:
                        self.HandleAck(seq_num)
                    elif self.state == 3:
                        if seq_num == self.next_seq:
                            print(f"[Sender] Received FIN ACK, closing connection...")
                            self.state = 0
                            self.StopTimer()
                            break
            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Sender] Error in receive_loop: {e}")
                import traceback
                traceback.print_exc()
                break
    
    def SendData(self):
        
        while self.state == 2:
            if self.file_pos >= self.file_size and len(self.window) == 0:
                print(f"[Sender] All data sent and acknowledged, sending FIN...")
                self.state = 3
                fin_seq = self.next_seq
                self.SendSegment(fin_seq, 3)
                self.window[fin_seq] = (
                    CreateSegment(fin_seq, 3),
                    0, time.time()
                )
                self.next_seq += 1
                self.StartTimer(fin_seq)
                break
            
            available_win = self.max_win - self.unacked_bytes
            
            if available_win > 0 and self.file_pos < self.file_size:
                payload_size = min(1000, available_win, self.file_size - self.file_pos)
                
                if payload_size > 0:
                    self.file.seek(self.file_pos)
                    payload = self.file.read(payload_size)
                    
                    if len(payload) > 0:
                        seq_num = self.next_seq
                        seg = CreateSegment(seq_num, 0, payload)
                        
                        self.window[seq_num] = (seg, len(payload), time.time())
                        self.unacked_bytes += len(payload)
                        
                        self.SendSegment(seq_num, 0, payload)
                        print(f"[Sender] Sent DATA segment: seq={seq_num}, len={len(payload)}, file_pos={self.file_pos}/{self.file_size}")
                        
                        self.next_seq += len(payload)
                        self.file_pos += len(payload)
                        
                        if not self.timer_running:
                            self.StartTimer(seq_num)
                        elif self.oldest_unacked_seq is None or seq_num < self.oldest_unacked_seq:
                            self.oldest_unacked_seq = seq_num
                    else:
                        break
                else:
                    time.sleep(0.01)
            else:
                time.sleep(0.01)
    
    def Run(self):
        
        try:
            self.file = open(self.filename, 'rb')
            self.file.seek(0, 2)
            self.file_size = self.file.tell()
            self.file.seek(0)
        except Exception as e:
            return
        
        recv_thread = threading.Thread(target=self.ReceiveLoop, daemon=True)
        recv_thread.start()
        
        self.state = 1
        self.isn = random.randint(0, 65535)
        self.base = self.isn
        self.next_seq = self.isn
        
        self.start_time = time.time()
        
        print(f"[Sender] Starting connection, ISN={self.isn}")
        self.SendSegment(self.isn, 2)
        self.window[self.isn] = (
            CreateSegment(self.isn, 2),
            0, time.time()
        )
        self.next_seq = self.isn + 1
        self.StartTimer(self.isn)
        print(f"[Sender] SYN sent, waiting for ACK...")
        
        max_wait_time = 30
        wait_start = time.time()
        while self.state == 1:
            if time.time() - wait_start > max_wait_time:
                print(f"[Sender] Connection establishment timeout!")
                return
            time.sleep(0.01)
        
        if self.state != 2:
            print(f"[Sender] Connection not established, state={self.state}")
            return
        
        print(f"[Sender] Connection established! Starting data transmission...")
        self.SendData()
        
        print(f"[Sender] Waiting for FIN ACK...")
        max_wait_time = 30
        wait_start = time.time()
        while self.state == 3:
            if time.time() - wait_start > max_wait_time:
                print(f"[Sender] FIN ACK timeout!")
                return
            time.sleep(0.01)
        
        print(f"[Sender] Connection closed successfully!")
        
        if self.file:
            self.file.close()
        
        self.sock.close()
        
        self.WriteLog()
    
    def WriteLog(self):
        
        with open('sender_log.txt', 'w') as f:
            for entry in self.log_entries:
                f.write(entry)
            
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


if __name__ == '__main__':
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
    
    sender = UrpSender(sender_port, receiver_port, filename, max_win, rto,
                       flp, rlp, fcp, rcp)
    sender.Run()

