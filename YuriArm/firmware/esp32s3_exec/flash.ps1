# YuriArm ESP32-S3 一键编译+烧录
# 用法: powershell -ExecutionPolicy Bypass -File flash.ps1 [-Port COM17]
# 注意: ESP32-S3 原生 USB 口需手动进下载模式：按住 BOOT -> 点一下 RESET -> 松开 BOOT
param([string]$Port = "COM17")

$cli = "$env:USERPROFILE\.arduino-cli\arduino-cli.exe"
$fqbn = "esp32:esp32:esp32s3:CDCOnBoot=cdc"
$sketch = $PSScriptRoot

Write-Host "[1/2] compiling ..." -ForegroundColor Cyan
& $cli compile --fqbn $fqbn $sketch
if ($LASTEXITCODE -ne 0) { Write-Host "compile FAILED" -ForegroundColor Red; exit 1 }

Write-Host "[2/2] uploading to $Port (hold BOOT + tap RESET first!) ..." -ForegroundColor Cyan
& $cli upload -p $Port --fqbn $fqbn $sketch
if ($LASTEXITCODE -ne 0) { Write-Host "upload FAILED - 是否按了 BOOT?" -ForegroundColor Red; exit 1 }

Write-Host "OK - 烧录完成" -ForegroundColor Green
