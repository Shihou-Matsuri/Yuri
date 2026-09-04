# CameraCar 舵机标定

> 状态：2026-09-04 已完成。最终结果已写回默认配置、测试、GUI、YuriConsole 与独立 CameraCar 发布包。

## 当前硬件

- 有线相机车走 USB 直连 Feetech 总线，默认 `COM21 @ 1M`
- 扫描确认在线 ID：`4、5、6`（`254` 按广播/无关设备忽略）
- 本次真机确认映射：`ID4=前中`，`ID5=后左`，`ID6=后右`
- 本次真机确认正方向：`ID4=顺时针`，`ID5=逆时针`，`ID6=顺时针`

历史旧映射 `ID5=前中、ID6=后左、ID4=后右` 已不再作为当前配置。

## 校准结果

| ID | 用户确认的位置 | 用户确认的正方向 | 最终 `directions` |
|---|---|---|---|
| 4 | 前中 | 顺时针 | -1 |
| 5 | 后左 | 逆时针 | 1 |
| 6 | 后右 | 顺时针 | -1 |

`CarConfig` 当前默认：

```text
front_id = 4
rear_left_id = 5
rear_right_id = 6
directions = {4: -1, 5: 1, 6: -1}
```

## 标定流程（重校准）

从仓库根执行：

```powershell
# 1. 先只做只读扫描
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --scan

# 2. 逐个低速点动，每次结束后会立即停轮、关扭矩
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 4 --duration 2.0 --test-rpm 20
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 5 --duration 2.0 --test-rpm 20
.\lerobot_venv312\Scripts\python.exe .\YuriChassis\camera_car_drive.py --port COM21 --one-wheel 6 --duration 2.0 --test-rpm 20
```

每次点动后等待用户回答：

1. 该 ID 对应：`前中`、`后左`、还是 `后右`？
2. 该 ID 正方向是 `顺时针` 还是 `逆时针`？

## 同步与验证

映射或方向改变时必须：

1. 更新 `YuriChassis/camera_car_drive.py` 的 ID 与 `directions`
2. 同步 `YuriChassis/README.md`、`YuriConsole/README.md` 和本校准表
3. 更新 `YuriChassis/tests`，确认 `test_default_directions_match_calibration` 等测试
4. 重建 `YuriChassis/release/CameraCarController.exe`、`YuriConsole/frontend` 与 `YuriConsole/release/YuriConsole.exe`
5. 更新对应 `.sha256` 校验文件
6. 提交并推送

## 构建与验证命令

```powershell
# Python 测试
.\lerobot_venv312\Scripts\python.exe -m unittest discover -s YuriChassis\tests -v

# 前端构建
cd YuriConsole/frontend
npm.cmd run build
```
