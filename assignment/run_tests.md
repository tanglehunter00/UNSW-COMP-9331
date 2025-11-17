# URP Protocol Test Scenarios

按照作业要求测试不同场景。请在两个终端窗口中分别运行以下命令。

## Test 1: Stop-and-Wait over Reliable Channel
**参数**: max_win=1000, rto=100ms, 无丢包无损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20000 20001 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20001 20000 poems.txt 1000 0.1 0 0 0 0
```

---

## Test 2a: Stop-and-Wait with Loss (forward and reverse)
**参数**: max_win=1000, rto=100ms, flp=rlp=0.1, fcp=rcp=0

**终端1 (Receiver)**:
```bash
python receiver.py 20010 20011 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20011 20010 poems.txt 1000 0.1 0.1 0.1 0 0
```

---

## Test 2b: Stop-and-Wait with Corruption (forward and reverse)
**参数**: max_win=1000, rto=100ms, flp=rlp=0, fcp=rcp=0.1

**终端1 (Receiver)**:
```bash
python receiver.py 20020 20021 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20021 20020 poems.txt 1000 0.1 0 0 0.1 0.1
```

---

## Test 2c: Stop-and-Wait with Loss and Corruption
**参数**: max_win=1000, rto=100ms, flp=rlp=0.05, fcp=rcp=0.02

**终端1 (Receiver)**:
```bash
python receiver.py 20030 20031 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20031 20030 poems.txt 1000 0.1 0.05 0.05 0.02 0.02
```

---

## Test 3: Sliding Window over Reliable Channel
**参数**: max_win=5000, rto=100ms, 无丢包无损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20040 20041 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20041 20040 poems.txt 5000 0.1 0 0 0 0
```

---

## Test 4a: Sliding Window with Loss (forward and reverse)
**参数**: max_win=5000, rto=100ms, flp=rlp=0.1, fcp=rcp=0

**终端1 (Receiver)**:
```bash
python receiver.py 20050 20051 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20051 20050 poems.txt 5000 0.1 0.1 0.1 0 0
```

---

## Test 4b: Sliding Window with Corruption (forward and reverse)
**参数**: max_win=5000, rto=100ms, flp=rlp=0, fcp=rcp=0.1

**终端1 (Receiver)**:
```bash
python receiver.py 20060 20061 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20061 20060 poems.txt 5000 0.1 0 0 0.1 0.1
```

---

## Test 4c: Sliding Window with Loss and Corruption
**参数**: max_win=5000, rto=100ms, flp=rlp=0.05, fcp=rcp=0.02

**终端1 (Receiver)**:
```bash
python receiver.py 20070 20071 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20071 20070 poems.txt 5000 0.1 0.05 0.05 0.02 0.02
```

---

## 验证结果

每个测试完成后，检查：
1. `sender_log.txt` - 发送方日志
2. `receiver_log.txt` - 接收方日志
3. `output.txt` - 接收到的文件

使用以下命令验证文件是否正确：
```bash
diff poems.txt output.txt
```

如果文件相同，不会有输出；如果有差异，会显示不同之处。

