# ======== 猛兽派对钓鱼辅助主流程代码整理版（使用 mss 加速截图 + 数字变化检测）========

# ====== 1. 基础模块导入 ======
import ctypes
import time
import sys
import random
import traceback
import os
import platform
from datetime import datetime, timedelta, timezone

from log.fish_probability_report import generate_report
from first_catch import archive_first_catch, is_first_catch, record_first_catch
from session_extend import extension_dialog_visible

import cv2
import numpy as np
import pygetwindow as gw

# ====== 新增：资源路径适配（PyInstaller 兼容）======

# 原始偵測座標來自 1024x768；1920x1080 時依畫面高度縮放，
# 中央 UI 以畫面中心對齊，右側 UI 以右邊界對齊。
REFERENCE_WIDTH, REFERENCE_HEIGHT = 1024, 768
TARGET_WIDTH, TARGET_HEIGHT = 1920, 1080


def ui_rect(rel_x, rel_y, rel_w, rel_h, width, height, anchor="center"):
    scale = height / REFERENCE_HEIGHT
    base_x = rel_x * REFERENCE_WIDTH
    if anchor == "right":
        x = width - (REFERENCE_WIDTH - base_x) * scale
    else:
        x = width / 2 + (base_x - REFERENCE_WIDTH / 2) * scale
    return (int(x), int(rel_y * height),
            max(1, int(rel_w * REFERENCE_WIDTH * scale)),
            max(1, int(rel_h * REFERENCE_HEIGHT * scale)))



def resource_path(relative_path):
    """ 获取资源文件的真实路径（开发模式 or PyInstaller 打包模式） """
    try:
        # PyInstaller 打包后，资源在临时目录 _MEIxxxxx
        base_path = sys._MEIPASS
    except Exception:
        # 开发模式：使用当前脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

DEBUG_SAVE_IMAGES = False

# 依赖检测
try:
    import pyautogui
except Exception as e:
    print("请安装: pip install pyautogui ，报错信息:", e)
    raise

try:
    import mss
except Exception as e:
    print("请安装: pip install mss ，报错信息:", e)
    raise

USE_KEYBOARD = True
try:
    import keyboard
except Exception as e:
    USE_KEYBOARD = False
    print("请安装: pip install keyboard ，报错信息:", e)
    raise

try:
    import win32gui
except Exception as e:
    print("请安装: pip install win32gui ，报错信息:", e)
    raise

# 品质统计：今日累计跨同一天的重启延续；桶周期统计只记录上次满桶后的收获。
QUALITY_ORDER = ["标准", "非凡", "稀有", "史诗", "传奇"]
star_quality_count = {q: 0 for q in QUALITY_ORDER}
bucket_quality_count = {q: 0 for q in QUALITY_ORDER}
paused_due_to_bucket_full = False
statistics_logged = False


def reset_bucket_statistics():
    """开始新的鱼桶周期。"""
    for quality in QUALITY_ORDER:
        bucket_quality_count[quality] = 0
    if 'log_window' in globals() and log_window:
        log_window._update_stats_display()


TAIWAN_TIMEZONE = timezone(timedelta(hours=8))


