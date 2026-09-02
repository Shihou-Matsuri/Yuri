#pragma once
#include <Arduino.h>
#include "config.h"
#include "feetech_bus.h"

// 运动控制器：归一化<->原始换算、逐关节写目标、多关节插值执行、
// 200ms 看门狗、软件急停（本地负载监测由 main 循环调用）。
class MotionController {
 public:
  explicit MotionController(FeetechBus& bus);

  // ---- 总线原语（失败返回 false）----
  bool readAllPositions(int16_t out[NUM_JOINTS]);          // Present_Position（raw）
  bool readAllLoads(int16_t out[NUM_JOINTS]);              // Present_Load（raw，含方向位）
  bool readVoltage(float& v);                              // 平均电压（V）
  bool readTemperature(float& t);                          // 平均温度（℃）
  bool setTorque(bool on);
  bool writeGoalRaw(const int16_t raw[NUM_JOINTS]);        // 逐关节写 Goal_Position

  // ---- 归一化换算（与 lerobot motors_bus 完全一致）----
  static int16_t normToRaw(const JointDef& j, float norm);
  static float rawToNorm(const JointDef& j, int16_t raw);

  // ---- 插值执行 ----
  bool moveToNorm(const float targets[NUM_JOINTS], uint32_t durationMs);  // 从当前位形插值到目标
  bool tick();                       // 推进一帧；true=插值进行中
  bool interpActive() const { return interp_; }

  // ---- 看门狗 ----
  void feedWatchdog() { lastCmdMs_ = millis(); }
  bool watchdogExpired() const { return (uint32_t)(millis() - lastCmdMs_) > WATCHDOG_MS; }

  // ---- 急停 ----
  void estop() { estop_ = true; }
  void resume() { estop_ = false; }
  bool estopActive() const { return estop_; }

  int findJoint(const char* name) const;

 private:
  FeetechBus& bus_;
  uint32_t lastCmdMs_ = 0;
  bool estop_ = false;

  int16_t lastRaw_[NUM_JOINTS] = {};   // 最近一次命令/读到的位置（插值起点）
  int16_t from_[NUM_JOINTS];
  int16_t to_[NUM_JOINTS];
  float delta_[NUM_JOINTS];
  uint32_t stepsTotal_ = 0;
  uint32_t stepsDone_ = 0;
  bool interp_ = false;
};
