@echo off
REM ============================================================
REM  LeKiwi SO-101 主动臂带动从动臂 - 遥操作启动脚本
REM  Windows 批处理。主动臂(COM7) 带动 从动臂(COM4)。
REM  轮子用独立代码控制，不在此脚本内。
REM ============================================================
cd /d C:\Users\21209\lerobot

echo.
echo [1/2] 启动遥操作: 主动臂(COM7) 带动 从动臂(COM4)
echo       握着主动臂动, 从动臂会跟着动
echo       按 Ctrl+C 停止
echo.

C:\Users\21209\lerobot_venv312\Scripts\lerobot-teleoperate.exe ^
  --robot.type=so101_follower ^
  --robot.port=COM4 ^
  --teleop.type=so101_leader ^
  --teleop.port=COM7

if %errorlevel% neq 0 (
    echo.
    echo [错误] 遥操作退出, 错误码 %errorlevel%
    echo 常见原因:
    echo   - COM4/COM7 端口不对, 或从动臂/主动臂没上电
    echo   - 舵机未校准 (需先跑校准)
    echo.
    pause
)