def get_application_directory():
    """取得实际启动文件所在位置，兼容 Python 与 PyInstaller 单档执行档。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_logical_day_key():
    """依台灣時間中午 12 點切換每日統計的日期。"""
    logical_day = datetime.now(TAIWAN_TIMEZONE) - timedelta(hours=12)
    return logical_day.strftime("%Y%m%d")


def get_calendar_day_key():
    """取得台灣曆法日期，用於遷移舊版午夜切換的日誌。"""
    return datetime.now(TAIWAN_TIMEZONE).strftime("%Y%m%d")


def get_daily_log_path():
    """取得逻辑当天的统计日志路径，并在启动时建立 log 文件夹及当天文件。"""
    log_directory = os.path.join(get_application_directory(), "log")
    os.makedirs(log_directory, exist_ok=True)
    logical_day_key = get_logical_day_key()
    log_path = os.path.join(log_directory, f"{logical_day_key}.log")

    # 舊版以午夜切換檔案；在中午前首次啟動時，將舊檔移到正確的邏輯日期。
    calendar_day_key = get_calendar_day_key()
    legacy_log_path = os.path.join(log_directory, f"{calendar_day_key}.log")
    if logical_day_key != calendar_day_key and not os.path.exists(log_path) and os.path.exists(legacy_log_path):
        os.replace(legacy_log_path, log_path)

    if not os.path.exists(log_path):
        with open(log_path, "a", encoding="utf-8"):
            pass
    return log_path


def load_daily_statistics():
    """读取当天的累计统计，兼容旧日志格式并供本次启动继续累计。"""
    log_path = get_daily_log_path()
    saved_counts = {quality: 0 for quality in QUALITY_ORDER}
    found_summary = False
    try:
        with open(log_path, "r", encoding="utf-8") as log_file:
            for line in log_file:
                if "今日累計統計" not in line and "本次启动累计" not in line:
                    continue

                summary = line.split("：", 1)[-1].strip()
                line_counts = {}
                for item in summary.split(", "):
                    quality, value = item.split("=", 1)
                    if quality in QUALITY_ORDER:
                        line_counts[quality] = int(value)

                if set(line_counts) == set(QUALITY_ORDER):
                    found_summary = True
                    # 当日累计只会增加；取最大值可避开旧版写入的空白统计。
                    for quality in QUALITY_ORDER:
                        saved_counts[quality] = max(saved_counts[quality], line_counts[quality])

        if not found_summary:
            return None

        for quality in QUALITY_ORDER:
            star_quality_count[quality] = saved_counts[quality]
        return sum(star_quality_count.values())
    except (OSError, ValueError) as e:
        print(f"讀取今日統計日誌失敗: {e}")
        return None


def refresh_probability_report():
    """依目前執行檔旁的 log 重建報表；報表失敗不影響釣魚。"""
    try:
        generate_report(os.path.join(get_application_directory(), "log"))
    except Exception as e:
        print(f"更新魚類品質機率統計失敗: {e}")


def save_statistics_log(reason):
    """将今天的累计统计与当前鱼桶周期追加到每日日志。"""
    global statistics_logged
    if statistics_logged:
        return

    timestamp = datetime.now(TAIWAN_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    log_path = get_daily_log_path()
    daily_summary = ", ".join(f"{quality}={star_quality_count[quality]}" for quality in QUALITY_ORDER)
    bucket_summary = ", ".join(f"{quality}={bucket_quality_count[quality]}" for quality in QUALITY_ORDER)
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(
                f"[{timestamp}] {reason}\n"
                f"  今日累計統計（共 {sum(star_quality_count.values())} 條）：{daily_summary}\n"
                f"  當前魚桶週期（共 {sum(bucket_quality_count.values())} 條）：{bucket_summary}\n"
            )
        statistics_logged = True
    except Exception as e:
        print(f"统计日志写入失败: {e}")


# ====== 新增：数字变化触发器（用于替代感叹号检测） ======

class NumberChangeTrigger:
    def __init__(self, rel_x=0.873, rel_y=0.897, w=19, h=16, threshold=0.95):
        self.rel_x, self.rel_y = rel_x, rel_y
        self.w, self.h = w, h
        self.similarity_threshold = threshold
        self.base_image = None
        self.last_trigger_time = 0
        self.detection_interval = 0.3
        self.debug_counter = 0  # 用于命名当前帧
        self.base_saved = False  # 确保只保存一次基准图

    def set_base(self, frame, window_w, window_h):
        x, y, w, h = ui_rect(self.rel_x, self.rel_y,
                             self.w / REFERENCE_WIDTH, self.h / REFERENCE_HEIGHT,
                             window_w, window_h, anchor="right")
        region = self._extract(frame, x, y, w, h)
        if region is not None and region.size > 0:
            raw_base = region.copy()  # 原始彩色图
            self.base_image = self._preprocess(region)

            # === 保存基准图（只保存一次）===
            if not self.base_saved and DEBUG_SAVE_IMAGES:
                cv2.imwrite("DEBUG_BASE_RAW.png", raw_base)
                cv2.imwrite("DEBUG_BASE_PROCESSED.png", self.base_image)
                print(f"✅ 基准图已保存！位置: (x={x}, y={y}) 尺寸: {self.w}x{self.h}")
                self.base_saved = True
            return True
        return False

    def should_reel(self, frame, window_w, window_h):
        now = time.time()
        if now - self.last_trigger_time < self.detection_interval:
            return False, 1.0

        if self.base_image is None:
            return False, 1.0

        x, y, w, h = ui_rect(self.rel_x, self.rel_y,
                             self.w / REFERENCE_WIDTH, self.h / REFERENCE_HEIGHT,
                             window_w, window_h, anchor="right")
        region = self._extract(frame, x, y, w, h)
        if region is None or region.size == 0:
            return False, 1.0

        current_raw = region.copy()
        current = self._preprocess(region)
        if current.shape != self.base_image.shape:
            return False, 1.0

        diff = cv2.absdiff(self.base_image, current)
        diff_ratio = np.sum(diff > 0) / diff.size
        similarity = 1.0 - diff_ratio

        # === 每次比对都保存当前图（带序号）===
        self.debug_counter += 1
        if DEBUG_SAVE_IMAGES:
            cv2.imwrite(f"DEBUG_CURRENT_{self.debug_counter:04d}.png", current_raw)
            cv2.imwrite(f"DEBUG_CURRENT_BIN_{self.debug_counter:04d}.png", current)
        # 可选：也保存差异图
        # cv2.imwrite(f"DEBUG_DIFF_{self.debug_counter:04d}.png", diff)

        # print(f"[{self.debug_counter}] 相似度: {similarity:.4f} | 变化率: {diff_ratio:.2%}")

        if similarity < self.similarity_threshold:
            self.base_image = current.copy()
            self.last_trigger_time = now
            # print(f"🎯 触发收杆！相似度 {similarity:.4f} < 阈值 {self.similarity_threshold}")

            return True, similarity

        return False, similarity

    def _extract(self, frame, x, y, w, h):
        h_img, w_img = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _preprocess(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
        return binary


# ====== 2. 游戏窗口初始化相关 ======
def find_game_window(title_list=("猛獸派對", "猛兽派对", "Party Animals", "party animals")):
    for t in title_list:
        try:
            wins = gw.getWindowsWithTitle(t)
            if wins and hasattr(wins[0], '_hWnd'):
                return wins[0]
        except Exception as e:
            print(f"查找窗口 '{t}' 出错: {e}")
    return None

window_titles = ["猛獸派對", "猛兽派对", "Party Animals", "party animals"]
window = find_game_window(window_titles)
if window is None:
    print(f"无法找到游戏窗口，请确认已经启动，窗口名应为其中之一: {window_titles}")
    sys.exit()
hwnd = window._hWnd

# 自动切换到目标窗口
try:
    window.activate()
    print("已尝试切换至猛兽派对窗口")
    time.sleep(0.8)
except Exception as e:
    print(f"切换窗口失败，需手动切换：{e}")

# ===【关键修改】用 GetWindowRect + GetClientRect 精准对齐客户区===
try:
    # 直接將客戶區原點換算成螢幕座標，避免 16:9 視窗邊框造成偏移。
    client_width, client_height = win32gui.GetClientRect(hwnd)[2:]
    window_left, window_top = win32gui.ClientToScreen(hwnd, (0, 0))

    window_width = client_width
    window_height = client_height

    if window_width <= 0 or window_height <= 0:
        raise ValueError("窗口宽高读取结果异常！")
    print(f"✅ 客户区定位成功: {window_width}x{window_height} @ ({window_left}, {window_top})")
    if (window_width, window_height) != (TARGET_WIDTH, TARGET_HEIGHT):
        raise ValueError(f"請將遊戲客戶區設為 {TARGET_WIDTH}x{TARGET_HEIGHT}（目前為 {window_width}x{window_height}）")
except Exception as e:
    print("读取窗口大小和位置失败:", e)
    traceback.print_exc()
    sys.exit()



# 使用畫面中央的「魚桶滿了，無法釣魚」文字，不再推測 F 按鈕是否變化。
# 以下是以 1920x1080 遊戲客戶區為基準的搜尋區域。
BUCKET_BANNER_SEARCH = (790, 310, 340, 64)  # (x, y, w, h)


class BucketFullTrigger:
    def __init__(self, min_consecutive=2, threshold=0.8, template_name="bucket_full_template.png"):
        self.min_consecutive_frames = min_consecutive
        self.similarity_threshold = threshold
        self.consecutive_match_count = 0
        template_path = resource_path(template_name)
        self.full_template = cv2.imread(template_path) if os.path.exists(template_path) else None
        if self.full_template is not None:
            self.full_template = self._white_text(self.full_template)

    @staticmethod
    def _white_text(image):
        """只保留低飽和度的白字，排除河水、樹木及半透明提示背景。"""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        return cv2.inRange(hsv, (0, 0, 175), (179, 65, 255))

    def similarity(self, frame, window_w, window_h):
        """僅計算提示匹配度，分類後才累計連續影格。"""
        if self.full_template is None:
            return 0.0

        scale = window_h / TARGET_HEIGHT
        x, y, w, h = (round(v * scale) for v in BUCKET_BANNER_SEARCH)
        x += (window_w - round(TARGET_WIDTH * scale)) // 2
        region = frame[y:y+h, x:x+w]
        template = self.full_template
        if region.size == 0 or region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
            return 0.0

        mask = self._white_text(region)
        # 文字未出現時不能只因背景相似而報滿桶。
        if cv2.countNonZero(mask) < 1500:
            return 0.0
        return cv2.minMaxLoc(cv2.matchTemplate(mask, template, cv2.TM_CCOEFF_NORMED))[1]

    def confirm(self, similarity, selected):
        if selected and similarity >= self.similarity_threshold:
            self.consecutive_match_count += 1
        else:
            self.consecutive_match_count = 0
        return self.consecutive_match_count >= self.min_consecutive_frames

    def check_bucket_full(self, frame, window_w, window_h):
        """保留單一提示的檢查介面，組合檢測請使用 check_blocking_banners。"""
        similarity = self.similarity(frame, window_w, window_h)
        return self.confirm(similarity, True), similarity


def play_bucket_full_wav():
    if platform.system() == "Windows":
        try:
            import winsound
            wav_path = resource_path("bucket_full.wav")
            if not os.path.exists(wav_path):
                print("警告：未找到音频文件 bucket_full.wav")
                return
            # 先完整播放鱼桶满提示，再让后续的品质音效开始播放，
            # 避免两个非同步音效互相覆盖。
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        except Exception as e:
            print("播放 bucket_full.wav 失败:", e)

def play_sound(file_name):
    if platform.system() != "Windows":
        print("非 Windows 系统，跳过音频播放")
        return
    try:
        import winsound
        file_path = resource_path(file_name)
        if not os.path.exists(file_path):
            print(f"音频文件不存在: {file_path}")
            return
        winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        print(f"播放音频 {file_name} 失败: {e}")



# ====== 4. 鼠标控制（低级）操作相关 ======
PUL = ctypes.POINTER(ctypes.c_ulong)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)
    ]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)
    ]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),("wParamL", ctypes.c_short),("wParamH", ctypes.c_ushort)]
class INPUT_I(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT),("ki", KEYBDINPUT),("hi", HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", INPUT_I)]
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

SendInput = ctypes.windll.user32.SendInput

def _send_mouse_event(flags, dx=0, dy=0, data=0):
    extra = ctypes.c_ulong(0)
    mi = MOUSEINPUT(dx, dy, data, flags, 0, ctypes.pointer(extra))
    ii = INPUT_I()
    ii.mi = mi
    command = INPUT(INPUT_MOUSE, ii)
    SendInput(1, ctypes.byref(command), ctypes.sizeof(command))

def send_game_key(scan_code, release=False):
    """用 Windows 掃描碼送出按鍵；瞬間虛擬鍵在遊戲裡可能被忽略。"""
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if release else 0)
    extra = ctypes.c_ulong(0)
    ki = KEYBDINPUT(0, scan_code, flags, 0, ctypes.pointer(extra))
    ii = INPUT_I()
    ii.ki = ki
    command = INPUT(INPUT_KEYBOARD, ii)
    if SendInput(1, ctypes.byref(command), ctypes.sizeof(command)) != 1:
        raise OSError("SendInput 無法將掃描碼送入遊戲；請確認遊戲和程式權限相同")


def left_down():
    check_fishing_paused()
    _send_mouse_event(MOUSEEVENTF_LEFTDOWN)
def left_up(): _send_mouse_event(MOUSEEVENTF_LEFTUP)
def left_click():
    left_down()
    try:
        fishing_sleep(0.05)
    finally:
        left_up()
def move_mouse_abs(x, y):
    sx = ctypes.windll.user32.GetSystemMetrics(0)
    sy = ctypes.windll.user32.GetSystemMetrics(1)
    if sx == 0 or sy == 0:
        print("系统分辨率异常，无法移动鼠标")
        return
    nx = int(x * 65535 / (sx - 1))
    ny = int(y * 65535 / (sy - 1))
    _send_mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny)


# ====== 5. 坐标、颜色与辅助检测 ======
# （以下坐标仅用于 reel() 中的颜色判断，保留不变）
CHECK_X, CHECK_Y = (
    window_left + window_width / 2 + 100 * window_height / REFERENCE_HEIGHT,
    window_top + 0.9478 * window_height
)
CHECK_X2, CHECK_Y2 = (
    (0.5444 * window_width) + window_left,
    (0.9067 * window_height) + window_top
)
CHECK_X3, CHECK_Y3 = (
    (0.5083 * window_width) + window_left,
    (0.2811 * window_height) + window_top
)
CHECK_X, CHECK_Y = int(CHECK_X), int(CHECK_Y)
CHECK_X2, CHECK_Y2 = int(CHECK_X2), int(CHECK_Y2)
CHECK_X3, CHECK_Y3 = int(CHECK_X3), int(CHECK_Y3)

def get_pointer_color(x, y):
    try:
        color = pyautogui.pixel(x, y)
        return color
    except Exception as e:
        print(f"获取屏幕坐标({x},{y})像素颜色失败: {e}")
        raise

def color_changed(base_color, new_color, tolerance=12):
    br, bg, bb = base_color
    nr, ng, nb = new_color
    return (abs(br - nr) > tolerance) or (abs(bg - ng) > tolerance) or (abs(bb - nb) > tolerance)

def color_in_range(base_color, new_color, tolerance=12):
    br, bg, bb = base_color
    nr, ng, nb = new_color
    return (abs(br - nr) <= tolerance) and (abs(bg - ng) <= tolerance) and (abs(bb - nb) <= tolerance)


# ====== 6.x 收鱼后五角星品质检测 ======

STAR_REGION_RATIO = (0.40, 0.05, 0.20, 0.15)
COLOR_REGION_OFFSET_X = -45
COLOR_REGION_WIDTH  = 120

quality_color_map = {
    "标准": (183, 186, 193),
    "非凡": (144, 198, 90),
    "稀有": (112, 174, 241),
    "史诗": (171, 102, 251),
    "传奇": (248, 197, 68)
}

def get_dominant_color(region):
    mean_color_bgr = region.mean(axis=(0,1))
    mean_rgb = tuple(int(c) for c in mean_color_bgr[::-1])
    reshaped = region.reshape(-1, 3)
    colors, counts = np.unique(reshaped, axis=0, return_counts=True)
    dominant_bgr = colors[np.argmax(counts)]
    dominant_rgb = tuple(int(c) for c in dominant_bgr[::-1])
    return mean_rgb, dominant_rgb

def color_distance(c1, c2):
    return np.linalg.norm(np.array(c1) - np.array(c2))

def match_quality(rgb_color):
    best_name, best_dist = None, 1e9
    for q_name, qc in quality_color_map.items():
        d = color_distance(rgb_color, qc)
        if d < best_dist:
            best_name, best_dist = q_name, d
    return best_name, best_dist

def detect_star_quality(screenshot=None):
    global star_quality_count, bucket_quality_count
    check_fishing_paused()
    try:
        # === 获取当前画面 ===
        if screenshot is None:
            with mss.mss() as sct:
                region = {"top": window_top, "left": window_left, "width": window_width, "height": window_height}
                screenshot = sct.grab(region)
            img = np.array(screenshot)[:, :, :3]
        else:
            img = screenshot

        h_img, w_img = img.shape[:2]  # ← 必须添加！

        # === 动态获取模板路径 ===
        template_path = resource_path("star_template.png")
        if not os.path.exists(template_path):
            print(f"❌ 五角星模板缺失: {template_path}")
            return None

        template = cv2.imread(template_path)
        if template is None:
            print("五角星模板加载失败")
            return None

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        th, tw = template_gray.shape[:2]

        sx, sy, sw, sh = ui_rect(*STAR_REGION_RATIO, w_img, h_img)
        detect_region = img[sy:sy+sh, sx:sx+sw]
        detect_gray = cv2.cvtColor(detect_region, cv2.COLOR_BGR2GRAY)

        SCALES = [h_img / REFERENCE_HEIGHT * s for s in (1.0, 0.9, 0.8, 0.7, 0.6)]
        best_score = 0
        best_loc = None
        best_tw, best_th = tw, th
        for s in SCALES:
            template_w, template_h = max(1, int(tw*s)), max(1, int(th*s))
            if template_w > sw or template_h > sh:
                continue
            t_resized = cv2.resize(template_gray, (template_w, template_h), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(detect_gray, t_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_loc = max_loc
                best_tw, best_th = t_resized.shape[1], t_resized.shape[0]

        # 低門檻會把樹木／收線量表錯當成五角星，導致截圖與統計過早完成。
        # 現有成功截圖匹配度約 0.96～0.97；非品質畫面約 0.44～0.70。
        if best_loc is None or best_score < 0.90:
            return None

        top_left = (sx + best_loc[0], sy + best_loc[1])
        bottom_right = (top_left[0] + best_tw, top_left[1] + best_th)

        y1, y2 = top_left[1], bottom_right[1]
        scale = h_img / REFERENCE_HEIGHT
        x1 = top_left[0] + best_tw + int(COLOR_REGION_OFFSET_X * scale)
        x2 = x1 + int(COLOR_REGION_WIDTH * scale)
        color_region = img[y1:y2, x1:x2]
        if color_region.size == 0:
            return None

        mean_rgb, dominant_rgb = get_dominant_color(color_region)
        mean_q, mean_dist = match_quality(mean_rgb)
        dom_q, dom_dist = match_quality(dominant_rgb)

        quality = dom_q
        check_fishing_paused()

        # 五角星已辨識成功，儲存這次辨識使用的畫面。
        screenshot_path = None
        screenshot_error = None
        first_detected = False
        try:
            from PIL import Image

            screenshot_dir = os.path.join(get_application_directory(), "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            milliseconds = int((time.time() % 1) * 1000)

            filename = f"{quality}_{timestamp}_{milliseconds:03d}.png"
            screenshot_path = os.path.join(screenshot_dir, filename)

            # img 就是本次用來辨識五角星的畫面
            image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            Image.fromarray(image_rgb).save(screenshot_path)

        except Exception as e:
            screenshot_error = str(e)
            screenshot_path = None

        if screenshot_path:
            try:
                first_detected = is_first_catch(img, resource_path("first_catch_template.png"))
            except Exception as e:
                safe_log(f"⚠️ 首次捕獲辨識失敗：{e}")
            if first_detected:
                try:
                    first_path = archive_first_catch(
                        screenshot_path, img, resource_path("first_catch_template.png"), detected=True)
                    safe_log(f"🌟 首次捕獲截圖另存於 screenshots/firstone/{first_path.name}")
                except Exception as e:
                    safe_log(f"⚠️ 首次捕獲截圖備份失敗：{e}")

        check_fishing_paused()
        star_quality_count[quality] += 1
        bucket_quality_count[quality] += 1
        if first_detected:
            try:
                record_first_catch(
                    os.path.join(get_application_directory(), "log", "firstone.log"),
                    quality, QUALITY_ORDER,
                    datetime.now(TAIWAN_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"))
            except Exception as e:
                safe_log(f"⚠️ 首次捕獲統計寫入失敗：{e}")
        if 'log_window' in globals() and log_window:
            log_window._update_stats_display()
        return {"mean": (mean_rgb, mean_q, mean_dist),
                "dominant": (dominant_rgb, quality, dom_dist),
                "screenshot_path": screenshot_path, "screenshot_error": screenshot_error}

    except Exception as e:
        print(f"五角星检测异常: {e}")
        traceback.print_exc()
        return None



# ====== 7. 主要钓鱼流程 ======
def check_blocking_banners(frame, bucket_trigger, bait_trigger):
    """同時比較滿桶／缺餌文字，避免共同的「無法釣魚」造成誤報。"""
    bucket_score = bucket_trigger.similarity(frame, window_width, window_height)
    bait_score = bait_trigger.similarity(frame, window_width, window_height)
    bucket_ready = bucket_trigger.full_template is not None
    bait_ready = bait_trigger.full_template is not None

    selected = None
    # 兩者都有模板時，必須有明確的分數差距；平手不猜測原因。
    if bucket_ready and bait_ready:
        if bucket_score >= bucket_trigger.similarity_threshold and bucket_score - bait_score >= 0.05:
            selected = "bucket_full"
        elif bait_score >= bait_trigger.similarity_threshold and bait_score - bucket_score >= 0.05:
            selected = "bait_empty"
    elif bucket_ready and bucket_score >= bucket_trigger.similarity_threshold:
        selected = "bucket_full"
    elif bait_ready and bait_score >= bait_trigger.similarity_threshold:
        selected = "bait_empty"

    bucket_confirmed = bucket_trigger.confirm(bucket_score, selected == "bucket_full")
    bait_confirmed = bait_trigger.confirm(bait_score, selected == "bait_empty")
    if bucket_confirmed:
        print(f"✅ 偵測到魚桶滿提示（滿桶 {bucket_score:.3f}／缺餌 {bait_score:.3f}）")
        return "bucket_full"
    if bait_confirmed:
        print(f"✅ 偵測到魚餌不足提示（缺餌 {bait_score:.3f}／滿桶 {bucket_score:.3f}）")
        return "bait_empty"
    return None


def enhanced_bite_check(fishing_start_time, bucket_trigger, bait_trigger):
    """等待咬鉤；不再以固定秒數的單幀顏色誤判抛竿失敗。"""
    timeout = 60

    trigger = NumberChangeTrigger(
        rel_x=0.873,
        rel_y=0.897,
        w=19,
        h=16,
        threshold=0.95
    )

    fishing_sleep(0.8)
    with mss.mss() as sct:
        region = {"top": window_top, "left": window_left, "width": window_width, "height": window_height}
        screenshot = sct.grab(region)
        frame = np.array(screenshot)[:, :, :3]
        trigger.set_base(frame, window_width, window_height)

    last_sec = -1
    while True:
        check_fishing_paused()
        elapsed = time.time() - fishing_start_time

        # 等待咬鉤期間仍持續檢查魚桶滿、魚餌不足提示。

        fishing_sleep(0.05)
        with mss.mss() as sct:
            frame = np.array(sct.grab({
                "top": window_top, "left": window_left,
                "width": window_width, "height": window_height
            }))[:, :, :3]

        # 延長遊戲提示優先：點「是」後重設咬鉤基準，再繼續等上魚。
        if (session_extension_active.is_set() or session_extension_rebaseline.is_set() or
                extension_dialog_visible(frame, resource_path("session_extend_template.png"))):
            while True:
                check_fishing_paused()
                if win32gui.GetForegroundWindow() == hwnd:
                    handle_session_extension(frame)
                fishing_sleep(0.15)
                frame = capture_game_frame()
                if (not session_extension_active.is_set() and
                        not extension_dialog_visible(frame, resource_path("session_extend_template.png"))):
                    trigger.set_base(frame, window_width, window_height)
                    session_extension_rebaseline.clear()
                    fishing_start_time = time.time()
                    break
            continue

        blocked = check_blocking_banners(frame, bucket_trigger, bait_trigger)
        if blocked:
            return blocked

        should_reel, sim = trigger.should_reel(frame, window_width, window_height)
        if should_reel:
            check_fishing_paused()
            return True

        # 动态提示
        current_sec = int(elapsed)
        if current_sec != last_sec:
            sys.stdout.write(f"⏳等鱼儿上钩中... {current_sec} 秒")
            sys.stdout.flush()
            last_sec = current_sec

        if elapsed >= timeout:
            print(f"\r超时！{timeout} 秒内未咬钩")
            return False


def reeling_meter_visible(frame):
    """檢查收線量表左半部的亮綠色弧線（不是單一易變色像素）。"""
    h, w = frame.shape[:2]
    scale = h / TARGET_HEIGHT
    x1 = int(w / 2 - 190 * scale)
    x2 = int(w / 2 + 5 * scale)
    y1, y2 = int(890 * scale), int(1035 * scale)
    region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return False
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 100, 130), (85, 255, 255))
    return cv2.countNonZero(green) >= 1500 * scale * scale


def reel(fishing_start_time):
    """量表出現後連續消失才算收魚完成；超時則不拍魚類截圖。"""
    meter_seen = False
    missing_count = 0
    reel_start_time = time.time()
    deadline = reel_start_time + 75
    try:
        while time.time() < deadline:
            check_fishing_paused()
            left_down()
            fishing_sleep(0.6)
            left_up()
            fishing_sleep(0.3)
            with mss.mss() as sct:
                frame = np.array(sct.grab({
                    "top": window_top, "left": window_left,
                    "width": window_width, "height": window_height
                }))[:, :, :3]
            if reeling_meter_visible(frame):
                meter_seen = True
                missing_count = 0
            elif meter_seen:
                missing_count += 1
                if missing_count >= 2:
                    safe_log(f"🐟上魚咯，耗時 {time.time() - fishing_start_time:.2f} 秒")
                    return True
            elif time.time() - reel_start_time > 12:
                print("⚠️ 未偵測到收線量表，停止本輪（不截圖）")
                return False
        print("⚠️ 收線超時，未確認釣起魚（不截圖）")
        return False
    finally:
        left_up()


def auto_fish_once():
    bucket_trigger = BucketFullTrigger()
    bait_trigger = BucketFullTrigger(template_name="bait_empty_template.png")

    # === 第一步：执行抛竿 ===
    fishing_sleep(0.1)
    left_down()
    print("🎣 抛竿中...")

    # 等待抛竿動畫；只根據魚桶滿／魚餌不足的明確提示暫停。
    fishing_sleep(1.0)
    blocked = None
    for _ in range(5 if bucket_trigger.full_template is not None or bait_trigger.full_template is not None else 0):
        check_fishing_paused()
        with mss.mss() as sct:
            screenshot = sct.grab({"top": window_top, "left": window_left, "width": window_width, "height": window_height})
            frame = np.array(screenshot)[:, :, :3]

        blocked = check_blocking_banners(frame, bucket_trigger, bait_trigger)
        if blocked:
            check_fishing_paused()
            break
        fishing_sleep(0.1)

    if blocked:
        left_up()
        return handle_blocked(blocked)

    # ──────────────── 继续正常钓鱼流程 ────────────────
    # 等待抛竿完全结束
    fishing_sleep(random.uniform(1.0, 1.5))

    # 站立釣魚測試：拋竿後不送方向鍵。
    left_up()


    # 抛竿動作結束後才開始計算等待上鉤的時間。
    fishing_start_time = time.time()
    bite_check_active.set()
    try:
        status = enhanced_bite_check(fishing_start_time, bucket_trigger, bait_trigger)
    finally:
        bite_check_active.clear()
    if status in ("bucket_full", "bait_empty"):
        check_fishing_paused()
        left_up()
        return handle_blocked(status)
    if not status:
        print("⏳ 等待上鉤逾時；不送方向鍵，3 秒後重新拋竿")
        fishing_sleep(3)
        return "timeout"


    # 上鉤時立刻更新提示；真正辨識仍要等收魚完成。
    if log_window:
        log_window.clear_log()
    safe_log("🫧咬鉤了！🎣 開始收線")
    if not reel(fishing_start_time):
        return "timeout"
    fishing_sleep(random.uniform(1.5, 2.5))
    left_click()

    # 靜默等待品質卡片；成功後只顯示合併後的辨識結果。

    quality_result = None
    deadline = time.time() + 8

    while time.time() < deadline:
        check_fishing_paused()
        quality_result = detect_star_quality()

        if quality_result is not None:
            quality = quality_result["dominant"][1]
            # 一句話包含品質及實際存檔位置，不再另外輸出截圖訊息。
            screenshot_path = quality_result["screenshot_path"]
            if screenshot_path:
                screenshot_info = f"截圖存於 screenshots/{os.path.basename(screenshot_path)}"
            else:
                screenshot_info = f"截圖儲存失敗：{quality_result['screenshot_error']}"
            if log_window:
                log_window.clear_log()
            safe_log(f"✅ 已成功辨識魚類品質：{quality}；{screenshot_info}；稍後重新拋竿")
            break

        fishing_sleep(0.25)

    check_fishing_paused()
    if quality_result is None:
        print("⚠️ 等待 8 秒仍未辨識到品質卡片，本次不計入統計")
        # 留一張診斷圖，區分「收線尚未結束」與「品質卡片位置改變」。
        try:
            debug_dir = os.path.join(get_application_directory(), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with mss.mss() as sct:
                frame = sct.grab({"top": window_top, "left": window_left,
                                  "width": window_width, "height": window_height})
                filename = f"quality_timeout_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                path = os.path.join(debug_dir, filename)
                cv2.imwrite(path, np.array(frame)[:, :, :3])
            print(f"診斷截圖已存至：{path}")
        except Exception as e:
            print(f"無法儲存診斷截圖：{e}")

    # 辨識成功後保留摘要 2 秒，期間 F1 仍能立即中斷，不提前抛下一竿。
    fishing_sleep(2 if quality_result is not None else 1)
    return "success"



def handle_blocked(reason):
    """魚餌用盡與魚桶滿皆須停下並等 F1；僅滿桶結算本桶統計。"""
    if reason == "bucket_full":
        return handle_bucket_full()
    global fishing_paused, paused_due_to_bucket_full, pause_reason
    check_fishing_paused()
    fishing_paused = True
    paused_due_to_bucket_full = True
    pause_reason = "魚餌不足，請補充魚餌後按 F1"
    safe_log("🪱 魚餌不足，已暫停；補充魚餌後按 F1 繼續")
    if log_window:
        log_window.log_queue.put("__status_update__")
    return "bait_empty"


def handle_bucket_full():
    """统一处理鱼桶满的逻辑"""
    global fishing_paused, paused_due_to_bucket_full, pause_reason
    check_fishing_paused()
    print("🐟 魚桶滿了，已自動暫停；需按 F1 繼續釣魚。")
    play_bucket_full_wav()


    try:
        # 满桶音效只根据「上次满桶后到这次满桶前」的收获决定，
        # 不读取本次启动以来的累计统计。
        if bucket_quality_count.get("传奇", 0) > 0:
            play_sound("ouhuang.wav")
        elif bucket_quality_count.get("史诗", 0) > 0 or bucket_quality_count.get("稀有", 0) > 0:
            play_sound("huiben.wav")
        else:
            play_sound("dawo.wav")
    except Exception as e:
        print(f"播放品质音效失败: {e}")

    reset_bucket_statistics()
    fishing_paused = True
    paused_due_to_bucket_full = True
    pause_reason = "魚桶滿了，請清空魚桶後按 F1"
    safe_log("🐟 魚桶滿了需繼續按 F1，已自動暫停")
    if log_window:
        log_window.log_queue.put("__status_update__")
    return "bucket_full"

# ====== 新增：GUI 日志窗口模块 ======
import tkinter as tk
from PIL import Image, ImageTk
import threading
import queue
import win32gui
import win32con
import win32api


def listen_for_exit():
    keyboard.wait('f2')
    try:
        save_statistics_log("按下 F2 结束")
    finally:
        refresh_probability_report()  # os._exit 不會執行主執行緒的 finally。
        print("\n[EXIT] F2 pressed. Shutting down...")
        os._exit(0)

# 启动退出监听器
threading.Thread(target=listen_for_exit, daemon=True).start()

TRANSCOLOUR = 'white'

class LogWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🦊 Vicksy")
        # 去掉标题栏和边框
        self.root.overrideredirect(True)
        self.root.geometry("430x500")
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSCOLOUR)
        self.root.wm_attributes("-transparentcolor", TRANSCOLOUR)
        # 支持窗口拖动
        self.root.bind("<ButtonPress-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)

        # === 加载带透明通道图片 ===
        try:
            img_path = resource_path("vicksy_fishing.png")
            image = Image.open(img_path).convert("RGBA")
            # 缩放
            target_width = 200
            ratio = target_width / float(image.size[0])
            target_height = int(float(image.size[1]) * ratio)
            resized_image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            # 贴到白色背景以便透明色统一
            background = Image.new("RGB", resized_image.size, (255, 255, 255))
            if resized_image.mode == 'RGBA':
                background.paste(resized_image, mask=resized_image.split()[-1])
            else:
                background.paste(resized_image)
            self.photo = ImageTk.PhotoImage(background)
            self.img_label = tk.Label(self.root, image=self.photo, bg=TRANSCOLOUR)
            self.img_label.pack(pady=5)
        except Exception as e:
            print(f"图片加载失败: {e}")
            fallback = tk.Label(
                self.root,
                text="🦊",
                bg=TRANSCOLOUR,
                fg='lime',
                font=("Arial", 24)
            )
            fallback.pack(pady=20)

        # ====== 日志样式及字体查找 ======
        LOG_BG_COLOUR = 'white'
        LOG_FONT_COLOUR = 'black'
        FONT_CHOICES = [
            'Segoe UI Mono',
            'Consolas',
            'Courier New',
            'DejaVu Sans Mono',
        ]
        def find_available_font(font_list):
            for font_name in font_list:
                try:
                    tk.font.Font(family=font_name, size=12)
                    return font_name
                except Exception:
                    continue
            return 'TkDefaultFont'
        LOG_FONT_FAMILY = find_available_font(FONT_CHOICES)
        LOG_FONT_SIZE = 12
        LOG_HEIGHT = 4  # 兩則訊息中的截圖路徑折行後仍可看見完整內容

        self.text_widget = tk.Text(
            self.root,
            bg='black',
            fg='yellow',
            font=(LOG_FONT_FAMILY, LOG_FONT_SIZE),
            height=LOG_HEIGHT,
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.text_widget.pack(fill=tk.X, padx=5, pady=(0, 5))

        # === Emoji 彩色统计状态栏 ===
        self.stats_text = tk.Text(
            self.root,
            height=2,
            bg='black',
            fg='yellow',
            font=(LOG_FONT_FAMILY, 12),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=5,
            pady=2
        )
        self.stats_text.pack(fill=tk.X, padx=5, pady=(0, 5))

       # === ✅ 新增：状态提示栏（F1/F2 + 指示灯）===
        self.status_text = tk.Text(
            self.root,
            height=2,
            bg='black',
            fg='yellow',
            font=("微软雅黑", 12),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=5,
            pady=2
        )
        self.status_text.pack(fill=tk.X, padx=5, pady=(0, 5))

        # 配置 tags
        self.status_text.tag_configure("indicator", foreground="red")
        self.status_text.tag_configure("f1", foreground="cyan")
        self.status_text.tag_configure("f2", foreground="orange")
        self.status_text.tag_configure("paused", foreground="red")
        self.status_text.tag_configure("running", foreground="green")
        self.status_text.tag_configure("bucket_paused", foreground="#FFD700")



        # 品质 -> Emoji 映射
        self.quality_symbols = {
        "标准": "●",
        "非凡": "●",
        "稀有": "●",
        "史诗": "●",
        "传奇": "●"
        }

        # 品质 -> 颜色（用于高亮数字）
        self.quality_colors = {
            "标准": "#C0C0C0",
            "非凡": "#60C65A",
            "稀有": "#70AEF1",
            "史诗": "#AB66FB",
            "传奇": "#F8C544"
        }

        # 配置 tags
        self.stats_text.tag_configure("total", foreground="yellow")
        for q in self.quality_symbols:
            self.stats_text.tag_configure(q, foreground=self.quality_colors[q])

        # 初始化显示
        self._update_stats_display()
        self._update_status_display()
        # 关闭按钮
        close_btn = tk.Button(
            self.root,
            text="×",
            command=self.close,
            bg=TRANSCOLOUR,
            fg='red',
            font=("Arial", 20, "bold"),
            bd=0,
            highlightthickness=0,
            width=2
        )
        close_btn.place(relx=1.0, rely=0.0, anchor='ne')

        # === 日志队列等 ===
        self.log_queue = queue.Queue()
        self.running = True
        self.update_logs()

    def log(self, message):
        self.log_queue.put(str(message))

    def clear_log(self):
        """由工作线程请求清空画面日志，实际操作留给 GUI 线程执行。"""
        self.log_queue.put(None)

    def update_logs(self):
        MAX_LINES = 2  # 最多保留 4 行日志
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.text_widget.config(state=tk.NORMAL)

            if msg is None:
                self.text_widget.delete(1.0, tk.END)
                self.text_widget.config(state=tk.DISABLED)
                continue
            if msg == "__status_update__":
                self.text_widget.config(state=tk.DISABLED)
                self._update_status_display()
                continue

            # 插入新消息
            self.text_widget.insert(tk.END, msg + "\n")

            # 获取总行数
            line_count = int(self.text_widget.index('end-1c').split('.')[0])

            # 如果超过 MAX_LINES，删除最上面的行
            while line_count > MAX_LINES:
                self.text_widget.delete(1.0, "2.0")  # 删除第一行（包括换行符）
                line_count -= 1

            self.text_widget.config(state=tk.DISABLED)

        if self.running:
            self.root.after(100, self.update_logs)

    def run(self):
        self.root.mainloop()

    def stop(self):
        self.running = False

    def close(self):
        self.running = False
        self.root.destroy()  # main 的 finally 統一保存日誌並更新報表。

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _update_stats_display(self):
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)

        self._insert_statistics_row("本桶", bucket_quality_count)
        self.stats_text.insert(tk.END, "\n")
        self._insert_statistics_row("累計", star_quality_count)

        self.stats_text.config(state=tk.DISABLED)

    def _insert_statistics_row(self, label, counts):
        # 固定欄寬讓五種魚平均對齊，字體放大後兩列仍能完整顯示。
        self.stats_text.insert(tk.END, f"{label} 🎣{sum(counts.values()):>3} | ", "total")
        for quality in QUALITY_ORDER:
            self.stats_text.insert(tk.END, self.quality_symbols[quality], quality)
            self.stats_text.insert(tk.END, f"{counts[quality]:>3}  ", quality)

    def _update_status_display(self):
        global fishing_paused

        if paused_due_to_bucket_full:
            indicator_symbol = "🟡"
            indicator_tag = "bucket_paused"
            status_message = " " + pause_reason
        else:
            indicator_symbol = "🔴" if fishing_paused else "🟢"
            indicator_tag = "paused" if fishing_paused else "running"
            status_message = " F1: 釣魚 | F2: 結束"

        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)

        # 插入带颜色的指示灯 + 文字
        self.status_text.insert(tk.END, indicator_symbol, indicator_tag)
        self.status_text.insert(tk.END, status_message + f" | F3 防踢: {'開' if anti_kick_enabled else '關'}")

        self.status_text.config(state=tk.DISABLED)



# ====== 8. 主循环入口 ======
# ====== 全局钓鱼控制开关 ======
log_window = None
fishing_paused = True
pause_reason = ""
fishing_generation = 0
fishing_context = threading.local()
anti_kick_enabled = False
anti_kick_wakeup = threading.Event()
anti_kick_toggle_lock = threading.Lock()
anti_kick_last_toggle = 0.0
ANTI_KICK_INTERVAL = 15
ANTI_KICK_HOLD = 0.12
session_extension_active = threading.Event()
session_extension_rebaseline = threading.Event()
bite_check_active = threading.Event()
session_extension_lock = threading.Lock()
session_extension_last_click = 0.0


def capture_game_frame():
    with mss.mss() as sct:
        return np.array(sct.grab({
            "top": window_top, "left": window_left,
            "width": window_width, "height": window_height
        }))[:, :, :3]


def handle_session_extension(frame=None):
    """只在遊戲前景按延長遊戲的「是」；F1/F3 共用且避免重複點擊。"""
    global fishing_generation, session_extension_last_click
    if win32gui.GetForegroundWindow() != hwnd:
        return False
    template = resource_path("session_extend_template.png")
    if session_extension_active.is_set():
        return True
    if frame is None:
        frame = capture_game_frame()
    if not extension_dialog_visible(frame, template):
        return False
    with session_extension_lock:
        if session_extension_active.is_set():
            return True
        if time.monotonic() - session_extension_last_click < 2.0:
            return True  # 點擊後視窗消失前不再點第二次。
        if win32gui.GetForegroundWindow() != hwnd or not extension_dialog_visible(capture_game_frame(), template):
            return False  # 點擊前重新確認，避免點到其他畫面。
        session_extension_active.set()
        try:
            if not fishing_paused:
                if bite_check_active.is_set():
                    session_extension_rebaseline.set()  # 保留釣線，關窗後繼續辨識上魚。
                else:
                    fishing_generation += 1  # 其他階段中斷本輪，避免操作舊畫面。
            left_up()  # F1 抛竿／收線時可能仍按住滑鼠左鍵。
            if win32gui.GetForegroundWindow() != hwnd:
                return True
            session_extension_last_click = time.monotonic()
            pyautogui.click(window_left + 1040, window_top + 589)
            safe_log("⏱ 已按『是』，延長本局遊戲 60 分鐘")
            # 等畫面關閉後才允許新一輪抛竿或 F3 的 A 操作。
            for _ in range(25):
                time.sleep(0.12)
                if (win32gui.GetForegroundWindow() != hwnd or
                        not extension_dialog_visible(capture_game_frame(), template)):
                    break
            return True
        finally:
            session_extension_active.clear()


def session_extension_loop():
    """F1 釣魚中或 F3 防踢開啟時持續監看延長遊戲提示。"""
    while True:
        try:
            if (not fishing_paused or anti_kick_enabled) and win32gui.GetForegroundWindow() == hwnd:
                handle_session_extension()
        except Exception as e:
            safe_log(f"⚠️ 延長遊戲提示辨識／點擊失敗：{e}")
        time.sleep(0.5)


def anti_kick_ready():
    return (anti_kick_enabled and fishing_paused and
            not session_extension_active.is_set() and
            win32gui.GetForegroundWindow() == hwnd)


def anti_kick_move(scan_code):
    """短按按鍵一次；F1 切換、F3 關閉或失焦時立即放開。"""
    if not anti_kick_ready():
        return False
    send_game_key(scan_code)
    try:
        end = time.monotonic() + ANTI_KICK_HOLD
        while time.monotonic() < end:
            if not anti_kick_ready():
                return False
            time.sleep(max(0, min(0.05, end - time.monotonic())))
        return True
    finally:
        send_game_key(scan_code, release=True)


def anti_kick_loop():
    """F3 開啟且 F1 暫停、遊戲在前景時，每 15 秒短按 A 一次。"""
    next_press = time.monotonic() + 1
    last_focus_warning = 0.0
    while True:
        if anti_kick_wakeup.wait(0.5):
            anti_kick_wakeup.clear()
            next_press = time.monotonic() + 1  # F3 剛啟用先移動，不等 15 秒。
        if not anti_kick_enabled or time.monotonic() < next_press:
            continue
        try:
            if not fishing_paused or session_extension_active.is_set():
                continue
            if win32gui.GetForegroundWindow() != hwnd:
                if time.monotonic() - last_focus_warning >= 30:
                    safe_log("🛡 F3 已開但遊戲不在前景；不會送出防踢按鍵")
                    last_focus_warning = time.monotonic()
                continue
            if handle_session_extension():
                next_press = time.monotonic() + ANTI_KICK_INTERVAL
                continue
            if anti_kick_move(0x1E):  # A 掃描碼
                safe_log("🛡 F3 已送出 A 短按；若仍出現 AFK 警告，遊戲可能不接受模擬輸入")
            next_press = time.monotonic() + ANTI_KICK_INTERVAL
        except Exception as e:
            next_press = time.monotonic() + 3
            safe_log(f"⚠️ F3 防踢按鍵失敗：{e}")



class FishingInterrupted(BaseException):
    """F1 暫停時中斷本輪，避免被影像處理的通用 Exception 攔截。"""


def check_fishing_paused():
    if (fishing_paused or
            getattr(fishing_context, "generation", fishing_generation) != fishing_generation):
        raise FishingInterrupted()


def fishing_sleep(seconds):
    """讓抛竿、收線及等品質畫面的等待能在約 50ms 內響應 F1。"""
    end = time.monotonic() + seconds
    while True:
        check_fishing_paused()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.05, remaining))

def update_stats(self, total=0, standard=0, extraordinary=0, rare=0, epic=0, legendary=0):
    """更新钓鱼统计显示"""
    text = f"共钓 {total} 条：{standard} 标准，{extraordinary} 非凡，{rare} 稀有，{epic} 史诗，{legendary} 传奇"
    self.stats_label.config(text=text)

def safe_log(msg):
    """安全日志函数，避免 GUI 未初始化时报错"""
    if 'log_window' in globals() and log_window:
        log_window.log(msg)
    else:
        print(msg)


class PrintRedirector:
    def __init__(self):
        self.line_buffer = ""

    def write(self, message):
        if message.strip() == "":
            return
        self.line_buffer += message
        # 处理换行（print 默认带 \n）
        while "\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\n", 1)
            if line.strip():
                safe_log(line)

    def flush(self):
        # 如果有残余内容（无换行结尾），也输出
        if self.line_buffer.strip():
            safe_log(self.line_buffer.strip())
            self.line_buffer = ""
# ====== 主程序入口 ======
if __name__ == "__main__":
    # === 1. 初始化全局状态（必须在 LogWindow 创建前定义！）===
    fishing_paused = True  # 默认暂停
    loaded_daily_total = load_daily_statistics()

    # === 2. 创建日志窗口 ===
    log_window = LogWindow()

    # 重定向 print
    sys.stdout = PrintRedirector()
    sys.stderr = PrintRedirector()

    safe_log("🦊 狐狐附身...")
    if loaded_daily_total is not None:
        safe_log(f"📖 已載入今日累計：{loaded_daily_total} 條")
    safe_log("✅ F1 釣魚開關、F2 結束、F3 防踢開關")
    safe_log("请将窗口切回至猛兽派对...")
    safe_log(f"游戏窗口分辨率: {window_width}x{window_height}")
    safe_log("面朝小河，拿起鱼竿，准备好钓饵     按 F1 请🦊狐狐附身钓鱼")

    time.sleep(1)

    # ✅ 注册 F1 热键
    def toggle_fishing(e=None):
        global fishing_paused, paused_due_to_bucket_full, fishing_generation, pause_reason
        if fishing_paused and paused_due_to_bucket_full:
            paused_due_to_bucket_full = False
            pause_reason = ""
            fishing_paused = False
            status = "▶ 繼續釣魚..."
        else:
            fishing_paused = not fishing_paused
            status = "⏸ 已暂停" if fishing_paused else "▶ 钓鱼中..."
        fishing_generation += 1
        if fishing_paused:
            left_up()  # 立即放開抛竿／收線時按住的滑鼠鍵
        safe_log(status)
        if log_window:
            log_window.log_queue.put("__status_update__")

    keyboard.add_hotkey('F1', toggle_fishing)

    def toggle_anti_kick(e=None):
        global anti_kick_enabled, anti_kick_last_toggle
        with anti_kick_toggle_lock:
            now = time.monotonic()
            if now - anti_kick_last_toggle < 1.0:
                return  # 忽略長按 F3 時系統產生的重複按鍵事件。
            anti_kick_last_toggle = now
            anti_kick_enabled = not anti_kick_enabled
            anti_kick_wakeup.set()  # 啟用後約 1 秒開始第一次移動。
            safe_log("🛡 F3 防踢模式已開啟（僅釣魚暫停且遊戲在前景，每 15 秒短按 A 一次（約 0.12 秒））" if anti_kick_enabled
                     else "🛡 F3 防踢模式已關閉")
            if log_window:
                log_window.log_queue.put("__status_update__")

    keyboard.add_hotkey('F3', toggle_anti_kick)
    threading.Thread(target=anti_kick_loop, daemon=True).start()
    threading.Thread(target=session_extension_loop, daemon=True).start()

    # F2 退出已在 listen_for_exit 中处理

    # === 3. 启动钓鱼线程 ===
    def run_fishing_loop():
        global fishing_paused
        while True:
            if fishing_paused or session_extension_active.is_set():
                time.sleep(0.1)
                continue
            fishing_context.generation = fishing_generation
            try:
                result = auto_fish_once()
                if result not in ("bucket_full", "bait_empty"):
                    fishing_sleep(0.5)
            except FishingInterrupted:
                left_up()
                if log_window and fishing_paused:
                    log_window.clear_log()
                    safe_log("⏸ 本輪已停止；按 F1 將重新開始抛竿")
            except Exception:
                left_up()
                safe_log(f"❌ 运行出错:\n{traceback.format_exc()}")
                fishing_paused = True
                if log_window:
                    log_window.log_queue.put("__status_update__")

    fishing_thread = threading.Thread(target=run_fishing_loop, daemon=True)
    fishing_thread.start()

    # === 4. 启动 GUI ===
    try:
        log_window.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            save_statistics_log("程式結束")
        finally:
            refresh_probability_report()
            log_window.stop()
