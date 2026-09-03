#include <math.h>
#include "protocol.h"

// 指令表（与 protocol.py KNOWN_COMMANDS 对齐；固件实现子集）
static const char* kCommands[] = {
    "ping", "status", "move_joints", "teleop_joints", "move_to_pose", "home",
    "open_gripper", "close_gripper", "estop", "resume", "telemetry",
    "bus_diag", "bus_scan", "bus_raw", "bus_pos", "bus_goto", "car_scan", "car_status", "car_move",
    "car_home", "car_torque", "car_stop", "car_resume", "car_drive",
};
static const int kNumCommands = (int)(sizeof(kCommands) / sizeof(kCommands[0]));

static bool findJointIdx(const char* name, int& idx) {
  idx = -1;
  for (int i = 0; i < NUM_JOINTS; i++) {
    if (strcmp(JOINTS[i].name, name) == 0) { idx = i; return true; }
  }
  return false;
}

// 简易合拢：按步进压向目标，负载超过阈值=夹住；到位=没夹到（timeout）。
// 完整版（停滞确认窗口）后续按 arm.py close_gripper 移植。
static void closeGripper(FeetechBus& bus, JsonDocument& resp,
                         float targetNorm, float maxLoad, float stepNorm, uint32_t timeoutMs) {
  int gi = 6 - 1;  // gripper 恒为最后一个关节（id=6）
  int16_t load = 0;
  uint32_t t0 = millis();
  float cur = 0;
  {
    int16_t raw = 0;
    if (bus.readWord(JOINTS[gi].id, REG_PRESENT_POSITION, raw, 15)) cur = MotionController::rawToNorm(JOINTS[gi], raw);
  }
  float dir = (targetNorm < cur) ? -1.0f : 1.0f;
  while (millis() - t0 < timeoutMs) {
    int16_t loadRaw = 0;
    bus.readWord(JOINTS[gi].id, REG_PRESENT_LOAD, loadRaw, 15);
    load = (loadRaw < 0) ? (int16_t)-loadRaw : loadRaw;
    if (load > maxLoad) {
      resp["result"] = "gripped";
      resp["position"] = cur;
      resp["load"] = load;
      return;
    }
    float nxt = cur + dir * stepNorm;
    if (dir < 0 && nxt < targetNorm) nxt = targetNorm;
    if (dir > 0 && nxt > targetNorm) nxt = targetNorm;
    int16_t raw = MotionController::normToRaw(JOINTS[gi], nxt);
    if (!bus.writeWord(JOINTS[gi].id, REG_GOAL_POSITION, raw, 20)) break;
    cur = nxt;
    if ((dir < 0 && cur <= targetNorm + 0.5f) || (dir > 0 && cur >= targetNorm - 0.5f)) break;
    delay(50);
  }
  resp["result"] = "timeout";
  resp["position"] = cur;
  resp["load"] = load;
}

static void buildTelemetry(FeetechBus& bus, MotionController& motion, JsonDocument& resp) {
  int16_t pos[NUM_JOINTS], loads[NUM_JOINTS];
  bool posOk = motion.readAllPositions(pos);
  bool loadOk = motion.readAllLoads(loads);
  float v = 0, t = 0;
  bool vOk = motion.readVoltage(v);
  bool tOk = motion.readTemperature(t);

  JsonObject posObj = resp["result"]["positions"].to<JsonObject>();
  JsonObject loadObj = resp["result"]["loads"].to<JsonObject>();
  for (int i = 0; i < NUM_JOINTS; i++) {
    posObj[JOINTS[i].name] = MotionController::rawToNorm(JOINTS[i], pos[i]);
    loadObj[JOINTS[i].name] = loads[i];
  }
  resp["result"]["voltage"] = vOk ? v : (float)0;
  resp["result"]["temperature"] = tOk ? t : (float)0;
  resp["result"]["torque_on"] = !motion.estopActive();
  if (!posOk) resp["result"]["pos_read_error"] = true;
  if (!loadOk) resp["result"]["load_read_error"] = true;
}

