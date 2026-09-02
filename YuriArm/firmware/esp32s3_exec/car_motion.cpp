#include "car_motion.h"

CarMotionController::CarMotionController(FeetechBus& bus) : bus_(bus) {}

bool CarMotionController::readAllPositions(int16_t out[NUM_CAR_SERVOS]) {
  bool all = true;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    int16_t v = 0;
    if (bus_.readWord(CAR_SERVO_IDS[i], REG_PRESENT_POSITION, v, 15)) {
      out[i] = v;
    } else {
      all = false;
      out[i] = lastRaw_[i];
    }
  }
  memcpy(lastRaw_, out, sizeof(lastRaw_));
  return all;
}

bool CarMotionController::readAllLoads(int16_t out[NUM_CAR_SERVOS]) {
  bool all = true;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    int16_t v = 0;
    if (bus_.readWord(CAR_SERVO_IDS[i], REG_PRESENT_LOAD, v, 15)) {
      out[i] = v;
    } else {
      all = false;
      out[i] = 0;
    }
  }
  return all;
}

bool CarMotionController::readVoltage(float& v) {
  int sum = 0, cnt = 0;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    int16_t raw = 0;
    if (bus_.readWord(CAR_SERVO_IDS[i], REG_PRESENT_VOLTAGE, raw, 15)) {
      sum += (int)raw;
      cnt++;
    }
  }
  if (cnt == 0) return false;
  v = sum / 10.0f / cnt;
  return true;
}

bool CarMotionController::readTemperature(float& t) {
  int sum = 0, cnt = 0;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    int16_t raw = 0;
    if (bus_.readWord(CAR_SERVO_IDS[i], REG_PRESENT_TEMPERATURE, raw, 15)) {
      sum += (int)raw;
      cnt++;
    }
  }
  if (cnt == 0) return false;
  t = (float)sum / cnt;
  return true;
}

bool CarMotionController::setTorque(bool on) {
  bool all = true;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    if (!bus_.writeByte(CAR_SERVO_IDS[i], REG_TORQUE_ENABLE, on ? 1 : 0, 20)) all = false;
  }
  torqueOn_ = on;
  return all;
}

bool CarMotionController::writeGoalRaw(const int16_t raw[NUM_CAR_SERVOS]) {
  bool all = true;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    if (!bus_.writeWord(CAR_SERVO_IDS[i], REG_GOAL_POSITION, raw[i], 20)) all = false;
  }
  memcpy(lastRaw_, raw, sizeof(lastRaw_));
  return all;
}

bool CarMotionController::moveToRaw(const int16_t targets[NUM_CAR_SERVOS], uint32_t durationMs) {
  if (estop_) return false;
  // 位置指令要求舵机处于伺服模式；若之前在电机恒速模式则先切回
  if (driveMode_) leaveDriveMode();
  int16_t cur[NUM_CAR_SERVOS];
  if (!readAllPositions(cur)) memcpy(cur, lastRaw_, sizeof(cur));

  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    from_[i] = cur[i];
    to_[i] = targets[i];
  }
  uint32_t duration = max(50UL, durationMs);
  stepsTotal_ = max(1UL, (uint32_t)lroundf(duration * MOVE_STEPS_HZ / 1000.0f));
  stepsDone_ = 0;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    delta_[i] = (float)(to_[i] - from_[i]) / stepsTotal_;
  }
  if (!setTorque(true)) return false;
  interp_ = true;
  return true;
}

// ---- 电机恒速模式（car_drive） ----

bool CarMotionController::enterDriveMode() {
  if (driveMode_) return true;  // 幂等：已处于电机模式
  if (estop_) return false;
  // 位置插值进行中不允许切模式（先等它结束或发 car_stop）
  if (interp_) return false;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    // 切电机恒速模式 + 扭矩开（写速度前先清 0，避免上电瞬间乱转）
    if (!bus_.writeByte(CAR_SERVO_IDS[i], REG_RUN_MODE, CAR_MODE_MOTOR, 20)) return false;
    if (!bus_.writeByte(CAR_SERVO_IDS[i], REG_TORQUE_ENABLE, 1, 20)) return false;
    int16_t zero = 0;
    if (!bus_.writeMotorSpeed(CAR_SERVO_IDS[i], REG_MOVING_SPEED, zero, 20)) return false;
  }
  driveMode_ = true;
  driving_ = false;
  torqueOn_ = true;
  return true;
}

void CarMotionController::leaveDriveMode() {
  if (!driveMode_) return;  // 幂等
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    int16_t zero = 0;
    bus_.writeMotorSpeed(CAR_SERVO_IDS[i], REG_MOVING_SPEED, zero, 20);  // 先停
    bus_.writeByte(CAR_SERVO_IDS[i], REG_RUN_MODE, 0, 20);               // 回伺服模式
    bus_.writeByte(CAR_SERVO_IDS[i], REG_TORQUE_ENABLE, 0, 20);          // 扭矩关
  }
  driveMode_ = false;
  driving_ = false;
  torqueOn_ = false;
}

bool CarMotionController::writeDriveSpeeds(const int16_t raw[NUM_CAR_SERVOS]) {
  if (estop_) return false;
  if (!driveMode_ && !enterDriveMode()) return false;
  if (!torqueOn_ && !setTorque(true)) return false;  // car_torque off 后重开，防静默不转
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    // 限幅到 CAR_SPEED_LIMIT，防止误下发极端值
    int32_t v = raw[i];
    if (v > CAR_SPEED_LIMIT) v = CAR_SPEED_LIMIT;
    if (v < -CAR_SPEED_LIMIT) v = -CAR_SPEED_LIMIT;
    if (!bus_.writeMotorSpeed(CAR_SERVO_IDS[i], REG_MOVING_SPEED, (int16_t)v, 20)) return false;
  }
  driving_ = true;  // 正在按该速度持续输出
  memcpy(lastRaw_, raw, sizeof(lastRaw_));  // lastRaw_ 仅作位置回退参考，速度下无意义但保持不脏
  return true;
}

bool CarMotionController::driveZero() {
  int16_t zero[NUM_CAR_SERVOS] = {0, 0, 0};
  if (!driveMode_) return true;  // 不在电机模式，无需停
  bool all = true;
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    if (!bus_.writeMotorSpeed(CAR_SERVO_IDS[i], REG_MOVING_SPEED, zero[i], 20)) all = false;
  }
  driving_ = false;  // 已刹停（保持扭矩，防溜坡）
  return all;
}

bool CarMotionController::tick() {
  if (!interp_) return false;
  if (stepsDone_ >= stepsTotal_) {
    writeGoalRaw(to_);
    interp_ = false;
    return false;
  }
  int16_t raw[NUM_CAR_SERVOS];
  for (int i = 0; i < NUM_CAR_SERVOS; i++) {
    raw[i] = (int16_t)lroundf(from_[i] + delta_[i] * (float)stepsDone_);
  }
  writeGoalRaw(raw);
  stepsDone_++;
  return true;
}
