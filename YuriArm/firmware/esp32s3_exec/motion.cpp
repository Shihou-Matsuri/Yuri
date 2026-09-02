#include "motion.h"

MotionController::MotionController(FeetechBus& bus) : bus_(bus) {}

int MotionController::findJoint(const char* name) const {
  for (int i = 0; i < NUM_JOINTS; i++) {
    if (strcmp(JOINTS[i].name, name) == 0) return i;
  }
  return -1;
}

int16_t MotionController::normToRaw(const JointDef& j, float norm) {
  float r;
  if (j.mode == NormMode::RANGE_0_100) {
    r = (norm / 100.0f) * (j.range_max - j.range_min) + j.range_min;
  } else {
    r = ((norm + 100.0f) / 200.0f) * (j.range_max - j.range_min) + j.range_min;
  }
  if (r < j.range_min) r = j.range_min;
  if (r > j.range_max) r = j.range_max;
  return (int16_t)lroundf(r);
}

float MotionController::rawToNorm(const JointDef& j, int16_t raw) {
  float r = (float)raw;
  if (r < j.range_min) r = j.range_min;
  if (r > j.range_max) r = j.range_max;
  float frac = (r - j.range_min) / (float)(j.range_max - j.range_min);
  if (j.mode == NormMode::RANGE_0_100) return frac * 100.0f;
  return frac * 200.0f - 100.0f;
}

bool MotionController::readAllPositions(int16_t out[NUM_JOINTS]) {
  bool all = true;
  for (int i = 0; i < NUM_JOINTS; i++) {
    int16_t v = 0;
    if (bus_.readWord(JOINTS[i].id, REG_PRESENT_POSITION, v, 15)) {
      out[i] = v;
    } else {
      all = false;
      out[i] = lastRaw_[i];  // 读失败用最近值兜底
    }
  }
  memcpy(lastRaw_, out, sizeof(lastRaw_));
  return all;
}

bool MotionController::readAllLoads(int16_t out[NUM_JOINTS]) {
  bool all = true;
  for (int i = 0; i < NUM_JOINTS; i++) {
    int16_t v = 0;
    if (bus_.readWord(JOINTS[i].id, REG_PRESENT_LOAD, v, 15)) {
      out[i] = v;
    } else {
      all = false;
      out[i] = 0;
    }
  }
  return all;
}

bool MotionController::readVoltage(float& v) {
  int sum = 0, cnt = 0;
  for (int i = 0; i < NUM_JOINTS; i++) {
    int16_t raw = 0;
    if (bus_.readWord(JOINTS[i].id, REG_PRESENT_VOLTAGE, raw, 15)) {
      sum += (int)raw;  // 0.1V 单位
      cnt++;
    }
  }
  if (cnt == 0) return false;
  v = sum / 10.0f / cnt;
  return true;
}

bool MotionController::readTemperature(float& t) {
  int sum = 0, cnt = 0;
  for (int i = 0; i < NUM_JOINTS; i++) {
    int16_t raw = 0;
    if (bus_.readWord(JOINTS[i].id, REG_PRESENT_TEMPERATURE, raw, 15)) {
      sum += (int)raw;  // ℃
      cnt++;
    }
  }
  if (cnt == 0) return false;
  t = (float)sum / cnt;
  return true;
}

bool MotionController::setTorque(bool on) {
  bool all = true;
  for (int i = 0; i < NUM_JOINTS; i++) {
    if (!bus_.writeByte(JOINTS[i].id, REG_TORQUE_ENABLE, on ? 1 : 0, 20)) all = false;
  }
  return all;
}

bool MotionController::writeGoalRaw(const int16_t raw[NUM_JOINTS]) {
  bool all = true;
  for (int i = 0; i < NUM_JOINTS; i++) {
    if (!bus_.writeWord(JOINTS[i].id, REG_GOAL_POSITION, raw[i], 20)) all = false;
  }
  memcpy(lastRaw_, raw, sizeof(lastRaw_));
  return all;
}

bool MotionController::moveToNorm(const float targets[NUM_JOINTS], uint32_t durationMs) {
  if (estop_) return false;
  // 起点 = 最近已知位形（若总线空闲则读一次真实位置）
  int16_t cur[NUM_JOINTS];
  if (!readAllPositions(cur)) memcpy(cur, lastRaw_, sizeof(cur));

  for (int i = 0; i < NUM_JOINTS; i++) {
    from_[i] = cur[i];
    to_[i] = normToRaw(JOINTS[i], targets[i]);
  }
  stepsTotal_ = max(1UL, (uint32_t)lroundf(durationMs * MOVE_STEPS_HZ / 1000.0f));
  stepsDone_ = 0;
  for (int i = 0; i < NUM_JOINTS; i++) {
    delta_[i] = (float)(to_[i] - from_[i]) / stepsTotal_;
  }
  interp_ = true;
  return true;
}

bool MotionController::tick() {
  if (!interp_) return false;
  if (stepsDone_ >= stepsTotal_) {
    // 收尾：精确写最终目标
    writeGoalRaw(to_);
    interp_ = false;
    return false;
  }
  int16_t raw[NUM_JOINTS];
  for (int i = 0; i < NUM_JOINTS; i++) {
    raw[i] = (int16_t)lroundf(from_[i] + delta_[i] * (float)stepsDone_);
  }
  writeGoalRaw(raw);
  stepsDone_++;
  return true;
}
