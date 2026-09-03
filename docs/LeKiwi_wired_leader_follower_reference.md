# LeKiwi 有线版：主动臂带从动臂 操作说明

目标：在一台装有 LeRobot 的笔记本上，用**主动臂（leader）**遥控**装在小车上的从动臂（follower SO-ARM101）**，同时能用键盘开动小车。

> 前提：本机已装好 LeRobot 环境（本仓库根 `lerobot_venv312/` + 对应的 lerobot 源码）。
> 如果你还没装，先按 Seeed wiki「安装 LeRobot」章节装好再回来。

---

## 一、整体架构（有线版）

```text
你的笔记本（这台装 LeRobot 的机器）
 ├── USB口A ← USB线 ← 主动臂控制板（leader，ID 1~6）
 ├── USB口B ← USB线 ← 从动臂/SO-ARM101 控制板（follower，ID 1~6）
 │                       └── 从动臂舵机 1~6  + 底盘舵机 7/8/9
 │
 └── 摄像头（front / wrist）也插笔记本
```

关键点：**没有树莓派中转**。主动臂和从动臂都直接插笔记本。配置里 `ip = "127.0.0.1"`（指向本机，而不是树莓派 IP）。

---

## 二、找到两个 USB 端口

每个控制板接上后，用一个端口扫描命令找出来。

在 Linux 上：
```bash
sudo chmod 666 /dev/ttyACM0
sudo chmod 666 /dev/ttyACM1
```
然后用：
```bash
lerobot-find-port
```

在 Windows 上：看「设备管理器 → 端口(COM和LPT)」，记下两个 COM 口，例如：
```text
COM3 = 主动臂 leader
COM4 = 从动臂 follower
```

---

## 三、改配置文件

配置文件在 lerobot 源码里（editable 安装位置可用 `pip show lerobot` 查询）：
```text
<lerobot 源码>/lerobot/common/robot_devices/robots/configs.py
```

找到 `LeKiwiRobotConfig`，改成下面这样（**有线版**）。

```python
@RobotConfig.register_subclass("lekiwi")
@dataclass
class LeKiwiRobotConfig(RobotConfig):
    max_relative_target: int | None = None

    # ---- 有线版：指向本机，不是树莓派 IP ----
    ip: str = "127.0.0.1"
    port: int = 5555
    video_port: int = 5556

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "front": OpenCVCameraConfig(
                camera_index=0, fps=30, width=640, height=480, rotation=90
            ),
            "wrist": OpenCVCameraConfig(
                camera_index=1, fps=30, width=640, height=480, rotation=180
            ),
        }
    )

    calibration_dir: str = ".cache/calibration/lekiwi"

    # ---- 主动臂 leader：插笔记本的 USB 口 ----
    leader_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem585A0077581",   # ← 主动臂端口，按你的改
                motors={
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex":   [3, "sts3215"],
                    "wrist_flex":   [4, "sts3215"],
                    "wrist_roll":   [5, "sts3215"],
                    "gripper":      [6, "sts3215"],
                },
            ),
        }
    )

    # ---- 从动臂 follower（含底盘三轮）----
    follower_arms: dict[str, MotorsBusConfig] = field(
        default_factory=lambda: {
            "main": FeetechMotorsBusConfig(
                port="/dev/tty.usbmodem58760431061",   # ← 从动臂端口，按你的改
                motors={
                    "shoulder_pan": [1, "sts3215"],
                    "shoulder_lift": [2, "sts3215"],
                    "elbow_flex":   [3, "sts3215"],
                    "wrist_flex":   [4, "sts3215"],
                    "wrist_roll":   [5, "sts3215"],
                    "gripper":      [6, "sts3215"],
                    "left_wheel":  (7, "sts3215"),
                    "back_wheel":  (8, "sts3215"),
                    "right_wheel": (9, "sts3215"),
                },
            ),
        }
    )

    teleop_keys: dict[str, str] = field(
        default_factory=lambda: {
            "forward": "w", "backward": "s",
            "left": "a", "right": "d",
            "rotate_left": "z", "rotate_right": "x",
            "speed_up": "r", "speed_down": "f",
            "quit": "q",
        }
    )

    mock: bool = False
```

改三处即可：
1. `ip = "127.0.0.1"`
2. leader 的 `port`
3. follower 的 `port`

---

## 四、校准两臂（先校准，再做遥操作）

校准**主动臂**：
```bash
cd <lerobot 源码目录>
python lerobot/scripts/control_robot.py \
  --robot.type=lekiwi \
  --robot.cameras='{}' \
  --control.type=calibrate \
  --control.arms='["main_leader"]'
```

校准**从动臂**（臂装在小车上再校准更准）：
```bash
python lerobot/scripts/control_robot.py \
  --robot.type=lekiwi \
  --robot.cameras='{}' \
  --control.type=calibrate \
  --control.arms='["main_follower"]'
```

> 轮子电机（7/8/9）**不需要校准**。

---

## 五、遥操作：主动臂带从动臂（有线版）

有线版 = **两个命令都在你这台笔记本上跑**（不用 SSH 到树莓派）。开两个终端。

**终端1 —— 运行/执行侧：**
```bash
cd <lerobot 源码目录>
python lerobot/scripts/control_robot.py \
  --robot.type=lekiwi \
  --control.type=remote_robot
```

**终端2 —— 遥控侧（你手握主动臂）：**
```bash
cd <lerobot 源码目录>
python lerobot/scripts/control_robot.py \
  --robot.type=lekiwi \
  --control.type=teleoperate \
  --control.fps=30
```

成功连接后，会看到类似：
```text
[INFO] Connected to remote robot at tcp://127.0.0.1:5555 ...
```

**这时**：
- 你握主动臂动 → 从动臂（小车上）跟着动
- 按键盘 W/A/S/D/Z/X → 开小车

键盘对照：
```text
W 前进   S 后退   A 左移   D 右移
Z 左转   X 右转   R 加速   F 减速
Q 退出
```

---

## 六、排查

| 现象 | 原因/处理 |
|---|---|
| 连不上 127.0.0.1:5555 | 两个终端顺序：先跑 remote_robot 再跑 teleoperate |
| 从动臂不动 | 端口填错；从动臂校准没做；舵机 ID 不是 1~6 |
| 只有臂动、车不动 | 检查底盘 7/8/9 是否接在 follower 板上、有没有电 |
| 端口权限 | Linux: `sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1` |
| 一臂的 ID 报重复 | 主动臂、从动臂各自独立插不同 USB 板，ID 1~6 各自独立没问题 |

---

## 七、注意

- 这台文档假设已在目标笔记本装好 LeRobot 环境。没装先装。
- 从动臂在小车上，USB 线长度要够从车够到笔记本，或用延长线。
- 底盘舵机 7/8/9 需要 12V 供电；从动臂舵机按它的额定电压供电。
- 主动臂和从动臂的 6 个舵机 ID 都是 1~6 没关系，因为它们插不同的控制板。
