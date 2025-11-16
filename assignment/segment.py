"""
URP Segment Format Handler
处理URP段的编码、解码和校验和计算
"""
import struct
import random

# 段类型常量
SEGMENT_DATA = 0
SEGMENT_ACK = 1
SEGMENT_SYN = 2
SEGMENT_FIN = 3

# Flag位位置（在reserved+flags字段中）
FLAG_ACK = 0x2000  # bit 13
FLAG_SYN = 0x4000  # bit 14
FLAG_FIN = 0x8000  # bit 15

MSS = 1000  # Maximum Segment Size (payload only)
HEADER_SIZE = 6


def calculate_checksum(data):
    """
    计算16位ones' complement校验和
    """
    checksum = 0
    # 处理所有16位字
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            word = (data[i] << 8) + data[i + 1]
        else:
            word = (data[i] << 8)  # 奇数长度，最后字节补0
        checksum += word
        # 处理溢出
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
    # 取反
    return (~checksum) & 0xFFFF


def create_segment(seq_num, segment_type, payload=b''):
    """
    创建URP段
    
    Args:
        seq_num: 16位序列号
        segment_type: SEGMENT_DATA, SEGMENT_ACK, SEGMENT_SYN, SEGMENT_FIN
        payload: 数据载荷（仅DATA段）
    
    Returns:
        bytes: 编码后的段
    """
    # 构建header前4字节
    seq_bytes = struct.pack('>H', seq_num)
    
    # 构建flags字段
    flags = 0
    if segment_type == SEGMENT_ACK:
        flags = FLAG_ACK
    elif segment_type == SEGMENT_SYN:
        flags = FLAG_SYN
    elif segment_type == SEGMENT_FIN:
        flags = FLAG_FIN
    # SEGMENT_DATA: flags = 0
    
    flags_bytes = struct.pack('>H', flags)
    
    # 临时段（不含checksum）
    temp_segment = seq_bytes + flags_bytes + b'\x00\x00' + payload
    
    # 计算校验和
    checksum = calculate_checksum(temp_segment)
    checksum_bytes = struct.pack('>H', checksum)
    
    # 完整段
    segment = seq_bytes + flags_bytes + checksum_bytes + payload
    
    return segment


def parse_segment(segment_data):
    """
    解析URP段
    
    Args:
        segment_data: 接收到的段数据
    
    Returns:
        tuple: (seq_num, segment_type, payload, is_valid) 或 None（如果段太短）
    """
    if len(segment_data) < HEADER_SIZE:
        return None
    
    # 解析header
    seq_num = struct.unpack('>H', segment_data[0:2])[0]
    flags_field = struct.unpack('>H', segment_data[2:4])[0]
    received_checksum = struct.unpack('>H', segment_data[4:6])[0]
    
    # 提取payload
    payload = segment_data[6:]
    
    # 确定段类型
    if flags_field & FLAG_ACK:
        segment_type = SEGMENT_ACK
    elif flags_field & FLAG_SYN:
        segment_type = SEGMENT_SYN
    elif flags_field & FLAG_FIN:
        segment_type = SEGMENT_FIN
    else:
        segment_type = SEGMENT_DATA
    
    # 验证校验和
    # 将checksum字段置0后计算
    temp_segment = segment_data[0:4] + b'\x00\x00' + payload
    calculated_checksum = calculate_checksum(temp_segment)
    
    is_valid = (calculated_checksum == received_checksum)
    
    return (seq_num, segment_type, payload, is_valid)


def corrupt_segment(segment_data):
    """
    损坏段：随机翻转一个字节的一位（不能是header前4字节）
    
    Args:
        segment_data: 原始段数据
    
    Returns:
        bytes: 损坏后的段数据
    """
    if len(segment_data) <= 4:
        # 如果段太短，翻转header的某个位
        byte_idx = random.randint(0, len(segment_data) - 1)
    else:
        # 不能损坏header前4字节，从第5字节开始
        byte_idx = random.randint(4, len(segment_data) - 1)
    
    # 翻转随机位
    bit_idx = random.randint(0, 7)
    corrupted = bytearray(segment_data)
    corrupted[byte_idx] ^= (1 << bit_idx)
    
    return bytes(corrupted)


def get_segment_type_name(segment_type):
    """获取段类型名称"""
    if segment_type == SEGMENT_DATA:
        return "DATA"
    elif segment_type == SEGMENT_ACK:
        return "ACK"
    elif segment_type == SEGMENT_SYN:
        return "SYN"
    elif segment_type == SEGMENT_FIN:
        return "FIN"
    return "UNKNOWN"

