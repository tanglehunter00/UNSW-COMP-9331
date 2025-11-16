"""
Packet Loss & Corruption (PLC) Module
模拟网络丢包和损坏
"""
import random
import segment


class PLC:
    """PLC模块：模拟前向和反向方向的丢包和损坏"""
    
    def __init__(self, flp, rlp, fcp, rcp):
        """
        初始化PLC模块
        
        Args:
            flp: forward loss probability (前向丢包概率)
            rlp: reverse loss probability (反向丢包概率)
            fcp: forward corruption probability (前向损坏概率)
            rcp: reverse corruption probability (反向损坏概率)
        """
        self.flp = flp
        self.rlp = rlp
        self.fcp = fcp
        self.rcp = rcp
    
    def process_forward(self, segment_data):
        """
        处理前向段（DATA/SYN/FIN）
        
        Returns:
            tuple: (processed_segment, status)
            status: 'ok', 'drp', 'cor'
        """
        rand = random.random()
        
        if rand < self.flp:
            # 丢包
            return (None, 'drp')
        elif rand < self.flp + self.fcp:
            # 损坏
            corrupted = segment.corrupt_segment(segment_data)
            return (corrupted, 'cor')
        else:
            # 正常
            return (segment_data, 'ok')
    
    def process_reverse(self, segment_data):
        """
        处理反向段（ACK）
        
        Returns:
            tuple: (processed_segment, status)
            status: 'ok', 'drp', 'cor'
        """
        rand = random.random()
        
        if rand < self.rlp:
            # 丢包
            return (None, 'drp')
        elif rand < self.rlp + self.rcp:
            # 损坏
            corrupted = segment.corrupt_segment(segment_data)
            return (corrupted, 'cor')
        else:
            # 正常
            return (segment_data, 'ok')

