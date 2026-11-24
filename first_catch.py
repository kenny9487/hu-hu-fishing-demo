"""辨識釣獲畫面上方的「首次捕獲」標籤並另外保存截圖。"""
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import re
import shutil

import cv2
import numpy as np


@lru_cache(maxsize=2)
def _template(path):
    # imdecode 能讀取 Windows 中文路徑，imread 在部分 OpenCV 版本不能。
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"無法讀取首次捕獲樣板：{path}")
    return image


def is_first_catch(frame, template_path):
    """frame 為 BGR 截圖；僅在通知橫幅的固定文字區比對樣板。"""
    height, width = frame.shape[:2]
    if (width, height) == (1024, 768):
        small_template = Path(template_path).with_name("first_catch_template_1024.png")
        return is_first_catch_banner(frame[40:95, 415:630], small_template)
    if width < 1100 or height < 130:
        return False
    # 遊戲使用 1920x1080；只看提示文字所在處，避免魚名與品質干擾。
    scale = height / 1080
    center = width / 2
    x1, x2 = int(center - 140 * scale), int(center + 140 * scale)
    y1, y2 = int(55 * scale), int(130 * scale)
    banner = frame[y1:y2, x1:x2]
    if banner.size == 0:
        return False
    if scale != 1:
        banner = cv2.resize(banner, (280, 75), interpolation=cv2.INTER_AREA)
    return is_first_catch_banner(banner, template_path)


def is_first_catch_banner(banner, template_path):
    """在通知橫幅的 BGR 裁切圖中辨識「首次捕獲」文字。"""
    gray = cv2.cvtColor(banner, cv2.COLOR_BGR2GRAY)
    template = _template(str(template_path))
    if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
        return False
    return cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))[1] >= 0.90


def record_first_catch(log_path, quality, quality_order, timestamp):
    """沿用 firstone.log 範本，依台灣時間中午 12 點切換今日統計。"""
    path = Path(log_path)
    zero = lambda: {name: 0 for name in quality_order}
    daily_counts, all_counts = zero(), zero()
    daily_day = entry_day = None
    current_day = (datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") -
                   timedelta(hours=12)).date()
    names = "|".join(re.escape(name) for name in quality_order)
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            header = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
            if header:
                entry_day = (datetime.strptime(header.group(1), "%Y-%m-%d %H:%M:%S") -
                             timedelta(hours=12)).date()
            if "首次捕獲統計" not in line:
                continue
            fields = {name: int(value) for name, value in
                      re.findall(rf"({names})\s*=\s*(\d+)", line)}
            if set(fields) != set(quality_order):
                continue
            if "今日首次捕獲統計" in line:
                daily_counts, daily_day = fields, entry_day
            elif "所有首次捕獲統計" in line or "首次捕獲統計" in line:
                all_counts = fields  # 兼容舊版只有「首次捕獲統計」的紀錄。
    if daily_day != current_day:
        daily_counts = zero()
    daily_counts[quality] += 1
    all_counts[quality] += 1

    def summary(counts):
        return ", ".join(f"{name}={counts[name]}" for name in quality_order)

    path.parent.mkdir(parents=True, exist_ok=True)
    # 兼容手動編輯的範本沒有結尾換行的情況。
    needs_newline = path.exists() and path.stat().st_size > 0
    if needs_newline:
        with path.open("rb") as existing:
            existing.seek(-1, 2)
            needs_newline = existing.read(1) not in (b"\n", b"\r")
    with path.open("a", encoding="utf-8") as output:
        if needs_newline:
            output.write("\n")
        output.write(
            f"[{timestamp}] 首次捕獲：{quality}\n"
            f"  今日首次捕獲統計（共 {sum(daily_counts.values())} 條）：{summary(daily_counts)}\n"
            f"  所有首次捕獲統計（共 {sum(all_counts.values())} 條）：{summary(all_counts)}\n"
        )
    return sum(all_counts.values())


def archive_first_catch(screenshot_path, frame, template_path, *, detected=False):
    """原截圖不移動；有首次捕獲標籤時額外複製到 screenshots/firstone。"""
    if not detected and not is_first_catch(frame, template_path):
        return None
    source = Path(screenshot_path)
    destination_dir = source.parent / "firstone"
    destination_dir.mkdir(exist_ok=True)
    destination = destination_dir / source.name
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination
