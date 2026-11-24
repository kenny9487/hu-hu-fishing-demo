"""把每日 log 最後一筆今日累計，整理成可在瀏覽器查看的魚類比例表。"""
from datetime import datetime
from html import escape
from pathlib import Path
import re

QUALITY_ORDER = ("标准", "非凡", "稀有", "史诗", "传奇")
COLORS = ("#9ca3af", "#50be76", "#57a8e9", "#a97af0", "#f6bd51")
REPORT_NAME = "魚類機率統計.html"
DATE_FILE = re.compile(r"\d{8}\.log\Z")


def daily_snapshots(log_dir):
    """只取每個統計日最後一筆完整的累計；不把同日多次存檔相加。"""
    snapshots = []
    for path in sorted(Path(log_dir).glob("*.log")):
        if not DATE_FILE.fullmatch(path.name):
            continue
        latest = None
        timestamp = ""
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("[") and "]" in line:
                timestamp = line[1:line.index("]")]
            if "今日累計統計" not in line and "本次启动累计" not in line:
                continue
            fields = {name: int(value) for name, value in
                      re.findall(r"(标准|非凡|稀有|史诗|传奇)\s*=\s*(\d+)", line)}
            if set(fields) == set(QUALITY_ORDER):
                latest = (fields, timestamp)
        if latest is not None:
            snapshots.append((path.stem, *latest))
    return snapshots


def percentage(count, total):
    return f"{100 * count / total:.1f}%" if total else "—"


def render_report(snapshots):
    totals = {q: sum(counts[q] for _, counts, _ in snapshots) for q in QUALITY_ORDER}
    grand_total = sum(totals.values())

    def row(label, counts, saved_at="", css_class=""):
        total = sum(counts.values())
        segments = "".join(
            f'<span style="width:{100 * counts[q] / total:.5f}%;background:{color}" '
            f'title="{q}：{counts[q]} 條（{percentage(counts[q], total)}）"></span>'
            for q, color in zip(QUALITY_ORDER, COLORS) if total and counts[q]
        )
        cells = "".join(
            f'<td><strong>{percentage(counts[q], total)}</strong><small>{counts[q]} 條</small></td>'
            for q in QUALITY_ORDER
        )
        return (f'<tr class="{css_class}"><th scope="row">{escape(label)}'
                f'<small>{escape(saved_at)}</small></th><td>{total}</td>{cells}'
                f'<td><div class="stack" aria-label="品質分布">{segments}</div></td></tr>')

    rows = "\n".join(
        row(f"{date[:4]}-{date[4:6]}-{date[6:]}", counts, saved_at)
        for date, counts, saved_at in snapshots
    )
    if not snapshots:
        rows = '<tr><td colspan="8">尚無有效的今日累計紀錄。</td></tr>'
    legend = "".join(
        f'<span><i style="background:{color}"></i>{q}</span>'
        for q, color in zip(QUALITY_ORDER, COLORS)
    )
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>魚類品質機率統計</title>
<style>
:root{{color-scheme:dark;font-family:"Microsoft JhengHei","Noto Sans TC",sans-serif}}
body{{margin:0;background:#101828;color:#e8edf8;padding:clamp(16px,4vw,50px)}}
main{{max-width:1350px;margin:auto}}h1{{margin-bottom:8px}}p{{color:#aabbd3;line-height:1.7}}
.summary{{padding:18px 22px;margin:22px 0;background:#1c2a40;border:1px solid #354863;border-radius:14px}}
.summary strong{{color:#ffd577;font-size:1.3em}}.legend{{display:flex;flex-wrap:wrap;gap:16px;margin:14px 0}}
.legend span{{display:inline-flex;align-items:center;gap:6px}}i{{width:12px;height:12px;border-radius:3px;display:inline-block}}
.scroll{{overflow-x:auto;border:1px solid #354863;border-radius:14px}}
table{{width:100%;min-width:900px;border-collapse:collapse;text-align:right}}
thead{{background:#22334c}}th,td{{padding:14px 12px;border-bottom:1px solid #34455e;white-space:nowrap}}
tr:last-child th,tr:last-child td{{border-bottom:0}}th:first-child,td:first-child{{text-align:left}}
tbody tr:hover{{background:#263751}}small{{display:block;color:#9aacc5;margin-top:4px}}
.total{{background:#243750;font-weight:bold}}.stack{{display:flex;width:180px;height:16px;border-radius:8px;overflow:hidden;background:#40506a}}
footer{{margin-top:20px;font-size:.9em;color:#9aacc5}}
</style></head><body><main>
<h1>🎣 魚類品質機率統計</h1>
<p>每個統計日只採用該日誌<strong>最後一筆有效「今日累計統計」</strong>；機率為各品質條數 ÷ 該日總條數，屬實際釣獲比例，並非遊戲官方掉落率。</p>
<div class="summary">涵蓋 <strong>{len(snapshots)}</strong> 個統計日，共 <strong>{grand_total}</strong> 條魚。
<div class="legend">{legend}</div></div>
<div class="scroll"><table><thead><tr><th scope="col">統計日／最後存檔時間</th><th scope="col">總條數</th>
{''.join(f'<th scope="col">{q}</th>' for q in QUALITY_ORDER)}<th scope="col">比例長條</th></tr></thead><tbody>
{rows}
{row('所有日期合計', totals, css_class='total') if snapshots else ''}
</tbody></table></div>
<footer>統計日按程式既有規則於台灣時間中午 12:00 切換；同一天多次存檔不會重複計數。報表更新：{created}。零條魚的日期顯示「—」。</footer>
</main></body></html>'''


def generate_report(log_dir):
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    target = log_dir / REPORT_NAME
    target.write_text(render_report(daily_snapshots(log_dir)), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(f"機率統計表已更新：{generate_report(Path(__file__).resolve().parent)}")
