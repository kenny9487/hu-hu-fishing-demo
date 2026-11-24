"""F3 的掃描碼與放鍵行為離線測試（不發送真實按鍵）。"""
import ast
import ctypes
from pathlib import Path
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))


def load_function(name, env):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<test>", "exec"), env)
    return env[name]


class AntiKickTests(unittest.TestCase):
    def test_scan_code_key_down_and_up(self):
        # 使用與 main.py 相同的 ctypes 結構，攔截 SendInput 而不操作電腦。
        names = {"MOUSEINPUT", "KEYBDINPUT", "HARDWAREINPUT", "INPUT_I", "INPUT"}
        nodes = [n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name in names]
        env = {"ctypes": ctypes, "PUL": ctypes.POINTER(ctypes.c_ulong),
               "INPUT_KEYBOARD": 1, "KEYEVENTF_KEYUP": 2, "KEYEVENTF_SCANCODE": 8}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<structs>", "exec"), env)
        sent = []

        def fake_send(count, pointer, size):
            command = ctypes.cast(pointer, ctypes.POINTER(env["INPUT"])).contents
            sent.append((command.type, command.ii.ki.wScan, command.ii.ki.dwFlags))
            return 1

        env["SendInput"] = fake_send
        send_game_key = load_function("send_game_key", env)
        send_game_key(0x1E)
        send_game_key(0x1E, release=True)
        self.assertEqual(sent, [(1, 0x1E, 8), (1, 0x1E, 10)])

    def test_release_on_pause(self):
        clock = [0.0]
        sent = []
        env = {"ANTI_KICK_HOLD": 0.12,
               "anti_kick_ready": lambda: clock[0] < 0.05,
               "time": type("Clock", (), {"monotonic": staticmethod(lambda: clock[0]),
                                      "sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s))}),
               "send_game_key": lambda scan, release=False: sent.append((scan, release))}
        move = load_function("anti_kick_move", env)
        self.assertFalse(move(0x20))
        self.assertEqual(sent, [(0x20, False), (0x20, True)])

    def test_f3_only_sends_one_a(self):
        loop = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                    and n.name == "anti_kick_loop")
        calls = [n for n in ast.walk(loop) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "anti_kick_move"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0].value, 0x1E)


if __name__ == "__main__":
    unittest.main()
