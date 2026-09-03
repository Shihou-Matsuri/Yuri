"""主动臂(leader)带动从动臂(follower)遥操作 —— SO-101 版。

基于 LeRobot 0.6.1 的 Python API，把"主动臂带从动臂"封装成一个独立可运行脚本，
不经过 lerobot-teleoperate CLI，直接驱动两条 feetech 总线。

原理（普通人版）：
  主动臂 = 你握着的那台。程序每秒读很多次它的 6 个关节角度(get_action)。
  从动臂 = 执行的那台。程序把读到的角度原样写给从动臂(send_action)。
  你动主动臂 → 从动臂跟着动，即"遥操作"。

两条总线各自独立(各自 USB/COM 口)，舵机 ID 各 1~6，互不冲突。
轮子：用 YuriChassis/ 的 kiwi_drive.py 独立控制，与本脚本无关。

运行前：
  1. lerobot 0.6.1 已装(本机: lerobot_venv312/（本仓库根）)
  2. 主动臂 USB 插好(默认 COM7)，从动臂 USB 插好(默认 COM4)
  3. 两块臂已上电、已校准(首次会自动触发校准, 需人摆臂配合)
  4. 停止按 Ctrl+C
"""

import sys
import time

from lerobot.teleoperators.so_leader.config_so_leader import SOLeaderTeleopConfig
from lerobot.teleoperators.so_leader.so_leader import SOLeader
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig
from lerobot.robots.so_follower.so_follower import SOFollower

# ---------- 硬件配置(按实际改) ----------
LEADER_PORT = "COM7"     # 主动臂串口
FOLLOWER_PORT = "COM4"   # 从动臂串口
FPS = 30                 # 控制频率(帧/秒)，越高越跟手
USE_DEGREES = True       # 角度用度(默认)


def main() -> None:
    # 1. 建配置
    leader_config = SOLeaderTeleopConfig(
        port=LEADER_PORT,
        use_degrees=USE_DEGREES,
    )
    follower_config = SOFollowerRobotConfig(
        port=FOLLOWER_PORT,
        use_degrees=USE_DEGREES,
    )

    # 2. 连两块臂(首次/无校准文件会触发 calibrate, 需人摆臂配合)
    leader = SOLeader(leader_config)
    follower = SOFollower(follower_config)

    leader.connect()
    follower.connect()
    # 从动臂需要扭矩来执行跟随(主动臂保持无扭矩只读, 便于你手掰)
    # enable_torque 在 feetech bus 层(不在 SOFollower 上)
    follower.bus.enable_torque()

    print("\n=== 遥操作开始: 握主动臂动, 从动臂跟随 ===")
    print(f"频率 {FPS}Hz | 停止按 Ctrl+C\n")

    period = 1.0 / FPS
    try:
        while True:
            t0 = time.perf_counter()

            # 读主动臂当前角度
            raw_action = leader.get_action()

            # 把角度原样写给从动臂(这里 key 都是 "<关节>.pos")
            follower.send_action(raw_action)

            # 按 fps 限速, 避免满速空转
            elapsed = time.perf_counter() - t0
            sleep = period - elapsed
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print("\n收到停止信号, 断开...")
    finally:
        leader.disconnect()
        follower.disconnect()
        print("已断开主动臂与从动臂")


if __name__ == "__main__":
    main()
