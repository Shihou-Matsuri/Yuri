#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include "config.h"
#include "feetech_bus.h"
#include "motion.h"
#include "car_motion.h"

// 行分隔 JSON 指令路由（与 PC 侧 yuriarm/protocol.py + firmware/protocol.md 对齐）。
// 返回 true 表示成功生成响应并写入 resp。
bool handleCommand(FeetechBus& bus, FeetechBus& bus2, MotionController& motion,
                   CarMotionController& car,
                   const char* line, size_t len,
                   String& resp, bool& keepalive);
