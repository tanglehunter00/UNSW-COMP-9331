
import socket
import sys
import time
import threading
import struct
import random

SEGMENT_DATA = 0
SEGMENT_ACK = 1
SEGMENT_SYN = 2
SEGMENT_FIN = 3

FLAG_ACK = 0x2000
FLAG_SYN = 0x4000
FLAG_FIN = 0x8000

MSS = 1000
HEADER_SIZE = 6


def calculate_checksum(data):
    
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


def create_segment(seq_num, segment_type, payload=b''):
    
    seq_bytes = struct.pack('>H', seq_num)
    
    flags = 0
    if segment_type == SEGMENT_ACK:
        flags = FLAG_ACK
    elif segment_type == SEGMENT_SYN:
        flags = FLAG_SYN
    elif segment_type == SEGMENT_FIN:
        flags = FLAG_FIN
    
    flags_bytes = struct.pack('>H', flags)
    
    temp_segment = seq_bytes + flags_bytes + b'\x00\x00' + payload
    
    checksum = calculate_checksum(temp_segment)
    checksum_bytes = struct.pack('>H', checksum)
    
    segment_data = seq_bytes + flags_bytes + checksum_bytes + payload
    
    return segment_data


def parse_segment(segment_data):
    
    if len(segment_data) < HEADER_SIZE:
        return None
    
    seq_num = struct.unpack('>H', segment_data[0:2])[0]
    flags_field = struct.unpack('>H', segment_data[2:4])[0]
    received_checksum = struct.unpack('>H', segment_data[4:6])[0]
    
    payload = segment_data[6:]
    
    if flags_field & FLAG_ACK:
        segment_type = SEGMENT_ACK
    elif flags_field & FLAG_SYN:
        segment_type = SEGMENT_SYN
    elif flags_field & FLAG_FIN:
        segment_type = SEGMENT_FIN
    else:
        segment_type = SEGMENT_DATA
    
    temp_segment = segment_data[0:4] + b'\x00\x00' + payload
    calculated_checksum = calculate_checksum(temp_segment)
    
    is_valid = (calculated_checksum == received_checksum)
    
    return (seq_num, segment_type, payload, is_valid)


def get_segment_type_name(segment_type):
    
    if segment_type == SEGMENT_DATA:
        return "DATA"
    elif segment_type == SEGMENT_ACK:
        return "ACK"
    elif segment_type == SEGMENT_SYN:
        return "SYN"
    elif segment_type == SEGMENT_FIN:
        return "FIN"
    return "UNKNOWN"

STATE_CLOSED = 0
STATE_ESTABLISHED = 1
STATE_TIME_WAIT = 2


