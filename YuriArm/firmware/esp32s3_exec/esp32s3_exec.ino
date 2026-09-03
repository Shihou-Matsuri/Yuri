// YuriArm 无线执行端（ESP32-S3）固件 —— 里程碑 F1（WiFi/TCP + 协议 + 运动 + 安全）
// 设计：docs/方案设计.md M3.5；协议：firmware/protocol.md；移植源：lerobot feetech.py / scservo_sdk
#include <WiFi.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "config.h"
#include "feetech_bus.h"
#include "motion.h"
#include "car_motion.h"
#include "protocol.h"

HardwareSerial ArmSerial(1);   // UART1 -> 从动臂总线（6x STS3215 via Waveshare Adapter）
FeetechBus bus1(ArmSerial, PIN_UART1_DE, PIN_UART1_RX, PIN_UART1_TX, ARM_BUS_BAUD);
HardwareSerial CarSerial(2);   // UART2 -> 小车总线（3 舵机，可选）
FeetechBus bus2(CarSerial, PIN_UART2_DE, PIN_UART2_RX, PIN_UART2_TX, ARM_BUS_BAUD);
MotionController motion(bus1);
CarMotionController car(bus2);
WiFiServer server(TCP_PORT);

static String lineBuf;
static uint32_t lastTickMs = 0;
static uint32_t lastLoadCheckMs = 0;
static bool watchdogTripped = false;
static bool carWatchdogTripped = false;

// ---- BLE 指令通道 ----
#define BLE_SERVICE_UUID "0000ff00-0000-1000-8000-00805f9b34fb"
#define BLE_RX_UUID      "0000ff01-0000-1000-8000-00805f9b34fb"
#define BLE_TX_UUID      "0000ff02-0000-1000-8000-00805f9b34fb"
static BLECharacteristic* bleTx = nullptr;
static String bleLineBuf;
static bool bleConnected = false;
#define BLE_QUEUE_MAX 8
static String bleQueue[BLE_QUEUE_MAX];  // 响应 FIFO（防止心跳 pong 覆盖大响应）
static uint8_t bleQHead = 0, bleQTail = 0;
#define BLE_CMD_QUEUE_MAX 8
static String bleCmdQueue[BLE_CMD_QUEUE_MAX];  // 待处理指令队列（回调只入队，主循环处理）
static uint8_t bleCmdQHead = 0, bleCmdQTail = 0;
static String bleActive;               // 正在逐片发送的响应（含结尾 '\n'）
static size_t bleActiveOff = 0;        // 已发送偏移

void tickMotion() {
  uint32_t now = millis();

  // 插值推进（MOVE_STEPS_HZ 帧率）
  if (now - lastTickMs >= (uint32_t)(1000.0f / MOVE_STEPS_HZ)) {
    lastTickMs = now;
    motion.tick();
    car.tick();
  }

  // 本地负载监测：运动期间每 ~100ms 检查全部关节，超阈值 -> 本地急停（不等笔记本）
  if (motion.interpActive() && now - lastLoadCheckMs >= 100) {
    lastLoadCheckMs = now;
    int16_t loads[NUM_JOINTS];
    if (motion.readAllLoads(loads)) {
      for (int i = 0; i < NUM_JOINTS; i++) {
        int32_t a = loads[i] < 0 ? -(int32_t)loads[i] : (int32_t)loads[i];
        if (a > JOINTS[i].estop_load) {
          Serial.printf("[SAFETY] joint '%s' load %d > %d -> estop\n",
                        JOINTS[i].name, (int)a, (int)JOINTS[i].estop_load);
          motion.estop();
          motion.setTorque(false);
          watchdogTripped = false;
          break;
        }
      }
    }
  }

  // 看门狗：200ms 无指令 -> 停止运动并关力矩（协议.md 硬性要求）
  if (motion.interpActive() && motion.watchdogExpired() && !watchdogTripped) {
    watchdogTripped = true;
    Serial.println("[SAFETY] watchdog expired -> stop & torque off");
    motion.estop();
    motion.setTorque(false);
  }

  // 小车看门狗：断线/停发指令后停止运动。
  // 位置插值中 -> estop + 扭矩关（原逻辑）；电机恒速行驶中（car_drive）-> 清 0 速刹停
  // 并保持扭矩（防溜坡），比扭矩关断更安全——车会稳稳停住而不是自由滑行。
  if ((car.interpActive() || car.driveActive()) && car.watchdogExpired() && !carWatchdogTripped) {
    carWatchdogTripped = true;
    if (car.driveActive()) {
      Serial.println("[SAFETY] car drive watchdog -> zero speed (hold torque)");
      car.driveZero();
    } else {
      Serial.println("[SAFETY] car watchdog expired -> stop & torque off");
      car.estop();
      car.setTorque(false);
    }
  }
}

