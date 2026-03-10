"""
/export_bugs — superadmin command.
Generates an HTML report of feedback entries and sends it as a document.
"""
import io
import logging
from html import escape
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from app.config import settings as cfg
from app.db import repositories as repo

router = Router()
logger = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "bug": ("🐛", "Баг"),
    "idea": ("💡", "Идея"),
    "complaint": ("😤", "Жалоба"),
}

# ── HTML template pieces ────────────────────────────────────────────

_CSS = """\
body{font-family:system-ui,sans-serif;margin:2em auto;max-width:900px;color:#222;background:#fafafa}
h1{text-align:center;margin-bottom:.2em}
.meta{text-align:center;color:#888;font-size:.85em;margin-bottom:2em}
.card{background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:1em 1.2em;margin-bottom:1em}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:.4em}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.85em;font-weight:600}
.bug{background:#ffe0e0;color:#b00}
.idea{background:#e0f0ff;color:#06a}
.complaint{background:#fff3e0;color:#c50}
.open{border-left:4px solid #f44336}
.done{border-left:4px solid #4caf50;opacity:.7}
.user{font-weight:600;color:#555}
.date{color:#999;font-size:.82em}
.text{margin-top:.4em;white-space:pre-wrap;word-break:break-word}
.empty{text-align:center;color:#aaa;padding:3em}
.stats{display:flex;gap:1.5em;justify-content:center;margin-bottom:1.5em;flex-wrap:wrap}
.stat{text-align:center}
.stat-num{font-size:1.6em;font-weight:700}
.stat-label{font-size:.8em;color:#888}
"""


def _format_dt(val) -> str:
    """Convert various datetime representations to readable string."""
    if val is None:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y %H:%M")
    try:
        dt = datetime.fromisoformat(str(val))
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return str(val)


def generate_html(items: list[dict]) -> str:
    """Build a self-contained HTML report from feedback rows."""
    open_count = sum(1 for i in items if i["status"] == "open")
    done_count = sum(1 for i in items if i["status"] == "done")

    cat_counts = {}
    for i in items:
        cat_counts[i["category"]] = cat_counts.get(i["category"], 0) + 1

    cards = []
    for item in items:
        cat = item["category"]
        icon, label = CATEGORY_LABELS.get(cat, ("📣", cat))
        status_cls = item["status"]
        who = f"@{item['username']}" if item.get("username") else f"id{item['user_id']}"
        text = escape(item["text"] or "[медиа без текста]")
        dt = _format_dt(item.get("created_at"))
        status_label = "открыто" if status_cls == "open" else "закрыто"

        cards.append(
            f'<div class="card {status_cls}">'
            f'<div class="card-header">'
            f'<span><span class="badge {cat}">{icon} {label}</span> '
            f'<span class="user">{escape(who)}</span> '
            f'<span style="color:#aaa">#{item["id"]}</span></span>'
            f'<span class="date">{dt} · {status_label}</span>'
            f'</div>'
            f'<div class="text">{text}</div>'
            f'</div>'
        )

    stats_html = (
        '<div class="stats">'
        f'<div class="stat"><div class="stat-num">{len(items)}</div><div class="stat-label">всего</div></div>'
        f'<div class="stat"><div class="stat-num">{open_count}</div><div class="stat-label">открытых</div></div>'
        f'<div class="stat"><div class="stat-num">{done_count}</div><div class="stat-label">закрытых</div></div>'
    )
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        icon, label = CATEGORY_LABELS.get(cat, ("📣", cat))
        stats_html += f'<div class="stat"><div class="stat-num">{count}</div><div class="stat-label">{icon} {label}</div></div>'
    stats_html += "</div>"

    body = "\n".join(cards) if cards else '<div class="empty">Обращений не найдено</div>'

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    return (
        "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Feedback export</title><style>{_CSS}</style></head><body>"
        f"<h1>📋 Feedback</h1>"
        f'<div class="meta">Экспорт от {now_str}</div>'
        f"{stats_html}"
        f"{body}"
        "</body></html>"
    )


# ── Handler ─────────────────────────────────────────────────────────

@router.message(Command("export_bugs"))
async def cmd_export_bugs(message: Message) -> None:
    if message.from_user.id != cfg.SUPERADMIN_ID:
        return

    args = (message.text or "").split()[1:]
    status_filter = None
    category_filter = None

    for arg in args:
        low = arg.lower()
        if low in ("open", "done"):
            status_filter = low
        elif low in CATEGORY_LABELS:
            category_filter = low

    try:
        items = await repo.get_all_feedback(
            status=status_filter,
            category=category_filter,
        )
    except Exception:
        logger.exception("Failed to fetch feedback for export")
        await message.answer("❌ Ошибка при загрузке фидбека из БД.")
        return

    html = generate_html(items)
    buf = io.BytesIO(html.encode("utf-8"))
    filename = "feedback_export.html"

    doc = BufferedInputFile(buf.getvalue(), filename=filename)
    count_open = sum(1 for i in items if i["status"] == "open")
    caption = f"📋 Экспорт фидбека: {len(items)} записей ({count_open} открытых)"

    await message.answer_document(doc, caption=caption)
