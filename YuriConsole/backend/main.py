"""综合遥控台后端：FastAPI + 静态托管（前端 build 产物）。

用法:
    python main.py --mock                 # 离线 mock 演示，自动开浏览器
    python main.py --mock --webview       # pywebview 桌面壳
    python main.py                        # 真机模式（连 ESP32/主动臂）
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parent
_CONSOLE = _BACKEND.parent
_BUNDLE = Path(getattr(sys, "_MEIPASS", str(_CONSOLE)))  # PyInstaller 解压目录；源码跑 = YuriConsole
_DIST = _BUNDLE / "frontend" / "dist"

sys.path.insert(0, str(_BACKEND))
from console_core import ConsoleCore  # noqa: E402
from wired_car import WiredCarCore  # noqa: E402

core = ConsoleCore(mock=False)
wired = WiredCarCore()
app = FastAPI(title="Yuri 综合遥控台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ConnectReq(BaseModel):
    link: str = "tcp"
    serial_port: str | None = None
    leader_port: str = "COM7"


class KeyReq(BaseModel):
    key: str


class EnabledReq(BaseModel):
    enabled: bool


@app.get("/api/state")
def state() -> dict:
    return {**core.state(), "wired": wired.state()}


@app.post("/api/connect")
def connect(req: ConnectReq) -> JSONResponse:
    core.mock = False
    msg = core.connect(link=req.link, serial_port=req.serial_port, leader_port=req.leader_port)
    return JSONResponse({"ok": msg == "ok", "msg": msg})


@app.post("/api/disconnect")
def disconnect() -> JSONResponse:
    core.disconnect()
    return JSONResponse({"ok": True})


@app.post("/api/car/press")
def car_press(req: KeyReq) -> JSONResponse:
    core.car_press(req.key)
    return JSONResponse({"ok": True})


@app.post("/api/car/release")
def car_release() -> JSONResponse:
    core.car_release()
    return JSONResponse({"ok": True})


class VelReq(BaseModel):
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0


@app.post("/api/car/vel")
def car_vel(req: VelReq) -> JSONResponse:
    """手柄摇杆连续速度（m/s、rad/s），0 即刹停。"""
    core.car_vel_set(req.vx, req.vy, req.omega)
    return JSONResponse({"ok": True})


@app.post("/api/car/estop")
def car_estop() -> JSONResponse:
    core.car_estop_cmd()
    return JSONResponse({"ok": True})


@app.post("/api/global/estop")
def global_estop() -> JSONResponse:
    core.global_estop_cmd()
    return JSONResponse({"ok": True})


@app.post("/api/resume")
def resume() -> JSONResponse:
    core.resume_cmd()
    return JSONResponse({"ok": True})


@app.post("/api/arm/enabled")
def arm_enabled(req: EnabledReq) -> JSONResponse:
    core.set_arm_enabled(req.enabled)
    return JSONResponse({"ok": True})


class ArmPadReq(BaseModel):
    enabled: bool = False
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@app.post("/api/arm/pad")
def arm_pad(req: ArmPadReq) -> JSONResponse:
    """手柄控机械臂（速率）；x=pan、y=lift、z=elbow。"""
    core.arm_pad_set(req.enabled, req.x, req.y, req.z)
    return JSONResponse({"ok": True})


class GripperReq(BaseModel):
    action: str = "open"   # open | close


@app.post("/api/gripper")
def gripper(req: GripperReq) -> JSONResponse:
    core.gripper_cmd(req.action)
    return JSONResponse({"ok": True})


@app.get("/api/logs")
def logs(level: str | None = None) -> list[dict]:
    return core.get_logs(level)


class WiredConnectReq(BaseModel):
    port: str | None = None


@app.post("/api/wired/connect")
def wired_connect(req: WiredConnectReq) -> JSONResponse:
    msg = wired.connect(req.port)
    return JSONResponse({"ok": msg == "ok", "msg": msg})


@app.post("/api/wired/disconnect")
def wired_disconnect() -> JSONResponse:
    wired.disconnect()
    return JSONResponse({"ok": True})


@app.post("/api/wired/press")
def wired_press(req: KeyReq) -> JSONResponse:
    wired.press(req.key)
    return JSONResponse({"ok": True})


@app.post("/api/wired/release")
def wired_release() -> JSONResponse:
    wired.release()
    return JSONResponse({"ok": True})


@app.post("/api/wired/estop")
def wired_estop() -> JSONResponse:
    wired.estop()
    return JSONResponse({"ok": True})


# ---- 静态托管（前端 npm run build 产物）----
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")


@app.get("/")
def index():
    if _DIST.exists():
        return FileResponse(_DIST / "index.html")
    return JSONResponse({"hint": "前端未构建：cd YuriConsole/frontend && npm run build"})


def _open_browser(url: str) -> None:
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()


def main() -> int:
    global core
    ap = argparse.ArgumentParser(description="Yuri 综合遥控台后端")
    ap.add_argument("--mock", action="store_true", help="离线 mock 模式")
    ap.add_argument("--webview", action="store_true", help="用 pywebview 桌面壳（需本机 WebView2）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    if args.mock:
        core = ConsoleCore(mock=True)
        core.connect()

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    if args.webview or getattr(sys, "frozen", False):
        try:
            import webview

            threading.Thread(
                target=lambda: uvicorn.run(app, host=args.host, port=args.port, log_level="warning"),
                daemon=True,
            ).start()
            webview.create_window("Yuri 综合遥控台", url, width=1280, height=820, min_size=(1100, 700))
            webview.start()
            return 0
        except Exception as exc:
            print(f"[main] 桌面壳不可用({exc})，退回浏览器")
    _open_browser(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())