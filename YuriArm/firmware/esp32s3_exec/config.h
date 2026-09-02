#pragma once
#include <Arduino.h>

// ===================== WiFi AP（笔记本直连，免路由器） =====================
#define WIFI_SSID        "YuriArm-AP"
#define WIFI_PASSWORD    "yuriarm123"
#define TCP_PORT         8765
#define WIFI_MAX_CLIENTS 2

// ===================== 安全参数（与 PC 侧 configs/arm.json 对齐） =====================
#define WATCHDOG_MS        500     // 500ms 内未收到任何指令/心跳 -> 停止运动
                                    // 设计值 200ms 针对 WiFi TCP（RTT 1-5ms）；
                                    // BLE / 无电机总线超时场景下 200ms 太紧，放宽到 500ms 仍能安全兜底
#define MOVE_STEPS_HZ      20.0f   // 插值步频（PC 侧 safety.move_steps_hz=20）
#define DEFAULT_ESTOP_LOAD 1500.0f // Present_Load 绝对值阈值（5V 工况，见 config.py 注释）

// ===================== 引脚（ESP32-S3-DevKitC-1 默认；换板只改这里） =====================
#define PIN_UART1_TX 17   // 主臂总线 TX（STS3215 x6；17→Waveshare TX，18→Waveshare RX，同号直连）
#define PIN_UART1_RX 18   // 主臂总线 RX
#define PIN_UART1_DE -1   // Waveshare Adapter(A) 用 TX 自动方向，不需要 DE；-1 = 不使用
#define PIN_UART2_TX 19   // 小车总线（可选，M6；避开主臂 15/16）
#define PIN_UART2_RX 20
#define PIN_UART2_DE 13   // Waveshare Adapter(A) 的 UART 模式不使用，保持悬空即可
#define PIN_LED      48   // DevKitC-1 板载 RGB（NeoPixel），活动指示
#define ARM_BUS_BAUD 1000000  // STS3215 默认 1Mbps

// ===================== 小车总线（UART2，可选 M6） =====================
#define NUM_CAR_SERVOS 3
// 小车 3 个舵机的 ID；若实际 ID 不是 1/2/3，只改这里或先用 USB 模式查一下
static const uint8_t CAR_SERVO_IDS[NUM_CAR_SERVOS] = {1, 2, 3};
// 小车测试默认中点：0~4095 的原始位置，舵机在伺服模式下通常 2048 为中间
#define CAR_SERVO_MID_RAW 2048

// ===================== 关节表（与 PC 侧标定 zgq_follower_arm.json 一致，2026-09-01） =====================
// 归一化单位：身体关节 -100..100（RANGE_M100_100），gripper 0..100（RANGE_0_100），
// 换算公式与 lerobot motors_bus.py 完全一致。
enum class NormMode : uint8_t { RANGE_M100_100, RANGE_0_100 };

struct JointDef {
  const char* name;
  uint8_t id;
  NormMode mode;
  int range_min;
  int range_max;
  float estop_load;   // Present_Load 绝对值阈值（可被协议指令覆盖）
};

static const JointDef JOINTS[] = {
  {"shoulder_pan",  1, NormMode::RANGE_M100_100,  787, 3126, 1500},
  {"shoulder_lift", 2, NormMode::RANGE_M100_100,  986, 3252, 1500},
  {"elbow_flex",    3, NormMode::RANGE_M100_100,  920, 3128, 1500},
  {"wrist_flex",    4, NormMode::RANGE_M100_100,  922, 3154, 1500},
  {"wrist_roll",    5, NormMode::RANGE_M100_100,  193, 3984, 1500},
  {"gripper",       6, NormMode::RANGE_0_100,    1485, 2913, 1500},
};
static constexpr int NUM_JOINTS = (int)(sizeof(JOINTS) / sizeof(JOINTS[0]));

// ===================== STS3215 控制表寄存器地址（lerobot feetech/tables.py） =====================
#define REG_OVERLOAD_TORQUE     36  // 1B
#define REG_TORQUE_ENABLE       40  // 1B
#define REG_ACCELERATION        41  // 1B
#define REG_GOAL_POSITION       42  // 2B
#define REG_PRESENT_POSITION    56  // 2B
#define REG_PRESENT_LOAD        60  // 2B
#define REG_PRESENT_VOLTAGE     62  // 1B
#define REG_PRESENT_TEMPERATURE 63  // 1B
#define REG_MOVING              66  // 1B


