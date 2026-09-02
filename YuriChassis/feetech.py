"""飞特 STS3215 舵机协议底层（TTL 半双工，数据低字节在前）。

只做两件事：算校验和、收发指令帧。给 diff_drive.py 调用。
"""

# 指令码（飞特协议固定值）
CMD_PING  = 0x01
CMD_READ  = 0x02
CMD_WRITE = 0x03

# 帧头
HEADER = b"\xFF\xFF"


def checksum(body: bytes) -> int:
    """校验和 = 所有字节相加取反，留低 8 位。

    飞特规则：Checksum = ~(ID + Length + Instruction + 参数...) & 0xFF
    """
    return (~sum(body)) & 0xFF


def write_command(ser, servo_id: int, addr: int, data: bytes):
    """写指令。

    帧：FF FF ID LEN 03 ADDR DATA... CHK
    LEN = 数据字节数 + 3（地址 1 + 数据 N + 指令/校验共 2）
    data 需低字节在前（调用方负责拼好）。
    """
    body = bytes([servo_id, len(data) + 3, CMD_WRITE, addr]) + data
    packet = HEADER + body + bytes([checksum(body)])
    ser.write(packet)
    ser.flush()


def write_byte(ser, servo_id: int, addr: int, value: int):
    """写 1 字节（如运行模式、扭矩开关）。"""
    write_command(ser, servo_id, addr, bytes([value & 0xFF]))


DIR_BIT = 0x8000          # 电机速度方向位（BIT15）


def encode_motor_speed(speed: int) -> int:
    """STS3215 电机模式速度编码（BIT15=方向，其余为幅值）。

    Feetech 电机恒速模式的运行速度寄存器按“BIT15 方向 + 低15位幅值”解释，
    不是二进制补码。负值必须编码为 0x8000 | abs(value)，否则会被当成
    反向满速（0xFD81 等），导致正/反转转速不对称。

    speed 为有符号转速，范围 [-0x7FFF, 0x7FFF]。
    """
    if speed < 0:
        magnitude = -speed
        if magnitude > 0x7FFF:
            raise ValueError(f"速度幅值超出上限: {speed}")
        return DIR_BIT | magnitude
    if speed > 0x7FFF:
        raise ValueError(f"速度幅值超出上限: {speed}")
    return speed


def write_word(ser, servo_id: int, addr: int, value: int):
    """写 2 字节（如运行速度），低字节在前。"""
    value &= 0xFFFF  # 截到 16 位
    write_command(ser, servo_id, addr, bytes([value & 0xFF, (value >> 8) & 0xFF]))


def write_motor_speed(ser, servo_id: int, addr: int, speed: int):
    """写电机模式速度：先做 BIT15 幅值编码，再低字节在前。"""
    encoded = encode_motor_speed(speed)
    write_command(ser, servo_id, addr, bytes([encoded & 0xFF, (encoded >> 8) & 0xFF]))


def ping(ser, servo_id: int) -> bool:
    """PING：确认舵机在线。返回是否收到应答。"""
    body = bytes([servo_id, 0x02, CMD_PING])
    packet = HEADER + body + bytes([checksum(body)])
    ser.reset_input_buffer()
    ser.write(packet)
    ser.flush()
    reply = ser.read(6)  # 应答 6 字节：FF FF ID 02 状态 CHK
    return len(reply) == 6 and reply[0] == 0xFF
