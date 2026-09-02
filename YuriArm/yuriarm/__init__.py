"""YuriArm：SO-101 机械臂指令控制与方块抓取包。

架构原则（与父仓库 lerobot / 兄弟仓库 YuriEye 兼容共存）：
- 本包不改动父仓库任何源码，只通过 lerobot 的公共接口（SO101Follower / FeetechMotorsBus）驱动真机；
- 所有对 lerobot 的导入都放在 LerobotArm.connect() 内惰性完成，保证本包在任意 Python 中可导入、
  纯逻辑模块（protocol/planner/state_machine）不依赖硬件环境；
- YuriEye 检测结果通过 perception.py 的薄封装接入，缺失时优雅降级为手动模式。
"""
__version__ = "0.1.0"