// 单路总线诊断：环回测试 + 逐电机 ping（uart1 按从动臂 JOINTS，uart2 按小车 CAR_SERVO_IDS）
static void diagBus(JsonDocument& resp, const char* key, FeetechBus& b, bool carBus = false) {
  uint8_t echoBuf[16];
  size_t echoCount = 0;
  bool echoOk = b.echoTest(echoBuf, 16, echoCount, 25);
  JsonObject o = resp["result"][key].to<JsonObject>();
  o["echo_bytes"] = echoCount;
  o["echo_ok"] = echoOk;
  char hex[64] = "";
  size_t pos = 0;
  for (size_t i = 0; i < echoCount && i < 16; i++) {
    pos += snprintf(hex + pos, sizeof(hex) - pos, "%02X ", echoBuf[i]);
  }
  o["echo_hex"] = hex;
  JsonArray motors = o["motors"].to<JsonArray>();
  if (!carBus) {
    for (int i = 0; i < NUM_JOINTS; i++) {
      JsonObject m = motors.add<JsonObject>();
      m["name"] = JOINTS[i].name;
      m["id"] = JOINTS[i].id;
      m["ping"] = b.ping(JOINTS[i].id, 25);
    }
  } else {
    for (int i = 0; i < NUM_CAR_SERVOS; i++) {
      JsonObject m = motors.add<JsonObject>();
      m["name"] = String("car_") + String(CAR_SERVO_IDS[i]);
      m["id"] = CAR_SERVO_IDS[i];
      m["ping"] = b.ping(CAR_SERVO_IDS[i], 25);
    }
  }
}

// 全 ID 扫描：找总线上所有真实存在的舵机，并读第一个的电压/温度
static void scanBus(JsonObject& result, FeetechBus& b, const char* key) {
  JsonArray found = result["found"].to<JsonArray>();
  int count = 0;
  uint16_t firstVolt = 0;
  uint8_t firstTemp = 0;
  bool haveRead = false;
  for (int id = 0; id < 254; id++) {
    if (b.ping((uint8_t)id, 8)) {
      found.add(id);
      count++;
      if (!haveRead) {
        uint8_t volt = 0, temp = 0;
        if (b.read((uint8_t)id, REG_PRESENT_VOLTAGE, 1, &volt, 15)) {
          firstVolt = (uint16_t)volt;
          haveRead = true;
        }
        if (b.read((uint8_t)id, REG_PRESENT_TEMPERATURE, 1, &temp, 15)) {
          firstTemp = temp;
        }
      }
    }
  }
  result["count"] = count;
  result["voltage_first"] = firstVolt;
  result["temperature_first"] = firstTemp;
  result["uart"] = key;
}

// 对 ID 1~6 各发一个 PING，把 RX 收到的原始字节原样打印成 HEX（不解析）
static void scanRaw(JsonDocument& resp, FeetechBus& b) {
  JsonObject ids = resp["result"]["ids"].to<JsonObject>();
  for (int id = 1; id <= 6; id++) {
    uint8_t buf[64];
    size_t count = 0;
    bool any = b.pingRaw((uint8_t)id, buf, 64, count, 120);
    char hex[200] = "";
    size_t p = 0;
    for (size_t i = 0; i < count; i++) {
      p += snprintf(hex + p, sizeof(hex) - p, "%02X ", buf[i]);
    }
    JsonObject o = ids[String(id)].to<JsonObject>();
    o["count"] = (int)count;
    o["hex"] = hex;
    o["any"] = any;
  }
  resp["result"]["uart"] = "uart1_tx17_rx18";
}

static int findCarIndex(uint8_t id) {
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    if (CAR_SERVO_IDS[i] == id) return i;
  }
  return -1;
}

