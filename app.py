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

from parser_5ka import update_catalog_from_5ka, CATALOG_FILE, MOSCOW_TZ

# Настройка логирования для вывода в консоль Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FlaskApp")

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
RECIPIENTS_FILE = "recipients.json"

# Состояние последнего обновления каталога для мониторинга
LAST_SYNC_META = {
    "last_run": "Еще не запускался",
    "status": "initialized",
    "items_count": 0,
    "categories_count": 0
}

# =====================================================================
# БАЗОВЫЙ КАТАЛОГ ТОВАРОВ (Используется до первого парсинга или как резерв)
# =====================================================================
DEFAULT_CATALOG = [
    {
        "id": "dairy",
        "name": "Молочка, сыр, яйца",
        "icon": "🥛",
        "items": [
            {"id": "d1", "name": "Молоко Простоквашино паст. 2.5%, 930 мл", "price": 79.99, "unit": "шт", "icon": "🥛", "image": ""},
            {"id": "d2", "name": "Кефир Домик в деревне 3.2%, 900 г", "price": 84.99, "unit": "шт", "icon": "🍶", "image": ""},
            {"id": "d3", "name": "Яйцо куриное Селяночка С1, 10 шт", "price": 109.99, "unit": "уп", "icon": "🥚", "image": ""},
            {"id": "d4", "name": "Масло сливочное Экомилк 82.5%, 180 г", "price": 189.99, "unit": "шт", "icon": "🧈", "image": ""},
            {"id": "d5", "name": "Сыр Брест-Литовск Сливочный 50%, 200 г", "price": 199.99, "unit": "шт", "icon": "🧀", "image": ""},
            {"id": "d6", "name": "Творог Савушкин Хуторок 5%, 300 г", "price": 119.99, "unit": "шт", "icon": "🥣", "image": ""},
            {"id": "d7", "name": "Сметана Простоквашино 15%, 300 г", "price": 82.99, "unit": "шт", "icon": "🥣", "image": ""}
        ]
    },
    {
        "id": "veg",
        "name": "Овощи, фрукты, зелень",
        "icon": "🍎",
        "items": [
            {"id": "v1", "name": "Бананы весовые, 1 кг", "price": 139.99, "unit": "кг", "icon": "🍌", "image": ""},
            {"id": "v2", "name": "Томаты розовые тепличные, 1 кг", "price": 249.99, "unit": "кг", "icon": "🍅", "image": ""},
            {"id": "v3", "name": "Огурцы среднеплодные гладкие, 1 кг", "price": 169.99, "unit": "кг", "icon": "🥒", "image": ""},
            {"id": "v4", "name": "Картофель мытый в сетке, 2 кг", "price": 119.99, "unit": "уп", "icon": "🥔", "image": ""},
            {"id": "v5", "name": "Яблоки Гала отборные, 1 кг", "price": 129.99, "unit": "кг", "icon": "🍎", "image": ""},
            {"id": "v6", "name": "Лук репчатый, 1 кг", "price": 39.99, "unit": "кг", "icon": "🧅", "image": ""},
            {"id": "v7", "name": "Морковь мытая, 1 кг", "price": 59.99, "unit": "кг", "icon": "🥕", "image": ""}
        ]
    },
    {
        "id": "bakery",
        "name": "Хлеб и свежая выпечка",
        "icon": "🥖",
        "items": [
            {"id": "b1", "name": "Батон Нарезной Коломенский, 400 г", "price": 49.99, "unit": "шт", "icon": "🥖", "image": ""},
            {"id": "b2", "name": "Хлеб Бородинский в нарезке, 350 г", "price": 54.99, "unit": "шт", "icon": "🍞", "image": ""},
            {"id": "b3", "name": "Лаваш Армянский тонкий, 200 г", "price": 44.99, "unit": "уп", "icon": "🫓", "image": ""},
            {"id": "b4", "name": "Хлеб Тостовый Harry's пшеничный, 470 г", "price": 109.99, "unit": "уп", "icon": "🍞", "image": ""},
            {"id": "b5", "name": "Слойка с яблоком из пекарни, 100 г", "price": 39.99, "unit": "шт", "icon": "🥐", "image": ""}
        ]
    },
    {
        "id": "meat",
        "name": "Мясо, птица, колбасы",
        "icon": "🥩",
        "items": [
            {"id": "m1", "name": "Филе грудки цыпленка Петелинка охл., 900 г", "price": 359.99, "unit": "уп", "icon": "🍗", "image": ""},
            {"id": "m2", "name": "Фарш Домашний Мираторг охл., 400 г", "price": 199.99, "unit": "уп", "icon": "🥩", "image": ""},
            {"id": "m3", "name": "Сосиски Папа Может Молочные, 450 г", "price": 179.99, "unit": "уп", "icon": "🌭", "image": ""},
            {"id": "m4", "name": "Колбаса Вязанка Докторская вареная, 450 г", "price": 219.99, "unit": "шт", "icon": "🍖", "image": ""},
            {"id": "m5", "name": "Свинина лопатка без кости Слово Мясника, 1 кг", "price": 349.99, "unit": "кг", "icon": "🥩", "image": ""}
        ]
    },
    {
        "id": "grocery",
        "name": "Бакалея, макароны, крупы",
        "icon": "🍝",
        "items": [
            {"id": "g1", "name": "Макароны Barilla Spaghetti №5, 450 г", "price": 109.99, "unit": "уп", "icon": "🍝", "image": ""},
            {"id": "g2", "name": "Крупа гречневая Увелка в пакетиках, 400 г", "price": 79.99, "unit": "уп", "icon": "🌾", "image": ""},
            {"id": "g3", "name": "Рис Националь Краснодарский, 900 г", "price": 124.99, "unit": "уп", "icon": "🍚", "image": ""},
            {"id": "g4", "name": "Масло подсолнечное Слобода раф., 1 л", "price": 139.99, "unit": "бут", "icon": "🌻", "image": ""},
            {"id": "g5", "name": "Сахар белый кристаллический, 1 кг", "price": 69.99, "unit": "уп", "icon": "🧂", "image": ""},
            {"id": "g6", "name": "Мука пшеничная Макфа высший сорт, 2 кг", "price": 114.99, "unit": "уп", "icon": "🌾", "image": ""}
        ]
    },
    {
        "id": "drinks",
        "name": "Вода, соки, напитки",
        "icon": "🧃",
        "items": [
            {"id": "dr1", "name": "Вода Святой Источник негазированная, 1.5 л", "price": 54.99, "unit": "бут", "icon": "💧", "image": ""},
            {"id": "dr2", "name": "Сок Добрый Яблоко без сахара, 1 л", "price": 119.99, "unit": "шт", "icon": "🧃", "image": ""},
            {"id": "dr3", "name": "Напиток Добрый Кола, 1.5 л", "price": 129.99, "unit": "бут", "icon": "🥤", "image": ""},
            {"id": "dr4", "name": "Вода минеральная Ессентуки №4 стекло, 0.45 л", "price": 79.99, "unit": "бут", "icon": "🍾", "image": ""},
            {"id": "dr5", "name": "Чай Greenfield Golden Ceylon в пак., 25 шт", "price": 109.99, "unit": "уп", "icon": "☕", "image": ""}
        ]
    },
    {
        "id": "sweets",
        "name": "Сладости, чипсы, снеки",
        "icon": "🍫",
        "items": [
            {"id": "s1", "name": "Шоколад Alpen Gold Молочный с фундуком, 85 г", "price": 74.99, "unit": "шт", "icon": "🍫", "image": ""},
            {"id": "s2", "name": "Печенье Юбилейное Традиционное, 313 г", "price": 99.99, "unit": "уп", "icon": "🍪", "image": ""},
            {"id": "s3", "name": "Чипсы Lay's Сметана и зелень, 140 г", "price": 149.99, "unit": "уп", "icon": "🥔", "image": ""},
            {"id": "s4", "name": "Батончик Snickers Super, 80 г", "price": 69.99, "unit": "шт", "icon": "🍫", "image": ""}
        ]
    },
    {
        "id": "home",
        "name": "Для дома и гигиены",
        "icon": "🧻",
        "items": [
            {"id": "h1", "name": "Бумага туалетная Zewa Plus 2 слоя, 8 рул.", "price": 239.99, "unit": "уп", "icon": "🧻", "image": ""},
            {"id": "h2", "name": "Средство для мытья посуды Fairy Лимон, 450 мл", "price": 129.99, "unit": "шт", "icon": "🧴", "image": ""},
            {"id": "h3", "name": "Губки для посуды Фрекен Бок, 5 шт", "price": 64.99, "unit": "уп", "icon": "🧽", "image": ""},
            {"id": "h4", "name": "Пакеты для мусора 35 л прочные, 30 шт", "price": 79.99, "unit": "рул", "icon": "🗑️", "image": ""}
        ]
    }
]


