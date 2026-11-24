# 猛獸派對釣魚輔助（個人改作）

這是 [IYIcode/hu-hu-fishing-demo](https://github.com/IYIcode/hu-hu-fishing-demo) 的 [kenny9487 fork](https://github.com/kenny9487/hu-hu-fishing-demo)，保留既有 `main.py` 的客製功能，**不以原版 `yt.py` 覆蓋**。fork 仍留有上游的 `yt.py`、`auto-exe.bat` 供參考；請使用本版的 `main.py`、`auto-exe-fixed.bat`，勿混用上游 1024×768 的操作說明。本版透過擷取遊戲畫面、辨識提示和模擬滑鼠操作協助釣魚。僅供個人學習與研究，使用前請確認符合遊戲規則；自動化操作不保證不會被判定為 AFK。

## 功能與操作

- **F1**：開始／暫停釣魚。等待咬鉤、收線、辨識五種品質；目前 F1 流程**不發送 A、D、W、S 方向鍵**，但仍會按放滑鼠左鍵。站立時角色是否偏移尚未經遊戲內驗證。
- **F2**：儲存當日統計、更新報表並結束程式。
- **F3**：開啟／關閉防踢。僅在**釣魚暫停且遊戲視窗在前景**時，啟用約 1 秒後開始、之後每 15 秒以掃描碼短按 A 約 0.12 秒；遊戲不一定接受模擬輸入。
- **延長本局**：F1 運作或 F3 開啟期間，遊戲在前景時辨識「是否延長 60 分鐘」提示並按「是」；F1 等待上魚時會在提示關閉後重新建立辨識基準。
- **首次捕獲**：辨識品質且成功存下截圖後，若畫面顯示「首次捕獲」，原圖保留在 `screenshots/`，另複製到 `screenshots/firstone/`，並在 `log/firstone.log` 追加今日與所有首次捕獲品質統計。已存的截圖可用 `python backfill_first_catch.py` 補分類。
- **魚桶／魚餌提示**：辨識滿桶或缺餌後暫停，處理完按 F1 繼續；滿桶時可播放音效。
- **品質比例報表**：正常關閉程式時產生 `log/魚類機率統計.html`；每個統計日取最後一筆有效累計。這是**實際釣獲比例**，不是遊戲官方掉落率。

## 執行環境

- Windows 10／11；先啟動《猛獸派對》，將**遊戲客戶區**設為 **1920 × 1080**（不含視窗邊框），拿起魚竿並面向釣魚位置。程式啟動時會尋找並嘗試切換到遊戲視窗；未找到或解析度不同會退出。
- Python 與 `requirements.txt` 中的套件；Windows 的 `pywin32`、螢幕擷取和全域熱鍵需要能在目前使用者權限下運作。程式不會自行安裝遊戲。

在本資料夾執行（PowerShell）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

也可使用已打包的 `dist/fishing-helper.exe`，無需另裝 Python。若移動 EXE，舊的 `log/` 和 `screenshots/` 要自行複製到 **EXE 同一層**才能延續紀錄；程式使用 EXE 旁的資料夾，而非原始碼旁的資料夾。

## 打包與測試

雙擊 `auto-exe-fixed.bat`，它會建立 `fishing_venv/`、安裝打包依賴，再以 PyInstaller `--onefile` 產生 `dist/fishing-helper.exe`。影像樣板、圖示與音效檔於打包時納入 EXE。打包前確認樣板與資源檔齊全；執行中的舊版 EXE 不會因原始碼改動而自動更新。

離線測試（不會操作遊戲）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

離線測試僅涵蓋部分辨識與輸入邏輯，不能代替遊戲內測試。

## 檔案與資料

| 路徑 | 用途 |
| --- | --- |
| `main.py` | 本版釣魚流程、熱鍵、日誌與介面 |
| `yt.py`、`auto-exe.bat` | fork 保留的上游原始版本，並非本版入口或建置腳本 |
| `first_catch.py`、`first_catch_template*.png` | 首次捕獲辨識、複製及紀錄 |
| `session_extend.py`、`session_extend_template.png` | 延長本局提示辨識 |
| `bucket_full_template.png`、`bait_empty_template.png`、`star_template.png` | 畫面辨識樣板 |
| `log/fish_probability_report.py` | 產生品質比例報表；亦可直接執行以手動更新 |
| `auto-exe-fixed.bat`、`resource/` | Windows 打包腳本與圖示 |
| `screenshots/`、`debug/`、`log/*.log`、`log/*.html` | 本機執行資料；由 `.gitignore` 排除，不應上傳個人截圖與紀錄 |

當日統計以**台灣時間中午 12:00** 切換；`log/YYYYMMDD.log` 是累計快照，同一天多次啟動不應將快照相加。`firstone.log` 記錄首次捕獲，與每日品質比例報表是不同的資料。

## 來源及授權注意

參考專案：[IYIcode/hu-hu-fishing-demo](https://github.com/IYIcode/hu-hu-fishing-demo)（原入口為 `yt.py`）；感謝原作者。本改作保留現有本機功能，不宣稱是上游官方版本。**上游 README 提到 MIT，但查閱時上游倉庫沒有 `LICENSE` 檔案；本專案目前也沒有可核驗的授權檔。** 公開分發原作者程式碼或二進位檔前，請先確認授權及署名要求；不要僅憑 README 的連結自行宣稱已取得 MIT 授權。
