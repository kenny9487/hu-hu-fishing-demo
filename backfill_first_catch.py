"""掃描已存的釣獲截圖，將畫面顯示「首次捕獲」者複製到 firstone。"""
from pathlib import Path
import shutil

import cv2
import numpy as np
from PIL import Image

from first_catch import is_first_catch_banner


def backfill(screenshot_dir, template_path):
    screenshot_dir = Path(screenshot_dir)
    destination_dir = screenshot_dir / "firstone"
    copied = 0
    checked = 0
    for source in sorted(screenshot_dir.glob("*.png")):
        destination = destination_dir / source.name
        if destination.exists():
            continue
        try:
            with Image.open(source) as image:
                if image.size == (1920, 1080):
                    banner = np.asarray(image.crop((820, 55, 1100, 130)).convert("RGB"))
                    selected_template = template_path
                elif image.size == (1024, 768):
                    banner = np.asarray(image.crop((415, 40, 630, 95)).convert("RGB"))
                    selected_template = Path(template_path).with_name("first_catch_template_1024.png")
                else:
                    continue
            if is_first_catch_banner(cv2.cvtColor(banner, cv2.COLOR_RGB2BGR), selected_template):
                destination_dir.mkdir(exist_ok=True)
                shutil.copy2(source, destination)
                copied += 1
                print(f"First catch: {source.name}", flush=True)
            checked += 1
        except (OSError, ValueError, cv2.error) as exc:
            print(f"Skipped {source.name}: {exc}", flush=True)
    print(f"Checked {checked} screenshots, copied {copied} new first catches.", flush=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    backfill(root / "screenshots", root / "first_catch_template.png")