static void buildCarTelemetry(CarMotionController& car, JsonDocument& resp) {
  int16_t pos[NUM_CAR_SERVOS];
  int16_t loads[NUM_CAR_SERVOS];
  bool posOk = car.readAllPositions(pos);
  bool loadOk = car.readAllLoads(loads);
  float v = 0, t = 0;
  bool vOk = car.readVoltage(v);
  bool tOk = car.readTemperature(t);

  JsonArray motors = resp["result"]["motors"].to<JsonArray>();
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    JsonObject m = motors.add<JsonObject>();
    m["id"] = CAR_SERVO_IDS[i];
    m["position"] = pos[i];
    m["load"] = loads[i];
  }
  resp["result"]["voltage"] = vOk ? v : (float)0;
  resp["result"]["temperature"] = tOk ? t : (float)0;
  resp["result"]["torque_on"] = car.torqueOn();
  resp["result"]["active"] = car.interpActive();
  resp["result"]["drive_mode"] = car.driveModeOn();   // 舵机是否已切电机恒速模式
  resp["result"]["drive_active"] = car.driveActive(); // 是否正在按 car_drive 速度行驶
  if (!posOk) resp["result"]["pos_read_error"] = true;
  if (!loadOk) resp["result"]["load_read_error"] = true;
}