// 处理一行指令：返回 ok；respond=false 表示无需回包（如 heartbeat 心跳）。
// 任何有效指令都喂狗。
bool processCommandLine(const String& line, String& resp, bool& respond) {
  respond = true;
  if (line.indexOf("heartbeat") >= 0) {
    // 心跳/保活：只喂狗，不回包（避免高频心跳的 pong 流量拥塞 BLE 链路）
    motion.feedWatchdog();
    car.feedWatchdog();
    watchdogTripped = false;
    carWatchdogTripped = false;
    respond = false;
    return true;
  }
  bool keepalive = false;
  bool ok = handleCommand(bus1, bus2, motion, car, line.c_str(), line.length(), resp, keepalive);
  if (ok) {
    motion.feedWatchdog();
    car.feedWatchdog();
    watchdogTripped = false;
    carWatchdogTripped = false;
  }
  return ok;
}

// 从任意 Stream（USB 串口 / TCP）读行分隔 JSON 指令并回包；同一套协议，传输无关
void handleStream(Stream& s) {
  while (s.available()) {
    char c = (char)s.read();
    if (c == '\n') {
      lineBuf.trim();
      if (lineBuf.length() > 0) {
        String resp;
        bool respond = true;
        if (processCommandLine(lineBuf, resp, respond) && respond) {
          s.print(resp);
          s.print('\n');
        }
      }
      lineBuf = "";
    } else if (c != '\r') {
      if (lineBuf.length() >= 512) lineBuf = "";
      lineBuf += c;
    }
  }
}

void handleClient(WiFiClient& client) {
  Serial.println("[TCP] client connected");
  while (client.connected()) {
    tickMotion();
    handleStream(client);
  }
  Serial.println("[TCP] client disconnected");
  client.stop();
}

// ---- BLE 指令通道（GATT：RX=写指令，TX=通知回包） ----
class BLEConnCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* s) override {
    bleConnected = true;
    Serial.println("[BLE] client connected");
  }
  void onDisconnect(BLEServer* s) override {
    bleConnected = false;
    Serial.println("[BLE] client disconnected, re-advertising");
    BLEDevice::startAdvertising();
  }
};

class BLERxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* ch) override {
    String v = ch->getValue();
    for (size_t i = 0; i < v.length(); i++) {
      char c = v[i];
      if (c == '\n') {
        bleLineBuf.trim();
        if (bleLineBuf.length() > 0) {
          // 收到完整行：立即喂狗（回调不做任何慢操作/总线访问，避免与主循环并发争用 UART）
          motion.feedWatchdog();
          watchdogTripped = false;
          // 压入指令队列，由主循环统一处理
          if (((uint8_t)(bleCmdQHead + 1) % BLE_CMD_QUEUE_MAX) == bleCmdQTail) {
            bleCmdQTail = (uint8_t)((bleCmdQTail + 1) % BLE_CMD_QUEUE_MAX);  // 满：丢最旧
          }
          bleCmdQueue[bleCmdQHead] = bleLineBuf;
          bleCmdQHead = (uint8_t)((bleCmdQHead + 1) % BLE_CMD_QUEUE_MAX);
        }
        bleLineBuf = "";
      } else if (c != '\r') {
        if (bleLineBuf.length() >= 512) bleLineBuf = "";
        bleLineBuf += c;
      }
    }
  }
};

