#include "feetech_bus.h"

FeetechBus::FeetechBus(HardwareSerial& ser, uint8_t dePin, int8_t rxPin, int8_t txPin, uint32_t baud)
    : ser_(ser), dePin_(dePin), rxPin_(rxPin), txPin_(txPin), baud_(baud) {}

bool FeetechBus::begin() {
  if (dePin_ >= 0) {
    pinMode(dePin_, OUTPUT);
    digitalWrite(dePin_, LOW);  // 默认接收态
  }
  ser_.begin(baud_, SERIAL_8N1, rxPin_, txPin_, false, 200);
  return true;
}

void FeetechBus::end() { ser_.end(); }

void FeetechBus::swapPins() {
  ser_.end();
  int8_t tmp = rxPin_;
  rxPin_ = txPin_;
  txPin_ = tmp;
  begin();
}

void FeetechBus::flushRx() {
  while (ser_.available()) ser_.read();
}

bool FeetechBus::txPacket(const uint8_t* pkt, size_t len) {
  flushRx();
  if (dePin_ >= 0) digitalWrite(dePin_, HIGH);  // MAX485 发送态（无 DE 时无影响）
  delayMicroseconds(20);       // 方向稳定
  size_t written = ser_.write(pkt, len);
  ser_.flush();
  delayMicroseconds(20);
  if (dePin_ >= 0) digitalWrite(dePin_, LOW);   // 回接收态
  // 注意：不要在这里清空 RX！Waveshare Adapter(A) 的 TX/RX 是分开的，
  // 舵机应答会立即进入 RX；若在此当作"回显"清掉，ping/read 就会一直失败。
  // rxStatus() 会自动跳过噪声/回显字节并搜索 FF FF 包头。
  return written == len;
}

bool FeetechBus::echoTest(uint8_t* echoed, size_t maxLen, size_t& count, uint32_t timeoutMs) {
  uint8_t test[8];
  for (int i = 0; i < 8; i++) test[i] = 0xA5;   // 无 FF FF 头，舵机不会响应
  flushRx();
  if (dePin_ >= 0) digitalWrite(dePin_, HIGH);
  delayMicroseconds(20);
  ser_.write(test, 8);
  ser_.flush();
  delayMicroseconds(20);
  if (dePin_ >= 0) digitalWrite(dePin_, LOW);
  count = 0;
  uint32_t t0 = millis();
  while ((uint32_t)(millis() - t0) < timeoutMs && count < maxLen) {
    if (ser_.available()) echoed[count++] = (uint8_t)ser_.read();
  }
  return count > 0;
}

bool FeetechBus::pingRaw(uint8_t id, uint8_t* out, size_t maxLen, size_t& count, uint32_t timeoutMs) {
  uint8_t pkt[6] = {0xFF, 0xFF, id, 2, 0x01, 0};
  pkt[5] = (uint8_t)~(id + 2 + 0x01);
  flushRx();
  if (dePin_ >= 0) digitalWrite(dePin_, HIGH);
  delayMicroseconds(20);
  size_t written = ser_.write(pkt, 6);
  ser_.flush();
  delayMicroseconds(20);
  if (dePin_ >= 0) digitalWrite(dePin_, LOW);
  count = 0;
  uint32_t t0 = millis();
  while ((uint32_t)(millis() - t0) < timeoutMs && count < maxLen) {
    if (ser_.available()) out[count++] = (uint8_t)ser_.read();
  }
  return count > 0;
}

