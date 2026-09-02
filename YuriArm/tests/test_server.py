import json
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.arm import YuriArm  # noqa: E402
from yuriarm.commands import CommandContext  # noqa: E402
from yuriarm.config import ArmConfig  # noqa: E402
from yuriarm.server import YuriArmServer  # noqa: E402


class TestServer(unittest.TestCase):
    def setUp(self):
        self.cfg = ArmConfig.from_dict({})
        self.arm = YuriArm(self.cfg, mock=True)
        self.arm.connect()
        self.ctx = CommandContext(arm=self.arm, config=self.cfg)
        self.ctx.server_mode = True
        self.server = YuriArmServer(self.ctx, host="127.0.0.1", port=0)
        self.server.start()
        self.port = self.server._server.server_address[1]

    def tearDown(self):
        self.server.stop()

    def _send(self, raw: str) -> dict:
        with socket.create_connection(("127.0.0.1", self.port), timeout=5.0) as sock:
            sock.sendall((raw + "\n").encode("utf-8"))
            data = sock.recv(65536).decode("utf-8", errors="replace")
        return json.loads(data)

    def test_ping(self):
        r = self._send('{"id": 1, "cmd": "ping", "params": {}}')
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["pong"], True)

    def test_move_joints(self):
        r = self._send('{"id": 2, "cmd": "move_joints", "params": {"targets": {"shoulder_lift": 20.0}, "duration": 0.2}}')
        self.assertTrue(r["ok"], str(r))
        self.assertAlmostEqual(r["result"]["shoulder_lift"], 20.0, places=1)

    def test_calibrate_rejected_in_server_mode(self):
        r = self._send('{"id": 3, "cmd": "calibrate", "params": {}}')
        self.assertFalse(r["ok"])
        self.assertIn("服务器模式", r["error"])

    def test_estop_and_resume(self):
        r = self._send('{"id": 4, "cmd": "estop", "params": {}}')
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["state"], "estop")
        r2 = self._send('{"id": 5, "cmd": "resume", "params": {}}')
        self.assertTrue(r2["ok"], str(r2))

    def test_unknown_command(self):
        r = self._send('{"id": 6, "cmd": "nope", "params": {}}')
        self.assertFalse(r["ok"])
        self.assertIn("未知指令", r["error"])

    def test_bad_json(self):
        r = self._send("this is not json")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
