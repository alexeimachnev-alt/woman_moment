import os
import json
import logging
import atexit
from datetime import datetime
import pytz
import requests
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from parser_5ka import (
    update_catalog_from_5ka,
    log_and_save_catalog,
    EXTENDED_5KA_CATALOG,
    CATALOG_FILE,
    MOSCOW_TZ
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FlaskApp")

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
RECIPIENTS_FILE = "recipients.json"


def load_active_catalog():
    """Читает каталог из файла catalog_5ka.json или инициализирует его полным набором."""
    if not os.path.exists(CATALOG_FILE):
        res = log_and_save_catalog(EXTENDED_5KA_CATALOG, "Стартовая инициализация")
        return EXTENDED_5KA_CATALOG, res.get("updated_at", "")

    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "categories" in data:
                return data["categories"], data.get("updated_at", "Неизвестно")
            elif isinstance(data, list):
                return data, "Неизвестно"
    except Exception as e:
        logger.error(f"Ошибка чтения {CATALOG_FILE}: {e}")

    return EXTENDED_5KA_CATALOG, "Резервная копия"


# =====================================================================
# ПЛАНИРОВЩИК ЗАДАЧ APSCHEDULER (ЕЖЕДНЕВНО В 01:00 НОЧИ ПО МСК)
# =====================================================================
def scheduled_daily_catalog_sync():
    logger.info("⏰ [APScheduler] Запуск планового ночного парсинга каталога 5ka.ru (01:00 MSK)...")
    update_catalog_from_5ka()


scheduler = BackgroundScheduler(timezone=MOSCOW_TZ)
scheduler.add_job(
    func=scheduled_daily_catalog_sync,
    trigger=CronTrigger(hour=1, minute=0, timezone=MOSCOW_TZ),
    id="daily_5ka_catalog_sync",
    name="Ежедневный полный парсинг каталога 5ka.ru в 01:00 MSK",
    replace_existing=True
)
scheduler.start()
logger.info("✅ Планировщик APScheduler запущен: полное обновление каталога каждый день в 01:00 (Europe/Moscow).")
atexit.register(lambda: scheduler.shutdown(wait=False))


# =====================================================================
# РАБОТА С АДРЕСНОЙ КНИГОЙ ПОЛУЧАТЕЛЕЙ
# =====================================================================
def load_recipients():
    if not os.path.exists(RECIPIENTS_FILE):
        default_data = [{"id": "551209811", "name": "Основной получатель / Склад"}]
        save_recipients(default_data)
        return default_data
    try:
        with open(RECIPIENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_recipients(data):
    try:
        with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {RECIPIENTS_FILE}: {e}")


# =====================================================================
# МАРШРУТЫ FLASK
# =====================================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/catalog", methods=["GET"])
def get_catalog():
    categories, updated_at = load_active_catalog()
    return jsonify({
        "updated_at": updated_at,
        "categories": categories
    })


@app.route("/api/sync_catalog", methods=["POST"])
def manual_sync_catalog():
    """Запускает полный парсинг на сервере и возвращает детальную статистику."""
    logger.info("🔄 Запрошено принудительное полное обновление каталога 5ka.ru...")
    res = update_catalog_from_5ka()
    categories, updated_at = load_active_catalog()
    return jsonify({
        "sync_result": res,
        "updated_at": updated_at,
        "categories_count": len(categories),
        "items_count": sum(len(c.get("items", [])) for c in categories)
    })


@app.route("/api/upload_client_catalog", methods=["POST"])
def upload_client_catalog():
    body = request.get_json(silent=True) or {}
    categories = body.get("categories", [])
    if not isinstance(categories, list) or len(categories) == 0:
        return jsonify({"ok": False, "error": "Передан пустой каталог"}), 400

    res = log_and_save_catalog(categories, "https://5ka.ru/catalog/ (Client-Side Direct XHR)")
    return jsonify(res)


@app.route("/api/recipients", methods=["GET", "POST", "DELETE"])
def handle_recipients():
    recipients = load_recipients()

    if request.method == "GET":
        return jsonify(recipients)

    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        tg_id = str(body.get("id", "")).strip()
        name = str(body.get("name", "")).strip()

        if not tg_id or not name:
            return jsonify({"ok": False, "error": "Укажите имя и Telegram ID получателя."}), 400

        if not tg_id.lstrip("-").isdigit():
            return jsonify({"ok": False, "error": "Telegram ID должен состоять только из цифр."}), 400

        existing = next((r for r in recipients if str(r["id"]) == tg_id), None)
        if existing:
            existing["name"] = name
        else:
            recipients.append({"id": tg_id, "name": name})

        save_recipients(recipients)
        return jsonify({"ok": True, "recipients": recipients})

    if request.method == "DELETE":
        tg_id = request.args.get("id", "").strip()
        recipients = [r for r in recipients if str(r["id"]) != tg_id]
        save_recipients(recipients)
        return jsonify({"ok": True, "recipients": recipients})


@app.route("/api/send_order", methods=["POST"])
def send_order():
    data = request.get_json(silent=True) or {}
    recipient_id = str(data.get("recipient_id", "")).strip()
    recipient_name = str(data.get("recipient_name", "Получатель")).strip()
    sender = data.get("sender", {})
    items = data.get("items", [])
    comment = str(data.get("comment", "")).strip()

    if not recipient_id:
        return jsonify({"ok": False, "error": "Не выбран получатель заказа."}), 400
    if not items:
        return jsonify({"ok": False, "error": "Список заказа пуст."}), 400
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return jsonify({"ok": False, "error": "На сервере не настроен BOT_TOKEN в переменных окружения Render."}), 500

    sender_id = sender.get("id", "Неизвестно")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")
    username = sender.get("username", "")

    full_name = f"{first_name} {last_name}".strip() or "Пользователь"
    user_mention = f" (@{username})" if username else ""

    lines = [
        "🛒 <b>НОВЫЙ СПИСОК ЗАКАЗА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>Отправитель:</b> {full_name}{user_mention}",
        f"🆔 <b>Telegram ID отправителя:</b> <code>{sender_id}</code>",
        f"📌 <b>Получатель:</b> {recipient_name} (<code>{recipient_id}</code>)",
        "━━━━━━━━━━━━━━━━━━━━",
        "📋 <b>Позиции заказа:</b>\n"
    ]

    total_sum = 0.0
    total_qty = 0

    for idx, item in enumerate(items, start=1):
        name = item.get("name", "Товар")
        qty = int(item.get("qty", 1))
        price = float(item.get("price", 0))
        unit = item.get("unit", "шт")
        icon = item.get("icon", "▫️")
        line_sum = qty * price
        total_sum += line_sum
        total_qty += qty

        lines.append(
            f"{idx}. {icon} <b>{name}</b>\n"
            f"    └ {qty} {unit} × {price:.2f} ₽ = <b>{line_sum:.2f} ₽</b>"
        )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📦 <b>Всего позиций:</b> {len(items)} ({total_qty} ед.)")
    lines.append(f"💰 <b>ИТОГО: {total_sum:.2f} ₽</b>")

    if comment:
        lines.append(f"\n💬 <b>Комментарий:</b>\n<i>{comment}</i>")

    message_text = "\n".join(lines)

    tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": recipient_id,
        "text": message_text,
        "parse_mode": "HTML"
    }

    try:
        resp = requests.post(tg_url, json=payload, timeout=10)
        res_data = resp.json()

        if resp.status_code == 200 and res_data.get("ok"):
            return jsonify({"ok": True})
        else:
            desc = res_data.get("description", "Неизвестная ошибка Telegram API")
            if "chat not found" in desc.lower() or "bot was blocked" in desc.lower():
                desc = (
                    f"Не удалось доставить сообщение получателю (ID: {recipient_id}). "
                    "Убедитесь, что получатель запустил этого бота кнопкой /start."
                )
            return jsonify({"ok": False, "error": desc}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка соединения с Telegram API: {str(e)}"}), 500


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if chat_id and text.startswith("/start"):
        app_url = request.url_root.replace("http://", "https://")
        welcome_text = (
            f"👋 <b>Добро пожаловать в Каталог Заказов!</b>\n\n"
            f"🆔 Ваш Telegram ID: <code>{chat_id}</code>\n"
            f"<i>(Передайте этот ID тому, кто будет отправлять вам списки заказов, "
            f"или добавьте его в адресную книгу приложения).</i>\n\n"
            f"🔄 Полный каталог автоматически синхронизируется каждую ночь в 01:00 МСК.\n"
            f"👇 Нажмите кнопку ниже, чтобы открыть каталог и собрать заказ:"
        )
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🛒 Открыть каталог товаров", "web_app": {"url": app_url}}
            ]]
        }
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            },
            timeout=5
        )
    return jsonify({"ok": True})


if __name__ == "__main__":
    load_active_catalog()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
