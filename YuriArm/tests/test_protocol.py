import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yuriarm.protocol import (  # noqa: E402
    Command,
    CommandResult,
    ProtocolError,
    is_server_safe,
)


class TestProtocol(unittest.TestCase):
    def test_command_roundtrip(self):
        c = Command(cmd="move_joints", params={"targets": {"shoulder_lift": 30.0}, "duration": 2.0}, id=7)
        d = c.to_dict()
        c2 = Command.from_dict(d)
        self.assertEqual(c2.cmd, "move_joints")
        self.assertEqual(c2.params["targets"]["shoulder_lift"], 30.0)
        self.assertEqual(c2.id, 7)

    def test_command_parse_json_line(self):
        c = Command.parse('{"id": 1, "cmd": "ping", "params": {}}')
        self.assertEqual(c.cmd, "ping")
        self.assertEqual(c.id, 1)

    def test_unknown_command_rejected(self):
        with self.assertRaises(ProtocolError):
            Command.from_dict({"cmd": "fly_to_moon"})

    def test_params_must_be_dict(self):
        with self.assertRaises(ProtocolError):
            Command.from_dict({"cmd": "ping", "params": [1, 2]})

    def test_missing_cmd_rejected(self):
        with self.assertRaises(ProtocolError):
            Command.from_dict({"params": {}})

    def test_bad_json_rejected(self):
        with self.assertRaises(ProtocolError):
            Command.parse("not json at all")

    def test_result_roundtrip(self):
        r = CommandResult.ok_result({"positions": {"x": 1.0}}, id=3)
        d = r.to_dict()
        r2 = CommandResult.from_dict(d)
        self.assertTrue(r2.ok)
        self.assertEqual(r2.id, 3)

    def test_result_fail(self):
        r = CommandResult.fail("boom", id=1)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "boom")

    def test_server_safe(self):
        self.assertTrue(is_server_safe("move_joints"))
        self.assertTrue(is_server_safe("estop"))
        self.assertFalse(is_server_safe("calibrate"))


if __name__ == "__main__":
    unittest.main()
