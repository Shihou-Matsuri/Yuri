# CameraCar 舵机标定

> 状态：2026-09-04 正在校准，尚未完成。用户需要逐个确认实际位置和方向。

## 当前硬件

- 有线相机车走 USB 直连 Feetech 总线，默认 `COM21 @ 1M`
- 扫描发现在线 ID：`4、5、6`（另出现 `254`，当前按广播/无关设备忽略）
- 上一版默认映射：`ID5=前中`，`ID6=后左`，`ID4=后右`
- 上一版默认方向：前轮正，后左反，后右反

> 不要直接信任上面映射和方向。本次用户要求重新校准电机编号，必须逐舵机确认后才能写回。

## 标定流程

从仓库根执行：

```powershell
# 1. 先只做只读扫描
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --scan

# 2. 逐个低速点动，每次结束后会立即停轮、关扭矩
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 4 --duration 2.0 --test-rpm 20
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 5 --duration 2.0 --test-rpm 20
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 6 --duration 2.0 --test-rpm 20
```

每次点动后由用户回答两个问题：

1. 该 ID 对应：`前中`、`后左`、还是 `后右`？
2. 该 ID 正转时，物理方向是否需要反向？

## 记录表

| ID | 用户确认的位置 | 用户确认的方向 | 最终配置 |
|---|---|---|---|
| 4 | 待确认 | 待确认 | 待写入 |
| 5 | 待确认 | 待确认 | 待写入 |
| 6 | 待确认 | 待确认 | 待写入 |

## 完成后的修改

把最终结果写回：

```text
YuriChassis/camera_car_drive.py
  CarConfig.front_id
  CarConfig.rear_left_id
  CarConfig.rear_right_id
  CarConfig.__post_init__ 中的 directions
```

如果映射或方向改变，必须：

1. 更新 `YuriConsole/backend/wired_car.py` 中复用的 `cc.CarConfig`（它直接读取该文件，通常无需重复硬编码）
2. 更新 `YuriChassis/README.md` 与文档中的映射表
3. 运行 `YuriChassis/tests`，确认 `test_default_rear_wheels_are_reversed` 等测试与最终方向一致
4. 重建 `YuriConsole/frontend` 和 `YuriConsole/release/YuriConsole.exe`
5. 更新 `YuriConsole/release/YuriConsole.exe.sha256`
6. 提交并推送

## 构建与验证命令

```powershell
# Python 测试
.\lerobot_venv312\Scripts\python.exe -m unittest discover -s YuriChassis\tests -v

# 前端构建
cd YuriConsole/frontend
npm.cmd run build
```
