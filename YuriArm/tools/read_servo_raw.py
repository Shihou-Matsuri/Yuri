import serial, time, sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM7"
ID = int(sys.argv[2]) if len(sys.argv) > 2 else 6
BAUD = 1000000

def checksum(pkt):
    s = 0
    for b in pkt:
        s += b
    return (~s) & 0xFF

def read_raw(ser, servo_id, addr=56, size=2, timeout=0.05):
    # FF FF ID LEN(4) INST_READ(0x02) ADDR LEN checksum
    pkt = [0xFF, 0xFF, servo_id, 4, 0x02, addr, size]
    pkt.append(checksum(pkt))
    ser.reset_input_buffer()
    ser.write(bytes(pkt))
    time.sleep(timeout)
    resp = ser.read(64)
    if len(resp) < 6:
        return None
    # 找 FF FF 包头
    for i in range(len(resp) - 5):
        if resp[i] == 0xFF and resp[i+1] == 0xFF:
            rid = resp[i+2]
            ln = resp[i+3]
            # 数据在 index i+5 起 (ERR在i+4)
            if len(resp) >= i + 4 + ln:
                data = resp[i+5 : i+5+ln-1]
                if len(data) >= 2:
                    return data[0] | (data[1] << 8)
    return None

ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(0.3)
print(f"=== 读 {PORT} id{ID} Present_Position raw === 请转动该关节, Ctrl+C 停", flush=True)
t0 = time.time(); last = None; reads = 0
try:
    while time.time() - t0 < 10:
        v = read_raw(ser, ID)
        if v is not None:
            reads += 1
            if last is None or abs(v - last) > 8:
                print(f"t={time.time()-t0:.1f}s raw={v}", flush=True)
                last = v
        time.sleep(0.03)
except KeyboardInterrupt:
    pass
print(f"结束: 读到 {reads} 次, 最后 raw={last}")
ser.close()
