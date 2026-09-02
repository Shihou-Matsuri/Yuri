#pragma once
#include <Arduino.h>
#include "config.h"
#include "feetech_bus.h"

// 小车串行总线控制器（与主臂 MotionController 类似，但面向 3 个 arbitrary ID）。
// 仅处理注册表读写和简单的软件插值，不包含归一化关节换算。
class CarMotionController {
 public:
  CarMotionController(FeetechBus& bus);

  bool readAllPositions(int16_t out[NUM_CAR_SERVOS]);
  bool readAllLoads(int16_t out[NUM_CAR_SERVOS]);
  bool readVoltage(float& v);
  bool readTemperature(float& t);
  bool setTorque(bool on);
  bool writeGoalRaw(const int16_t raw[NUM_CAR_SERVOS]);

  bool moveToRaw(const int16_t targets[NUM_CAR_SERVOS], uint32_t durationMs);
  bool tick();
  bool interpActive() const { return interp_; }

  void feedWatchdog() { lastCmdMs_ = millis(); }
  bool watchdogExpired() const { return (uint32_t)(millis() - lastCmdMs_) > WATCHDOG_MS; }
  void estop() { estop_ = true; }
  void resume() { estop_ = false; }
  bool estopActive() const { return estop_; }
  bool torqueOn() const { return torqueOn_; }

 private:
  FeetechBus& bus_;
  uint32_t lastCmdMs_ = 0;
  bool estop_ = false;
  bool torqueOn_ = false;
  int16_t lastRaw_[NUM_CAR_SERVOS] = {};
  int16_t from_[NUM_CAR_SERVOS];
  int16_t to_[NUM_CAR_SERVOS];
  float delta_[NUM_CAR_SERVOS];
  uint32_t stepsTotal_ = 0;
  uint32_t stepsDone_ = 0;
  bool interp_ = false;
};