def load_active_catalog():
    """Читает каталог из файла catalog_5ka.json или создает его из DEFAULT_CATALOG."""
    if not os.path.exists(CATALOG_FILE):
        initial_payload = {
            "updated_at": datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S MSK"),
            "source": "initial_seed",
            "total_categories": len(DEFAULT_CATALOG),
            "total_items": sum(len(c["items"]) for c in DEFAULT_CATALOG),
            "categories": DEFAULT_CATALOG
        }
        try:
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump(initial_payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Не удалось записать стартовый {CATALOG_FILE}: {e}")
        return DEFAULT_CATALOG, initial_payload["updated_at"]

    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "categories" in data:
                return data["categories"], data.get("updated_at", "Неизвестно")
            elif isinstance(data, list):
                return data, "Неизвестно"
    except Exception as e:
        logger.error(f"Ошибка чтения {CATALOG_FILE}: {e}")

    return DEFAULT_CATALOG, "Резервная копия"


# =====================================================================
# ПЛАНИРОВЩИК ЗАДАЧ APSCHEDULER (ЕЖЕДНЕВНО В 01:00 НОЧИ ПО МСК)
# =====================================================================
def scheduled_daily_catalog_sync():
    """Фоновая задача ежедневного обновления каталога в 01:00 ночи."""
    logger.info("⏰ [APScheduler] Запуск планового ночного обновления каталога 5ka.ru (01:00 MSK)...")
    res = update_catalog_from_5ka()
    LAST_SYNC_META["last_run"] = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S MSK")
    LAST_SYNC_META["status"] = res.get("status", "unknown")
    if res.get("ok"):
        LAST_SYNC_META["items_count"] = res.get("items_count", 0)
        LAST_SYNC_META["categories_count"] = res.get("categories_count", 0)


scheduler = BackgroundScheduler(timezone=MOSCOW_TZ)
scheduler.add_job(
    func=scheduled_daily_catalog_sync,
    trigger=CronTrigger(hour=1, minute=0, timezone=MOSCOW_TZ),
    id="daily_5ka_catalog_sync",
    name="Ежедневный парсинг каталога 5ka.ru в 01:00 MSK",
    replace_existing=True
)
scheduler.start()
logger.info("✅ Планировщик APScheduler запущен: автообновление каталога настроено на 01:00 ночи (Europe/Moscow).")
atexit.register(lambda: scheduler.shutdown(wait=False))


# =====================================================================
# РАБОТА С БАЗОЙ ПОЛУЧАТЕЛЕЙ (JSON)
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
    """Ручной запуск парсера из интерфейса Mini App или для проверки."""
    logger.info("🔄 Запрошено принудительное обновление каталога 5ka.ru пользователем...")
    res = update_catalog_from_5ka()
    categories, updated_at = load_active_catalog()
    return jsonify({
        "sync_result": res,
        "updated_at": updated_at,
        "categories_count": len(categories),
        "items_count": sum(len(c.get("items", [])) for c in categories)
    })


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
            f"🔄 Каталог автоматически обновляется каждую ночь в 01:00 МСК.\n"
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
    # Создаём стартовый файл каталога при первом запуске
    load_active_catalog()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