bool FeetechBus::rxStatus(uint8_t expectId, uint8_t* data, uint8_t dataLen, uint32_t timeoutMs) {
  uint8_t buf[kMaxPkt];
  size_t n = 0;
  uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    while (ser_.available() && n < kMaxPkt) {
      buf[n++] = (uint8_t)ser_.read();
      if (n >= 6) {
        // 找包头 FF FF
        size_t h = 0;
        while (h + 1 < n && !(buf[h] == 0xFF && buf[h + 1] == 0xFF)) h++;
        if (h > 0) { memmove(buf, buf + h, n - h); n -= h; }
        if (n >= 6 && buf[0] == 0xFF && buf[1] == 0xFF) {
          uint8_t len = buf[3];
          size_t total = (size_t)len + 4;   // 2头 + ID + LEN + LEN字节 + CHK
          if (n >= total) {
            bool ok = (buf[2] == expectId);
            if (ok) {
              uint8_t sum = 0;
              for (size_t i = 2; i < total - 1; i++) sum += buf[i];
              ok = ((uint8_t)~sum == buf[total - 1]);
            }
            if (ok) {
              // 数据长度 = LEN - 3（ERROR 1B 及其余）
              uint8_t avail = len >= 2 ? (uint8_t)(len - 2) : 0;
              if (dataLen > 0) {
                if (avail >= dataLen) { memcpy(data, buf + 5, dataLen); return true; }
                return false;  // 数据不够
              }
              return true;      // PING/WRITE 状态包
            }
            return false;       // ID 不匹配或校验失败
          }
        }
      }
    }
  }
  return false;  // 超时
}

bool FeetechBus::ping(uint8_t id, uint32_t timeoutMs) {
  uint8_t pkt[6] = {0xFF, 0xFF, id, 2, 0x01, 0};
  pkt[5] = (uint8_t)~(id + 2 + 0x01);
  if (!txPacket(pkt, 6)) { errCount_++; return false; }
  return rxStatus(id, nullptr, 0, timeoutMs);
}

bool FeetechBus::read(uint8_t id, uint8_t addr, uint8_t size, uint8_t* out, uint32_t timeoutMs) {
  if (size == 0 || size > 32) return false;
  uint8_t pkt[8] = {0xFF, 0xFF, id, 4, 0x02, addr, size, 0};
  pkt[7] = (uint8_t)~(id + 4 + 0x02 + addr + size);
  if (!txPacket(pkt, 8)) { errCount_++; return false; }
  return rxStatus(id, out, size, timeoutMs);
}

bool FeetechBus::write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t size, uint32_t timeoutMs) {
  if (size == 0 || size > 32) return false;
  uint8_t pkt[kMaxPkt];
  pkt[0] = 0xFF; pkt[1] = 0xFF; pkt[2] = id;
  pkt[3] = (uint8_t)(size + 3);  // INST(1) + ADDR(1) + DATA(size) + 1
  pkt[4] = 0x03;                 // INST_WRITE
  pkt[5] = addr;
  memcpy(pkt + 6, data, size);
  uint8_t sum = id + pkt[3] + 0x03 + addr;
  for (uint8_t i = 0; i < size; i++) sum += data[i];
  pkt[6 + size] = (uint8_t)~sum;
  if (!txPacket(pkt, 7 + size)) { errCount_++; return false; }
  return rxStatus(id, nullptr, 0, timeoutMs);
}

bool FeetechBus::readWord(uint8_t id, uint8_t addr, int16_t& value, uint32_t timeoutMs) {
  uint8_t b[2];
  if (!read(id, addr, 2, b, timeoutMs)) return false;
  value = (int16_t)(b[0] | ((uint16_t)b[1] << 8));
  return true;
}

bool FeetechBus::writeWord(uint8_t id, uint8_t addr, int16_t value, uint32_t timeoutMs) {
  uint8_t b[2] = {(uint8_t)(value & 0xFF), (uint8_t)(((uint16_t)value >> 8) & 0xFF)};
  return write(id, addr, b, 2, timeoutMs);
}

bool FeetechBus::writeByte(uint8_t id, uint8_t addr, uint8_t value, uint32_t timeoutMs) {
  return write(id, addr, &value, 1, timeoutMs);
}

bool FeetechBus::writeMotorSpeed(uint8_t id, uint8_t addr, int16_t speed, uint32_t timeoutMs) {
  uint16_t enc;
  if (speed < 0) {
    int32_t mag = -(int32_t)speed;
    if (mag > 0x7FFF) return false;
    enc = (uint16_t)(0x8000u | (uint16_t)mag);  // BIT15 方向位 + 低 15 位幅值
  } else {
    if (speed > 0x7FFF) return false;
    enc = (uint16_t)speed;
  }
  uint8_t b[2] = {(uint8_t)(enc & 0xFF), (uint8_t)((enc >> 8) & 0xFF)};
  return write(id, addr, b, 2, timeoutMs);
}


