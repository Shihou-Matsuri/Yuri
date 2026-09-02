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
