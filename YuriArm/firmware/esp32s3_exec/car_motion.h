#pragma once
#include <Arduino.h>
#include "config.h"
#include "feetech_bus.h"

// 小车串行总线控制器（与从动臂 MotionController 类似，但面向 3 个 arbitrary ID）。
// 同时支持两种互斥的控制模式：
//   1. 位置模式（servo）：writeGoalRaw / moveToRaw —— 0~4095 插值，舵机伺服模式；
//   2. 电机恒速模式（motor）：enterDriveMode + writeDriveSpeeds —— kiwi 全向轮等
//      连续旋转轮，写 0x2E 速度寄存器（BIT15 幅值编码），由 car_drive 指令驱动。
// 模式切换：car_drive 首次调用自动 enterDriveMode；位置指令（car_move/car_home）
// 前若处于电机模式会自动 leaveDriveMode 切回伺服，保证两种指令流任意顺序都安全。
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

  // ---- 电机恒速模式（car_drive：kiwi 全向轮速度控制） ----
  bool enterDriveMode();                                   // 切电机模式+扭矩开+清 0 速；幂等
  void leaveDriveMode();                                   // 切回伺服模式+扭矩关；幂等
  bool writeDriveSpeeds(const int16_t raw[NUM_CAR_SERVOS]); // 限幅写速度；成功置 driving_
  bool driveZero();                                        // 写全 0 速并清 driving_（保扭矩刹停）
  bool driveActive() const { return driving_; }            // 是否处于速度输出状态
  bool driveModeOn() const { return driveMode_; }          // 舵机是否已切电机模式

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
  bool driveMode_ = false;   // 3 个舵机已处于电机恒速模式
  bool driving_ = false;     // 正在按 writeDriveSpeeds 的速度持续输出
  int16_t lastRaw_[NUM_CAR_SERVOS] = {};
  int16_t from_[NUM_CAR_SERVOS];
  int16_t to_[NUM_CAR_SERVOS];
  float delta_[NUM_CAR_SERVOS];
  uint32_t stepsTotal_ = 0;
  uint32_t stepsDone_ = 0;
  bool interp_ = false;
};
