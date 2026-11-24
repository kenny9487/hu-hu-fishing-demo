"""離線測試：不啟動遊戲、不發出真實滑鼠輸入。"""
import ast
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from session_extend import extension_dialog_visible  # noqa: E402


class SessionExtendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 使用已隨程式發布的文字樣板產生畫面，不依賴私人的原始截圖。
        cls.template = ROOT / "session_extend_template.png"
        text = cv2.imdecode(np.fromfile(str(cls.template), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        cls.modal = np.zeros((1080, 1920, 3), dtype=np.uint8)
        h, w = text.shape
        cls.modal[470:470 + h, 826:826 + w] = cv2.cvtColor(text, cv2.COLOR_GRAY2BGR)
        cls.blank = np.zeros_like(cls.modal)

    def test_detect_dialog_only(self):
        self.assertTrue(extension_dialog_visible(self.modal, self.template))
        self.assertFalse(extension_dialog_visible(self.blank, self.template))
        self.assertFalse(extension_dialog_visible(self.modal[:768, :1024], self.template))

    def test_click_yes_in_f1_and_f3_modes(self):
        # main.py 在匯入時會尋找遊戲視窗，僅編譯待測函式，注入假的輸入。
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "handle_session_extension")
        clicks, releases = [], []
        context = dict(
            fishing_generation=0, session_extension_last_click=0,
            fishing_paused=False, bite_check_active=threading.Event(),
            session_extension_rebaseline=threading.Event(),
            session_extension_active=threading.Event(), session_extension_lock=threading.Lock(),
            win32gui=SimpleNamespace(GetForegroundWindow=lambda: 42), hwnd=42,
            resource_path=lambda filename: str(ROOT / filename),
            extension_dialog_visible=extension_dialog_visible,
            left_up=lambda: releases.append(True),
            pyautogui=SimpleNamespace(click=lambda x, y: clicks.append((x, y))),
            safe_log=lambda message: None,
            time=SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None),
            window_left=0, window_top=0,
        )
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<handler>", "exec"), context)

        for biting, paused, expected_generation in [(True, False, 0),
                                                    (False, False, 1),
                                                    (False, True, 1)]:
            context["bite_check_active"].clear()
            context["session_extension_rebaseline"].clear()
            if biting:
                context["bite_check_active"].set()
            context["fishing_paused"] = paused
            context["session_extension_last_click"] = 0
            frames = iter([self.modal, self.blank])
            context["capture_game_frame"] = lambda: next(frames)
            self.assertTrue(context["handle_session_extension"](self.modal))
            self.assertEqual(context["fishing_generation"], expected_generation)
            self.assertEqual(context["session_extension_rebaseline"].is_set(), biting)
            self.assertFalse(context["session_extension_active"].is_set())
        self.assertEqual(clicks, [(1040, 589)] * 3)
        self.assertEqual(len(releases), 3)
        self.assertFalse(context["handle_session_extension"](self.blank))


if __name__ == "__main__":
    unittest.main()