bool handleCommand(FeetechBus& bus, FeetechBus& bus2, MotionController& motion,
                   CarMotionController& car,
                   const char* line, size_t len, String& resp, bool& keepalive) {
  keepalive = false;
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line, len);
  JsonDocument out;
  out["ok"] = false;
  out["error"] = (const char*)nullptr;
  out["result"] = (const char*)nullptr;

  if (err) {
    out["error"] = "JSON parse error";
    out["result"] = (const char*)nullptr;
    serializeJson(out, resp);
    return true;
  }

  const char* cmd = doc["cmd"] | "";
  if (doc["id"].is<int>()) out["id"] = doc["id"].as<int>();
  else if (doc["id"].is<const char*>()) out["id"] = doc["id"].as<const char*>();

  bool known = false;
  for (int i = 0; i < kNumCommands; i++) {
    if (strcmp(cmd, kCommands[i]) == 0) { known = true; break; }
  }
  if (!known) {
    out["error"] = "unknown command";
    out["result"] = (const char*)nullptr;
    serializeJson(out, resp);
    return true;
  }

  JsonObject params = doc["params"].as<JsonObject>();

  if (strcmp(cmd, "ping") == 0) {
    out["ok"] = true;
    out["result"]["pong"] = true;
    keepalive = true;
  } else if (strcmp(cmd, "status") == 0) {
    out["ok"] = true;
    out["result"]["state"] = motion.estopActive() ? "estop" : (motion.interpActive() ? "busy" : "idle");
    out["result"]["torque_on"] = !motion.estopActive();
    out["result"]["watchdog_ok"] = !motion.watchdogExpired();
    out["result"]["estop"] = motion.estopActive();
    JsonArray joints = out["result"]["joints"].to<JsonArray>();
    for (int i = 0; i < NUM_JOINTS; i++) {
      JsonObject j = joints.add<JsonObject>();
      j["name"] = JOINTS[i].name;
      j["id"] = JOINTS[i].id;
    }
    keepalive = true;
  } else if (strcmp(cmd, "move_joints") == 0) {
    JsonObject targets = params["targets"].as<JsonObject>();
    if (targets.isNull() || targets.size() == 0) {
      out["error"] = "missing targets";
    } else {
      float norm[NUM_JOINTS];
      // 只有 targets 未覆盖的关节才需要当前位形；桥遥操作总发全 6 关节，
      // 此时跳过 readAllPositions（省 6 次舵机总线读 ≈ 每条指令提速数倍），
      // 否则大幅动作密集 move_joints 会让 ESP32 忙于读舵机、heartbeat 排队超时误急停。
      bool needCurrent = (int)targets.size() < NUM_JOINTS;
      if (needCurrent) {
        int16_t cur[NUM_JOINTS];
        motion.readAllPositions(cur);   // 未指定关节保持当前位形
        for (int i = 0; i < NUM_JOINTS; i++) norm[i] = MotionController::rawToNorm(JOINTS[i], cur[i]);
      } else {
        for (int i = 0; i < NUM_JOINTS; i++) norm[i] = 0.0f;  // 占位，下面全被 targets 覆盖
      }
      bool any = false;
      for (JsonPair kv : targets) {
        int idx;
        if (!findJointIdx(kv.key().c_str(), idx)) {
          out["error"] = "unknown joint";
          out["result"] = (const char*)nullptr;
          serializeJson(out, resp);
          return true;
        }
        norm[idx] = kv.value().as<float>();
        any = true;
      }
      if (!any) {
        out["error"] = "missing targets";
      } else {
        uint32_t durationMs = 1000;
        if (params["duration"].is<float>()) {
          durationMs = (uint32_t)lroundf(max(0.05f, params["duration"].as<float>()) * 1000.0f);
        } else if (params["duration"].is<int>()) {
          durationMs = (uint32_t)max(50, params["duration"].as<int>());
        }
        if (motion.moveToNorm(norm, durationMs)) {
          out["ok"] = true;
          JsonObject pos = out["result"]["positions"].to<JsonObject>();
          for (int i = 0; i < NUM_JOINTS; i++) pos[JOINTS[i].name] = norm[i];
          motion.feedWatchdog();
          keepalive = true;
        } else {
          out["error"] = motion.estopActive() ? "estop active" : "move failed";
        }
      }
    }
  } else if (strcmp(cmd, "teleop_joints") == 0) {
    // 直写遥操作（遥操作桥专用）：接收全 6 关节归一化目标，直接写 Goal_Position。
    // 无插值状态机（舵机内部速度控制自行平滑），无 readAllPositions，不回包（见 .ino 抑制）。
    // 帧即喂狗；断连 500ms 由主循环 watchdog（teleopActive 覆盖）急停。
    JsonObject targets = params["targets"].as<JsonObject>();
    if (targets.isNull() || targets.size() == 0) {
      out["error"] = "missing targets";
    } else {
      float norm[NUM_JOINTS];
      // 未指定关节保持当前 lastRaw_ 位形（避免只发部分关节时其余被归零）
      for (int i = 0; i < NUM_JOINTS; i++) {
        norm[i] = MotionController::rawToNorm(JOINTS[i], motion.lastRaw(i));
      }
      bool any = false;
      for (JsonPair kv : targets) {
        int idx;
        if (!findJointIdx(kv.key().c_str(), idx)) {
          out["error"] = "unknown joint";
          out["result"] = (const char*)nullptr;
          serializeJson(out, resp);
          return true;
        }
        norm[idx] = kv.value().as<float>();
        any = true;
      }
      if (!any) {
        out["error"] = "missing targets";
      } else if (motion.writeTeleopTargets(norm)) {
        out["ok"] = true;   // 响应会被 .ino 抑制（teleop_joints 高频不回包）
      } else {
        out["error"] = motion.estopActive() ? "estop active" : "write failed";
      }
    }
    keepalive = true;
  } else if (strcmp(cmd, "home") == 0 || strcmp(cmd, "move_to_pose") == 0) {
    const char* pose = params["pose"] | "home";
    if (strcmp(pose, "home") == 0) {
      float norm[NUM_JOINTS];
      for (int i = 0; i < NUM_JOINTS; i++) norm[i] = 0.0f;
      if (motion.moveToNorm(norm, 2000)) {
        out["ok"] = true;
        out["result"]["pose"] = "home";
        motion.feedWatchdog();
        keepalive = true;
      } else {
        out["error"] = motion.estopActive() ? "estop active" : "move failed";
      }
    } else {
      out["error"] = "unknown pose";
    }
  } else if (strcmp(cmd, "open_gripper") == 0) {
    float target = 100.0f;
    if (params["target"].is<float>()) target = params["target"].as<float>();
    int gi = 6 - 1;
    int16_t raw = MotionController::normToRaw(JOINTS[gi], target);
    if (bus.writeWord(JOINTS[gi].id, REG_GOAL_POSITION, raw, 20)) {
      out["ok"] = true;
      out["result"]["result"] = "opened";
      out["result"]["position"] = target;
      motion.feedWatchdog();
      keepalive = true;
    } else {
      out["error"] = "bus write failed";
    }
  } else if (strcmp(cmd, "close_gripper") == 0) {
    float maxLoad = params["max_load"].is<float>() ? params["max_load"].as<float>() : 450.0f;
    uint32_t timeoutMs = params["timeout"].is<float>()
                             ? (uint32_t)lroundf(params["timeout"].as<float>() * 1000.0f)
                             : 4000;
    JsonDocument resp2;
    resp2["ok"] = true;
    resp2["result"] = (const char*)nullptr;
    closeGripper(bus, resp2, 0.0f, maxLoad, 2.0f, timeoutMs);
    out["ok"] = true;
    out["result"]["result"] = resp2["result"].as<const char*>();
    out["result"]["position"] = resp2["position"].as<float>();
    out["result"]["load"] = resp2["load"].as<float>();
    motion.feedWatchdog();
    keepalive = true;
  } else if (strcmp(cmd, "estop") == 0) {
    motion.estop();
    motion.setTorque(false);
    // 全局急停联动小车：清速度刹停（保扭矩防溜坡）+ 置 estop（后续 car_drive 被拒）
    if (car.driveActive()) car.driveZero();
    car.estop();
    out["ok"] = true;
    out["result"]["estop"] = true;
    keepalive = true;
  } else if (strcmp(cmd, "resume") == 0) {
    motion.resume();
    motion.setTorque(true);
    car.resume();  // 小车恢复响应，但速度不自动恢复——需笔记本重新下发 car_drive
    out["ok"] = true;
    out["result"]["estop"] = false;
    keepalive = true;
  } else if (strcmp(cmd, "bus_pos") == 0) {
    // 读单个舵机的 Present_Position 原始 raw 值（用于重标定 range）
    int id = params["id"] | -1;
    int addr = params["addr"] | (int)REG_PRESENT_POSITION;
    int16_t raw = 0;
    if (id < 0 || id > 254 || !bus.readWord((uint8_t)id, (uint8_t)addr, raw, 20)) {
      out["ok"] = false; out["error"] = "bus read failed";
    } else {
      out["ok"] = true;
      out["result"]["id"] = id;
      out["result"]["addr"] = addr;
      out["result"]["raw"] = raw;
    }
    keepalive = true;
  } else if (strcmp(cmd, "bus_goto") == 0) {
    // 直接写单舵机 Goal_Position raw（隔离硬件驱动问题）
    int id = params["id"] | -1;
    int raw = params["raw"] | -1;
    if (id < 0 || id > 254 || raw < 0 || !bus.writeWord((uint8_t)id, REG_GOAL_POSITION, (int16_t)raw, 20)) {
      out["ok"] = false; out["error"] = "bus write failed";
    } else {
      out["ok"] = true; out["result"]["id"] = id; out["result"]["raw"] = raw;
    }
    keepalive = true;
  } else if (strcmp(cmd, "telemetry") == 0) {
    out["ok"] = true;
    buildTelemetry(bus, motion, out);
    keepalive = true;
  } else if (strcmp(cmd, "bus_diag") == 0) {
    // 总线诊断：UART1（机械臂）+ UART2（小车）环回测试 + 逐电机 ping；
    // 每个 UART 先测当前 TX/RX，再试一次交换 RX/TX，避免官方“同号”接法与常规交叉接法卡住。
    out["ok"] = true;
    diagBus(out, "uart1", bus);
    bus.swapPins();
    diagBus(out, "uart1_swap", bus);
    bus.swapPins();  // 恢复固件默认接线方向
    diagBus(out, "uart2", bus2, /*carBus=*/true);
    bus2.swapPins();
    diagBus(out, "uart2_swap", bus2, /*carBus=*/true);
    bus2.swapPins();  // 恢复固件默认接线方向
    keepalive = true;
  } else if (strcmp(cmd, "bus_scan") == 0) {
    // 全 ID 扫描 UART1，找总线上真实舵机（不会受 ID 不是 1~6 影响）
    out["ok"] = true;
    JsonObject r = out["result"].to<JsonObject>();
    scanBus(r, bus, "uart1");
    keepalive = true;
  } else if (strcmp(cmd, "bus_raw") == 0) {
    // 发 PING 并显示 RX 原始字节，排查波特率/供电/方向
    out["ok"] = true;
    scanRaw(out, bus);
    keepalive = true;
  } else if (strcmp(cmd, "car_scan") == 0) {
    // 全 ID 扫描 UART2（当前方向和交换方向）：找出小车上实际存在的舵机 ID，
    // 不依赖 CAR_SERVO_IDS，也能区分 TX/RX 接反。
    out["ok"] = true;
    JsonObject u2 = out["result"]["uart2"].to<JsonObject>();
    scanBus(u2, bus2, "uart2");
    JsonObject u2Swap = out["result"]["uart2_swap"].to<JsonObject>();
    bus2.swapPins();
    scanBus(u2Swap, bus2, "uart2_swap");
    bus2.swapPins();
    keepalive = true;
  } else if (strcmp(cmd, "car_status") == 0) {
    out["ok"] = true;
    buildCarTelemetry(car, out);
    keepalive = true;
  } else if (strcmp(cmd, "car_torque") == 0) {
    bool on = params["on"].is<bool>() ? params["on"].as<bool>() : true;
    if (car.setTorque(on)) {
      out["ok"] = true;
      out["result"]["torque_on"] = on;
    } else {
      out["error"] = "car torque write failed";
    }
    keepalive = true;
  } else if (strcmp(cmd, "car_move") == 0) {
    int16_t target[NUM_CAR_SERVOS];
    car.readAllPositions(target);  // 未指定的舵机保持当前位形
    bool any = false;
    JsonObject targetsObj = params["targets"].as<JsonObject>();
    if (!targetsObj.isNull()) {
      for (JsonPair kv : targetsObj) {
        int id = (int)strtol(kv.key().c_str(), nullptr, 10);
        int idx = findCarIndex((uint8_t)id);
        if (idx < 0) {
          out["error"] = "unknown car servo id";
          out["result"] = (const char*)nullptr;
          serializeJson(out, resp);
          return true;
        }
        target[idx] = (int16_t)kv.value().as<int>();
        any = true;
      }
    } else if (params["raw"].is<JsonArray>()) {
      JsonArray rawArr = params["raw"].as<JsonArray>();
      if (rawArr.size() > NUM_CAR_SERVOS) {
        out["error"] = "too many car targets";
      } else {
        for (size_t i = 0; i < rawArr.size(); i++) {
          target[i] = (int16_t)rawArr[i].as<int>();
          any = true;
        }
      }
    }
    if (!any) {
      out["error"] = "missing car targets";
    } else {
      uint32_t durationMs = 1000;
      if (params["duration"].is<float>()) {
        durationMs = (uint32_t)lroundf(max(0.1f, params["duration"].as<float>()) * 1000.0f);
      } else if (params["duration"].is<int>()) {
        durationMs = (uint32_t)max(100, params["duration"].as<int>());
      }
      if (car.moveToRaw(target, durationMs)) {
        out["ok"] = true;
        JsonArray motors = out["result"]["motors"].to<JsonArray>();
        for (int i = 0; i < NUM_CAR_SERVOS; i++) {
          JsonObject m = motors.add<JsonObject>();
          m["id"] = CAR_SERVO_IDS[i];
          m["target"] = target[i];
        }
      } else {
        out["error"] = car.estopActive() ? "car estop active" : "car move failed";
      }
    }
    keepalive = true;
  } else if (strcmp(cmd, "car_home") == 0) {
    int16_t target[NUM_CAR_SERVOS];
    for (int i = 0; i < NUM_CAR_SERVOS; i++) target[i] = CAR_SERVO_MID_RAW;
    uint32_t durationMs = 1000;
    if (params["duration"].is<float>()) {
      durationMs = (uint32_t)lroundf(max(0.1f, params["duration"].as<float>()) * 1000.0f);
    } else if (params["duration"].is<int>()) {
      durationMs = (uint32_t)max(100, params["duration"].as<int>());
    }
    if (car.moveToRaw(target, durationMs)) {
      out["ok"] = true;
      out["result"]["position"] = CAR_SERVO_MID_RAW;
    } else {
      out["error"] = car.estopActive() ? "car estop active" : "car move failed";
    }
    keepalive = true;
  } else if (strcmp(cmd, "car_drive") == 0) {
    // 电机恒速模式速度控制（kiwi 全向轮）：持续速度，非插值。
    // params: {"speeds":{"7":300,"8":-150,"9":0}} 或 {"raw":[300,-150,0]}
    // 值 = 有符号 raw speed，范围 ±CAR_SPEED_LIMIT；车保持该速度直到下一条
    // car_drive / car_stop / 看门狗超时（500ms 无指令自动清 0 速刹停）。
    if (car.interpActive()) {
      out["error"] = "car interp active (wait or car_stop first)";
    } else {
      int16_t speeds[NUM_CAR_SERVOS] = {0, 0, 0};
      bool any = false;
      JsonObject speedsObj = params["speeds"].as<JsonObject>();
      if (!speedsObj.isNull()) {
        for (JsonPair kv : speedsObj) {
          int id = (int)strtol(kv.key().c_str(), nullptr, 10);
          int idx = findCarIndex((uint8_t)id);
          if (idx < 0) {
            out["error"] = "unknown car servo id";
            out["result"] = (const char*)nullptr;
            serializeJson(out, resp);
            return true;
          }
          speeds[idx] = (int16_t)kv.value().as<int>();
          any = true;
        }
      } else if (params["raw"].is<JsonArray>()) {
        JsonArray rawArr = params["raw"].as<JsonArray>();
        if (rawArr.size() > NUM_CAR_SERVOS) {
          out["error"] = "too many car speeds";
        } else {
          for (size_t i = 0; i < rawArr.size(); i++) {
            speeds[i] = (int16_t)rawArr[i].as<int>();
            any = true;
          }
        }
      }
      if (!any) {
        out["error"] = "missing car speeds";
      } else if (car.writeDriveSpeeds(speeds)) {
        out["ok"] = true;
        JsonArray motors = out["result"]["motors"].to<JsonArray>();
        for (int i = 0; i < NUM_CAR_SERVOS; i++) {
          JsonObject m = motors.add<JsonObject>();
          m["id"] = CAR_SERVO_IDS[i];
          m["speed"] = speeds[i];
        }
      } else {
        out["error"] = car.estopActive() ? "car estop active (resume first)"
                                         : "car drive failed";
      }
    }
    keepalive = true;
  } else if (strcmp(cmd, "car_stop") == 0) {
    // 急停：先清速度刹停（避免扭矩切断瞬间轮子自由滑），再置 estop + 扭矩关
    if (car.driveActive()) car.driveZero();
    car.estop();
    car.setTorque(false);
    out["ok"] = true;
    out["result"]["estop"] = true;
    keepalive = true;
  } else if (strcmp(cmd, "car_resume") == 0) {
    car.resume();
    car.setTorque(true);
    out["ok"] = true;
    out["result"]["estop"] = false;
    keepalive = true;
  }

  serializeJson(out, resp);
  return true;
}

