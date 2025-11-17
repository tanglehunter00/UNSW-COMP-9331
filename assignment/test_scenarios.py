"""
URP Protocol Test Scenarios
按照作业要求测试不同场景
"""
import subprocess
import time
import os
import sys

def run_test(test_name, receiver_cmd, sender_cmd, wait_time=10):
    """运行一个测试场景"""
    print(f"\n{'='*80}")
    print(f"Test: {test_name}")
    print(f"{'='*80}")
    print(f"Receiver: {receiver_cmd}")
    print(f"Sender: {sender_cmd}")
    print(f"{'='*80}\n")
    
    # 启动接收方
    receiver = subprocess.Popen(
        receiver_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 等待接收方启动
    time.sleep(1)
    
    # 启动发送方
    sender = subprocess.Popen(
        sender_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 等待完成
    try:
        sender.wait(timeout=wait_time)
        receiver.wait(timeout=wait_time)
    except subprocess.TimeoutExpired:
        print(f"Test {test_name} timed out!")
        receiver.kill()
        sender.kill()
        return False
    
    # 检查输出文件
    if os.path.exists('output.txt'):
        size = os.path.getsize('output.txt')
        print(f"Output file size: {size} bytes")
        return True
    else:
        print("Output file not found!")
        return False

def main():
    """主测试函数"""
    print("URP Protocol Test Suite")
    print("="*80)
    
    # 测试文件
    test_file = "poems.txt"
    if not os.path.exists(test_file):
        print(f"Test file {test_file} not found!")
        return
    
    file_size = os.path.getsize(test_file)
    print(f"Test file: {test_file} ({file_size} bytes)")
    
    # 端口配置（每次测试使用不同端口）
    base_port = 20000
    
    tests = [
        {
            "name": "Test 1: Stop-and-Wait over Reliable Channel",
            "receiver": f"python receiver.py {base_port} {base_port+1} output.txt 1000",
            "sender": f"python sender.py {base_port+1} {base_port} {test_file} 1000 0.1 0 0 0 0",
            "wait": 15
        },
        {
            "name": "Test 2a: Stop-and-Wait with Loss (forward and reverse)",
            "receiver": f"python receiver.py {base_port+10} {base_port+11} output.txt 1000",
            "sender": f"python sender.py {base_port+11} {base_port+10} {test_file} 1000 0.1 0.1 0.1 0 0",
            "wait": 30
        },
        {
            "name": "Test 2b: Stop-and-Wait with Corruption (forward and reverse)",
            "receiver": f"python receiver.py {base_port+20} {base_port+21} output.txt 1000",
            "sender": f"python sender.py {base_port+21} {base_port+20} {test_file} 1000 0.1 0 0 0.1 0.1",
            "wait": 30
        },
        {
            "name": "Test 2c: Stop-and-Wait with Loss and Corruption",
            "receiver": f"python receiver.py {base_port+30} {base_port+31} output.txt 1000",
            "sender": f"python sender.py {base_port+31} {base_port+30} {test_file} 1000 0.1 0.05 0.05 0.02 0.02",
            "wait": 30
        },
        {
            "name": "Test 3: Sliding Window over Reliable Channel",
            "receiver": f"python receiver.py {base_port+40} {base_port+41} output.txt 5000",
            "sender": f"python sender.py {base_port+41} {base_port+40} {test_file} 5000 0.1 0 0 0 0",
            "wait": 15
        },
        {
            "name": "Test 4a: Sliding Window with Loss (forward and reverse)",
            "receiver": f"python receiver.py {base_port+50} {base_port+51} output.txt 5000",
            "sender": f"python sender.py {base_port+51} {base_port+50} {test_file} 5000 0.1 0.1 0.1 0 0",
            "wait": 30
        },
        {
            "name": "Test 4b: Sliding Window with Corruption (forward and reverse)",
            "receiver": f"python receiver.py {base_port+60} {base_port+61} output.txt 5000",
            "sender": f"python sender.py {base_port+61} {base_port+60} {test_file} 5000 0.1 0 0 0.1 0.1",
            "wait": 30
        },
        {
            "name": "Test 4c: Sliding Window with Loss and Corruption",
            "receiver": f"python receiver.py {base_port+70} {base_port+71} output.txt 5000",
            "sender": f"python sender.py {base_port+71} {base_port+70} {test_file} 5000 0.1 0.05 0.05 0.02 0.02",
            "wait": 30
        },
    ]
    
    results = []
    for test in tests:
        success = run_test(test["name"], test["receiver"], test["sender"], test["wait"])
        results.append((test["name"], success))
        time.sleep(2)  # 等待端口释放
    
    # 打印结果摘要
    print(f"\n{'='*80}")
    print("Test Results Summary")
    print(f"{'='*80}")
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()

