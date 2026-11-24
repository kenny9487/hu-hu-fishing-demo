"""辨識遊戲結束前的「是否延長 60 分鐘」確認視窗。"""
from functools import lru_cache

import cv2
import numpy as np


@lru_cache(maxsize=2)
def _load_template(path):
    # imdecode 支援 Windows 的中文路徑。
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"無法讀取延長遊戲樣板：{path}")
    return image


def extension_dialog_visible(frame, template_path):
    """frame 是 1920x1080 客戶區 BGR 畫面；僅比對提示文字所在區域。"""
    if frame.shape[:2] != (1080, 1920):
        return False
    region = cv2.cvtColor(frame[450:548, 800:1120], cv2.COLOR_BGR2GRAY)
    template = _load_template(str(template_path))
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return False
    score = cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))[1]
    return score >= 0.86