void bleInit() {
  BLEDevice::init("YuriArm-S3");
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new BLEConnCallbacks());
  BLEService* service = server->createService(BLE_SERVICE_UUID);
  bleTx = service->createCharacteristic(BLE_TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  bleTx->addDescriptor(new BLE2902());
  BLECharacteristic* rx = service->createCharacteristic(
      BLE_RX_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  rx->setCallbacks(new BLERxCallbacks());
  service->start();
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLE_SERVICE_UUID);
  BLEDevice::startAdvertising();
  Serial.println("[BLE] advertising as YuriArm-S3");
}

void setup() {
  Serial.begin(460800);
  Serial0.begin(460800);   // UART0：CH343 USB 转串口 / 调试口（GPIO43/44）
  delay(300);
  Serial.println();
  Serial.println("[YuriArm ESP32-S3 exec] boot");
  Serial0.println("[YuriArm ESP32-S3 exec] boot (UART0)");

  bus1.begin();
  bus2.begin();

  // 上电默认力矩关闭（协议.md 安全要求 #1）
  motion.setTorque(false);
  car.setTorque(false);
  motion.feedWatchdog();
  car.feedWatchdog();

  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] AP '%s' password '%s'\n", WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] AP IP: %s\n", WiFi.softAPIP().toString().c_str());

  server.begin();
  Serial.printf("[TCP] listening on :%d\n", TCP_PORT);

  bleInit();
  Serial.println("[ready] laptop: connect to AP, then TCP 192.168.4.1:8765");
}

// BLE 响应 FIFO 逐片发送：每 25ms 一片（20B），保证蓝牙栈有足够时间发出
void bleFlushPending() {
  static uint32_t lastMs = 0;
  if (!bleConnected) return;
  if (bleActive.length() == 0) {
    if (bleQHead == bleQTail) return;  // 队列空
    bleActive = bleQueue[bleQTail];
    bleQTail = (uint8_t)((bleQTail + 1) % BLE_QUEUE_MAX);
    bleActiveOff = 0;
  }
  if ((uint32_t)(millis() - lastMs) < 25) return;
  lastMs = millis();
  size_t len = bleActive.length();
  size_t n = (len - bleActiveOff) > 20 ? 20 : (len - bleActiveOff);
  bleTx->setValue((uint8_t*)(bleActive.c_str() + bleActiveOff), n);
  bleTx->notify();
  bleActiveOff += n;
  if (bleActiveOff >= len) {
    bleActive = "";
    bleActiveOff = 0;
  }
}

// 主循环处理 BLE 指令队列（与总线访问同任务，避免两个任务并发访问 UART1）
void bleProcessCommands() {
  while (bleCmdQHead != bleCmdQTail) {
    String line = bleCmdQueue[bleCmdQTail];
    bleCmdQTail = (uint8_t)((bleCmdQTail + 1) % BLE_CMD_QUEUE_MAX);
    String resp;
    bool respond = true;
    if (processCommandLine(line, resp, respond) && bleTx != nullptr && respond) {
      resp += '\n';
      if (((uint8_t)(bleQHead + 1) % BLE_QUEUE_MAX) == bleQTail) {
        bleQTail = (uint8_t)((bleQTail + 1) % BLE_QUEUE_MAX);  // 满：丢最旧
      }
      bleQueue[bleQHead] = resp;
      bleQHead = (uint8_t)((bleQHead + 1) % BLE_QUEUE_MAX);
    }
  }
}

void loop() {
  tickMotion();
  handleStream(Serial);          // USB CDC（原生 USB 口）
  handleStream(Serial0);         // UART0（CH343 USB 转串口 / 调试口，默认 GPIO43/44）
  bleProcessCommands();          // BLE 指令队列 -> 主循环处理
  bleFlushPending();             // BLE 响应逐片发送
  WiFiClient client = server.available();
  if (client) {
    handleClient(client);
  }
  delay(1);
}