class URPReceiver:
    
    
    def __init__(self, receiver_port, sender_port, output_filename, max_win):
        
        self.receiver_port = receiver_port
        self.sender_port = sender_port
        self.output_filename = output_filename
        self.max_win = max_win
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', receiver_port))
        self.sock.settimeout(0.1)
        
        self.state = STATE_CLOSED
        self.expected_seq = None
        self.isn = None
        
        self.buffer = {}
        self.received_bytes = set()
        
        self.file = None
        
        self.log_entries = []
        self.start_time = None
        
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
        
        if self.start_time is None:
            return
        elapsed = (time.time() - self.start_time) * 1000
        type_name = get_segment_type_name(segment_type)
        self.log_entries.append(
            f"{direction}  {status:3s}  {elapsed:7.2f}  {type_name:4s}  {seq_num:5d}  {payload_len:5d}\n"
        )
    
    def send_ack(self, ack_num):
        
        seg = create_segment(ack_num, SEGMENT_ACK)
        try:
            print(f"Sending ACK: ack_num={ack_num}, to port {self.sender_port}, segment_size={len(seg)}")
            self.sock.sendto(seg, ('localhost', self.sender_port))
            self.log('snd', 'ok', SEGMENT_ACK, ack_num, 0)
            self.stats['total_acks_sent'] += 1
            print(f"ACK sent successfully to localhost:{self.sender_port}")
        except Exception as e:
            print(f"Error sending ACK: {e}")
            import traceback
            traceback.print_exc()
    
    def is_duplicate(self, seq_num, payload_len):
        
        for i in range(seq_num, seq_num + payload_len):
            if i in self.received_bytes:
                return True
        return False
    
    def mark_received(self, seq_num, payload_len):
        
        for i in range(seq_num, seq_num + payload_len):
            self.received_bytes.add(i)
    
    def write_continuous_data(self):
        
        while self.expected_seq in self.buffer:
            payload = self.buffer[self.expected_seq]
            del self.buffer[self.expected_seq]
            
            if self.file:
                self.file.write(payload)
                self.file.flush()
            
            self.stats['original_data_received'] += len(payload)
            self.stats['original_segments_received'] += 1
            
            self.expected_seq += len(payload)
    
    def handle_data_segment(self, seq_num, payload):
        
        payload_len = len(payload)
        
        is_dup = self.is_duplicate(seq_num, payload_len)
        
        if is_dup:
            self.stats['duplicate_segments_received'] += 1
            self.send_ack(self.expected_seq)
            self.stats['duplicate_acks_sent'] += 1
            return
        
        self.mark_received(seq_num, payload_len)
        
        if seq_num == self.expected_seq:
            if self.file:
                self.file.write(payload)
                self.file.flush()
            
            self.stats['original_data_received'] += len(payload)
            self.stats['total_data_received'] += len(payload)
            self.stats['original_segments_received'] += 1
            self.stats['total_segments_received'] += 1
            
            print(f"Received in-order DATA: seq={seq_num}, len={len(payload)}, expected_seq={self.expected_seq}")
            
            self.expected_seq += payload_len
            
            self.send_ack(self.expected_seq)
            
            self.write_continuous_data()
        else:
            if seq_num > self.expected_seq:
                print(f"Received out-of-order DATA: seq={seq_num}, expected_seq={self.expected_seq}, buffering...")
                self.buffer[seq_num] = payload
                self.stats['total_data_received'] += len(payload)
                self.stats['total_segments_received'] += 1
            self.send_ack(self.expected_seq)
            self.stats['duplicate_acks_sent'] += 1
    
    def run(self):
        
        try:
            self.file = open(self.output_filename, 'wb')
        except Exception as e:
            return
        
        print(f"Waiting for SYN...")
        syn_received = False
        while not syn_received:
            try:
                data, addr = self.sock.recvfrom(2048)
                
                parsed = parse_segment(data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    print(f"Received corrupted SYN, discarding...")
                    self.stats['corrupted_segments_discarded'] += 1
                    self.log('rcv', 'cor', seg_type, seq_num, 0)
                    continue
                
                if seg_type == SEGMENT_SYN:
                    if self.isn is not None and seq_num == self.isn:
                        print(f"Received duplicate SYN, resending ACK...")
                        self.send_ack(self.expected_seq)
                    else:
                        print(f"Received SYN: ISN={seq_num}, sending ACK...")
                        self.isn = seq_num
                        self.expected_seq = seq_num + 1
                        self.state = STATE_ESTABLISHED
                        syn_received = True
                        self.start_time = time.time()
                        
                        self.log('rcv', 'ok', SEGMENT_SYN, seq_num, 0)
                        
                        self.send_ack(self.expected_seq)
                        print(f"Connection established! Waiting for data...")
                    break
            
            except socket.timeout:
                continue
            except Exception as e:
                return
        
        fin_received = False
        fin_ack_num = None
        
        while self.state == STATE_ESTABLISHED or self.state == STATE_TIME_WAIT:
            try:
                data, addr = self.sock.recvfrom(2048)
                
                parsed = parse_segment(data)
                if not parsed:
                    continue
                
                seq_num, seg_type, payload, is_valid = parsed
                
                if not is_valid:
                    print(f"Received corrupted segment: type={seg_type}, seq={seq_num}, discarding...")
                    self.stats['corrupted_segments_discarded'] += 1
                    self.log('rcv', 'cor', seg_type, seq_num, len(payload) if seg_type == SEGMENT_DATA else 0)
                    continue
                
                if seg_type == SEGMENT_SYN and seq_num == self.isn:
                    self.send_ack(self.expected_seq)
                    continue
                
                if self.state == STATE_TIME_WAIT and seg_type == SEGMENT_FIN:
                    if seq_num == fin_ack_num - 1:
                        print(f"Received retransmitted FIN in TIME_WAIT, resending ACK...")
                        self.send_ack(fin_ack_num)
                        continue
                
                if seg_type == SEGMENT_DATA:
                    self.log('rcv', 'ok', SEGMENT_DATA, seq_num, len(payload))
                elif seg_type == SEGMENT_FIN:
                    self.log('rcv', 'ok', SEGMENT_FIN, seq_num, 0)
                
                if seg_type == SEGMENT_DATA:
                    if self.state == STATE_ESTABLISHED:
                        self.handle_data_segment(seq_num, payload)
                elif seg_type == SEGMENT_FIN and not fin_received:
                    print(f"Received FIN, sending ACK and entering TIME_WAIT...")
                    fin_ack_num = seq_num + 1
                    self.send_ack(fin_ack_num)
                    fin_received = True
                    
                    self.state = STATE_TIME_WAIT
                    print(f"TIME_WAIT (2 seconds)...")
                    time_wait_start = time.time()
                    while time.time() - time_wait_start < 2.0:
                        try:
                            self.sock.settimeout(0.1)
                            data, addr = self.sock.recvfrom(2048)
                            parsed = parse_segment(data)
                            if parsed:
                                seq_num, seg_type, payload, is_valid = parsed
                                if is_valid and seg_type == SEGMENT_FIN and seq_num == fin_ack_num - 1:
                                    print(f"Received retransmitted FIN in TIME_WAIT, resending ACK...")
                                    self.send_ack(fin_ack_num)
                                    time_wait_start = time.time()
                        except socket.timeout:
                            continue
                        except Exception:
                            break
                    
                    self.state = STATE_CLOSED
                    print(f"Connection closed!")
                    break
            
            except socket.timeout:
                continue
            except Exception as e:
                break
        
        if self.file:
            self.file.close()
        
        self.sock.close()
        
        self.write_log()
    
    def write_log(self):
        
        with open('receiver_log.txt', 'w') as f:
            for entry in self.log_entries:
                f.write(entry)
            
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

