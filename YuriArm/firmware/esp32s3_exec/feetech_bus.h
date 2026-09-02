#pragma once
#include <Arduino.h>
#include <HardwareSerial.h>

// Feetech 总线协议 v0（STS3215 等），半双工，可选 MAX485/DE；Waveshare Adapter UART 模式不用 DE。
// 报文：FF FF ID LEN INST PARAM... CHK；LEN = 1 + INST + PARAM 字节数；
// 校验和 = ~(ID+LEN+INST+PARAM...) & 0xFF；2 字节数值小端（LO 在前）。
// 移植自 lerobot src/lerobot/motors/feetech/ + scservo_sdk（协议 v0 实现）。
class FeetechBus {
 public:
  FeetechBus(HardwareSerial& ser, uint8_t dePin, int8_t rxPin, int8_t txPin, uint32_t baud = 1000000);

  bool begin();
  void end();
  // 运行时交换 RX/TX 引脚（诊断接线方向用；两脚都是 ESP32 3.3V GPIO，不需要改动硬件）
  void swapPins();

  bool ping(uint8_t id, uint32_t timeoutMs = 30);
  bool read(uint8_t id, uint8_t addr, uint8_t size, uint8_t* out, uint32_t timeoutMs = 30);
  bool write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t size, uint32_t timeoutMs = 30);
  bool readWord(uint8_t id, uint8_t addr, int16_t& value, uint32_t timeoutMs = 30);
  bool writeWord(uint8_t id, uint8_t addr, int16_t value, uint32_t timeoutMs = 30);
  bool writeByte(uint8_t id, uint8_t addr, uint8_t value, uint32_t timeoutMs = 30);
  // 电机恒速模式速度写入：speed 为有符号值，内部做 BIT15 幅值编码
  // （Feetech 电机模式速度寄存器按"BIT15=方向 + 低15位=幅值"解释，不是补码；
  //   负值若直接按补码写会被当成反向满速）。范围 ±0x7FFF，越界返回 false。
  bool writeMotorSpeed(uint8_t id, uint8_t addr, int16_t speed, uint32_t timeoutMs = 30);

  void flushRx();
  // 单线 TTL 环回测试：发 8 字节 0xA5，统计 RX 收到多少字节（判断 TX/RX 是否都在线上）
  bool echoTest(uint8_t* echoed, size_t maxLen, size_t& count, uint32_t timeoutMs = 20);
  // 发送一个 PING 并原样抓取 RX 上的所有字节（不解析），排查协议/波特率/供电问题
  bool pingRaw(uint8_t id, uint8_t* out, size_t maxLen, size_t& count, uint32_t timeoutMs = 100);
  uint32_t errCount() const { return errCount_; }

 private:
  bool txPacket(const uint8_t* pkt, size_t len);
  // 收状态包；dataLen>0 时把数据拷到 data（READ 响应），dataLen=0 只校验（PING/WRITE 响应）
  bool rxStatus(uint8_t expectId, uint8_t* data, uint8_t dataLen, uint32_t timeoutMs);

  HardwareSerial& ser_;
  uint8_t dePin_;
  int8_t rxPin_;
  int8_t txPin_;
  uint32_t baud_;
  uint32_t errCount_ = 0;
  static constexpr size_t kMaxPkt = 64;
};

