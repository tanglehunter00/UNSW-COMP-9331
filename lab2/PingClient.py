import argparse
import random
import socket
import time
from statistics import mean

def now_ms():
    return int(time.time() * 1000)

parser = argparse.ArgumentParser(description="UDP Ping Client")
parser.add_argument("host", type=str, help="server host")
parser.add_argument("port", type=int, help="server UDP port")
args = parser.parse_args()
server_addr = (args.host, args.port)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.6)

seq = random.randint(40000, 50000)

# count result
rtts_ms = []
results = []
first_send_ms = None
end_time_ms = None
for i in range(15):
    send_timestamp_ms = now_ms()
    if first_send_ms is None:
        first_send_ms = send_timestamp_ms
    message = f"PING {seq} {send_timestamp_ms}\r\n"
    data = message.encode("utf-8")
    # receive
    try:
        sock.sendto(data, server_addr)
        recv_data, recv_addr = sock.recvfrom(2048)
        recv_time_ms = now_ms()
        rtt = recv_time_ms - send_timestamp_ms
        clean = recv_data.rstrip(b"\x00").decode("utf-8", errors="replace").strip()
        rtts_ms.append(rtt)
        results.append(f"PING to {args.host}, seq={seq}, rtt={rtt} ms")
    # lost
    except socket.timeout:
        results.append(f"PING to {args.host}, seq={seq}, rtt=timeout")
    end_time_ms = now_ms()
    seq += 1
sock.close()
for line in results:
    print(line)
received = len(rtts_ms)
lost = 15 - received
packet_loss_pct = (lost / 15) * 100.0
if received >= 1:
    min_rtt = min(rtts_ms)
    max_rtt = max(rtts_ms)
    avg_rtt = int(round(mean(rtts_ms)))
else:
    min_rtt = max_rtt = avg_rtt = None
if first_send_ms is not None and end_time_ms is not None:
    total_tx_ms = end_time_ms - first_send_ms
else:
    total_tx_ms = 0
if received >= 2:
    diffs = [abs(rtts_ms[i] - rtts_ms[i - 1]) for i in range(1, received)]
    jitter = sum(diffs) / (received - 1)
    jitter = int(round(jitter))
else:
    jitter = None
print(f"\nPacket loss: {int(round(packet_loss_pct))}%")
if received >= 1:
    print(f"Minimum RTT: {min_rtt} ms, Maximum RTT: {max_rtt} ms, Average RTT: {avg_rtt} ms")
else:
    print("Minimum RTT: N/A, Maximum RTT: N/A, Average RTT: N/A")
print(f"Total transmission time: {total_tx_ms} ms")
if jitter is not None:
    print(f"Jitter: {jitter} ms")
else:
    print("Jitter: N/A")