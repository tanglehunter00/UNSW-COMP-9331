# URP Protocol 测试指令

按照作业要求，依次测试以下场景。**每次测试前，先启动Receiver，再启动Sender**。

---

## Test 1: Stop-and-Wait over Reliable Channel
**说明**: max_win=1000 (相当于Stop-and-Wait), 无丢包无损坏

**终端1 (Receiver)**:
```bash
cd assignment
python receiver.py 20000 20001 output.txt 1000
```

**终端2 (Sender)**:
```bash
cd assignment
python sender.py 20001 20000 poems.txt 1000 0.1 0 0 0 0
```

**验证**: 完成后检查 `output.txt` 是否与 `poems.txt` 相同
```bash
diff poems.txt output.txt
```

---

## Test 2a: Stop-and-Wait with Loss (forward and reverse)
**说明**: max_win=1000, 前向和反向都有10%丢包

**终端1 (Receiver)**:
```bash
python receiver.py 20010 20011 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20011 20010 poems.txt 1000 0.1 0.1 0.1 0 0
```

**验证**: 检查日志中的重传次数和丢包统计

---

## Test 2b: Stop-and-Wait with Corruption (forward and reverse)
**说明**: max_win=1000, 前向和反向都有10%损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20020 20021 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20021 20020 poems.txt 1000 0.1 0 0 0.1 0.1
```

**验证**: 检查日志中的损坏段统计

---

## Test 2c: Stop-and-Wait with Loss and Corruption
**说明**: max_win=1000, 前向和反向都有丢包和损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20030 20031 output.txt 1000
```

**终端2 (Sender)**:
```bash
python sender.py 20031 20030 poems.txt 1000 0.1 0.05 0.05 0.02 0.02
```

**验证**: 检查日志中的重传、丢包和损坏统计

---

## Test 3: Sliding Window over Reliable Channel
**说明**: max_win=5000 (滑动窗口), 无丢包无损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20040 20041 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20041 20040 poems.txt 5000 0.1 0 0 0 0
```

**验证**: 应该能看到多个DATA段同时发送（窗口大小为5000字节，可以发送5个段）

---

## Test 4a: Sliding Window with Loss (forward and reverse)
**说明**: max_win=5000, 前向和反向都有10%丢包

**终端1 (Receiver)**:
```bash
python receiver.py 20050 20051 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20051 20050 poems.txt 5000 0.1 0.1 0.1 0 0
```

**验证**: 检查快速重传和超时重传

---

## Test 4b: Sliding Window with Corruption (forward and reverse)
**说明**: max_win=5000, 前向和反向都有10%损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20060 20061 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20061 20060 poems.txt 5000 0.1 0 0 0.1 0.1
```

**验证**: 检查损坏段统计和重传

---

## Test 4c: Sliding Window with Loss and Corruption
**说明**: max_win=5000, 前向和反向都有丢包和损坏

**终端1 (Receiver)**:
```bash
python receiver.py 20070 20071 output.txt 5000
```

**终端2 (Sender)**:
```bash
python sender.py 20071 20070 poems.txt 5000 0.1 0.05 0.05 0.02 0.02
```

**验证**: 检查所有统计信息

---

## 测试其他文件

如果想测试更大的文件，可以使用 `2br02b.txt`:

```bash
# Receiver
python receiver.py 20100 20101 output.txt 5000

# Sender
python sender.py 20101 20100 2br02b.txt 5000 0.1 0.05 0.05 0.02 0.02
```

---

## 检查日志文件

每次测试完成后，检查：

1. **sender_log.txt** - 发送方日志
   - 查看段发送/接收记录
   - 查看统计信息（重传次数、丢包数等）

2. **receiver_log.txt** - 接收方日志
   - 查看段接收/发送记录
   - 查看统计信息（损坏段数、重复段数等）

3. **output.txt** - 接收到的文件
   - 使用 `diff poems.txt output.txt` 验证文件是否正确

---

## 注意事项

1. **端口冲突**: 如果端口被占用，换一个端口号（建议使用49152-65535范围）
2. **测试顺序**: 先启动Receiver，再启动Sender
3. **等待完成**: 等待程序自然结束，不要手动中断
4. **日志文件**: 每次测试会覆盖之前的日志，如需保存请重命名

---

## 快速测试脚本（可选）

如果想快速测试所有场景，可以创建一个批处理文件，但建议手动测试以便观察每个场景的行为。

