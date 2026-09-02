"""本地 TCP JSON 指令服务器。

外部程序（脚本 / GUI / 未来 ML 管线）通过 localhost TCP 发送行分隔 JSON 指令
（protocol.Command），服务器逐条执行并返回 protocol.CommandResult。
默认只监听 127.0.0.1，避免局域网暴露控制端口。

同一时间只有一个 YuriArm 实例；命令由 YuriArm 内部 RLock 串行化。
"""
from __future__ import annotations

import json
import logging
import socketserver
import threading

from .commands import CommandContext, dispatch
from .protocol import Command, CommandResult

logger = logging.getLogger(__name__)


class YuriArmServer:
    """封装 TCP 服务器生命周期。"""

    def __init__(self, ctx: CommandContext, host: str = "127.0.0.1", port: int = 8765):
        self.ctx = ctx
        self.host = host
        self.port = port
        self._server: socketserver.ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("服务器已在运行")
        server = _TCPServer((self.host, self.port), _Handler)
        server.ctx = self.ctx
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True, name="yuriarm-server")
        self._thread.start()
        logger.info("YuriArm 指令服务器启动于 %s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None


class _Handler(socketserver.StreamRequestHandler):
    """处理一条连接：逐行读取 JSON 指令并回写 JSON 结果。"""

    def handle(self) -> None:  # noqa: D102
        ctx: CommandContext = self.server.ctx  # type: ignore[attr-defined]
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                cmd = Command.parse(line)
            except Exception as e:  # noqa: BLE001
                self._send(CommandResult.fail(f"协议错误: {e}"))
                continue
            result = dispatch(ctx, cmd)
            self._send(result)

    def _send(self, result: CommandResult) -> None:
        payload = json.dumps(result.to_dict(), ensure_ascii=False, default=str) + "\n"
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()


class _TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    ctx: CommandContext  # 由 start() 注入
