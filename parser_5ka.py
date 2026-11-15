import os
import json
import time
import logging
from datetime import datetime
import pytz

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    import requests as std_requests
    HAS_CFFI = False

# Настройка логирования для консоли Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("5kaParser")

CATALOG_FILE = "catalog_5ka.json"
DEFAULT_STORE_CODE = os.environ.get("STORE_SAP_CODE", "Y232")
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Иконки по ключевым словам категорий Пятёрочки
CATEGORY_ICONS = {
    "молоч": "🥛", "сыр": "🧀", "яйц": "🥚",
    "овощ": "🍅", "фрукт": "🍎", "зелен": "🥬", "ягод": "🍓",
    "хлеб": "🥖", "выпеч": "🥐", "кондит": "🍰", "сладост": "🍫", "снек": "🥔", "чипс": "🥔",
    "мяс": "🥩", "птиц": "🍗", "колбас": "🌭", "сосиск": "🌭",
    "рыб": "🐟", "морепрод": "🦐",
    "бакале": "🍝", "макарон": "🍝", "круп": "🌾", "масл": "🌻", "консерв": "🥫",
    "вод": "💧", "сок": "🧃", "напит": "🥤", "чай": "☕", "кофе": "☕",
    "заморож": "🧊", "пельмен": "🥟", "морожен": "🍦",
    "дом": "🧻", "гигиен": "🧴", "уборк": "🧽", "детск": "🍼",
    "животн": "🐾", "кошк": "🐱", "собак": "🐶", "готовая еда": "🍱"
}

def guess_category_icon(cat_name: str) -> str:
    lower = cat_name.lower()
    for key, icon in CATEGORY_ICONS.items():
        if key in lower:
            return icon
    return "📦"


def get_http_session():
    """Создает сессию с TLS-отпечатком Chrome для обхода защиты 5ka.ru."""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://5ka.ru",
        "Referer": "https://5ka.ru/catalog/",
        "X-Device-Type": "desktop",
        "X-Platform": "webapp"
    }
    if HAS_CFFI:
        session = cffi_requests.Session(impersonate="chrome120")
        session.headers.update(headers)
        return session
    else:
        session = std_requests.Session()
        headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        session.headers.update(headers)
        return session


def fetch_categories(session, store_code: str):
    """Запрашивает дерево категорий из API Пятёрочки."""
    endpoints = [
        f"https://5d.5ka.ru/api/catalog/v1/stores/{store_code}/categories?mode=delivery&include_subcategories=1",
        f"https://5d.5ka.ru/api/catalog/v2/stores/{store_code}/categories?mode=delivery",
        "https://5ka.ru/api/v2/categories/"
    ]
    for url in endpoints:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info(f"Категории успешно получены из {url} (найдено разделов: {len(data)})")
                    return data
        except Exception as e:
            logger.warning(f"Попытка запроса категорий {url} не удалась: {e}")
    return []


def fetch_category_products(session, store_code: str, cat_id: str):
    """Выгружает все товары конкретной категории с пагинацией."""
    items = []
    limit = 40
    offset = 0

    while True:
        urls = [
            f"https://5d.5ka.ru/api/catalog/v1/stores/{store_code}/categories/{cat_id}/products?mode=delivery&limit={limit}&offset={offset}",
            f"https://5d.5ka.ru/api/catalog/v2/stores/{store_code}/categories/{cat_id}/products?mode=delivery&limit={limit}&offset={offset}"
        ]
        page_products = None
        for url in urls:
            try:
                resp = session.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    page_products = data.get("products") if isinstance(data, dict) else data
                    if isinstance(page_products, list):
                        break
            except Exception:
                continue

        if not page_products:
            break

        for prod in page_products:
            parsed = normalize_product(prod)
            if parsed:
                items.append(parsed)

        if len(page_products) < limit or offset >= 200:
            break
        offset += limit
        time.sleep(0.2)

    return items


def fetch_special_offers_fallback(session):
    """Резервный парсинг через публичный эндпоинт special_offers Пятёрочки."""
    grouped = {}
    page = 1
    while page <= 15:
        url = f"https://5ka.ru/api/v2/special_offers/?records_per_page=40&page={page}"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            for prod in results:
                cat_name = prod.get("group", {}).get("parent_group_name") or "Товары каталога"
                cat_id = str(prod.get("group", {}).get("parent_group_code") or "cat_general")
                if cat_id not in grouped:
                    grouped[cat_id] = {
                        "id": cat_id,
                        "name": cat_name,
                        "icon": guess_category_icon(cat_name),
                        "items": []
                    }
                parsed = normalize_product(prod)
                if parsed:
                    grouped[cat_id]["items"].append(parsed)
            if not data.get("next"):
                break
            page += 1
            time.sleep(0.25)
        except Exception as e:
            logger.warning(f"Ошибка резервного эндпоинта на стр. {page}: {e}")
            break
    return list(grouped.values())


def normalize_product(raw: dict):
    """Приводит товар из разных версий API 5ka.ru к единому формату для Mini App."""
    try:
        prod_id = str(raw.get("plu") or raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not prod_id or not name:
            return None

        # Извлечение актуальной цены
        price = 0.0
        prices_obj = raw.get("prices") or raw.get("current_prices") or {}
        if isinstance(prices_obj, dict):
            val = (
                prices_obj.get("cpd_promo_price")
                or prices_obj.get("promo")
                or prices_obj.get("regular")
                or prices_obj.get("price_reg__min")
                or prices_obj.get("price_promo__min")
            )
            if val is not None:
                price = float(str(val).replace(",", "."))
        elif isinstance(prices_obj, list) and len(prices_obj) > 0:
            price = float(str(prices_obj[0].get("value", 0)).replace(",", "."))

        if price <= 0 and raw.get("price"):
            price = float(str(raw.get("price")).replace(",", "."))

        if price <= 0:
            return None

        # Извлечение ссылки на фото товара
        image_url = ""
        img_links = raw.get("image_links") or {}
        if isinstance(img_links, dict):
            normal_list = img_links.get("normal") or img_links.get("small") or []
            if isinstance(normal_list, list) and normal_list:
                image_url = normal_list[0]
        if not image_url:
            image_url = raw.get("img_link") or raw.get("image") or ""

        unit = str(raw.get("uom") or raw.get("property_clarification") or "шт").strip()
        if len(unit) > 10:
            unit = "шт"

        return {
            "id": f"p_{prod_id}",
            "plu": prod_id,
            "name": name,
            "price": round(price, 2),
            "unit": unit,
            "image": image_url,
            "icon": "🛒"
        }
    except Exception:
        return None


def update_catalog_from_5ka(store_code: str = DEFAULT_STORE_CODE) -> dict:
    """
    Главная функция парсинга каталога https://5ka.ru/catalog/.
    Вызывается планировщиком каждый день в 01:00 ночи и при ручном обновлении.
    """
    start_ts = datetime.now(MOSCOW_TZ)
    logger.info(f"=== [СТАРТ ПАРСИНГА 5KA.RU] Время старта: {start_ts.strftime('%Y-%m-%d %H:%M:%S MSK')} | Магазин: {store_code} ===")

    session = get_http_session()
    parsed_categories = []
    total_products = 0

    try:
        raw_categories = fetch_categories(session, store_code)

        for cat in raw_categories:
            cat_id = str(cat.get("id") or cat.get("category_id") or "").strip()
            cat_name = str(cat.get("name") or "").strip()
            if not cat_id or not cat_name:
                continue

            icon = guess_category_icon(cat_name)
            cat_items = []
            seen_ids = set()

            # Если есть подкатегории, обходим их или саму категорию
            subcats = cat.get("categories") or cat.get("subcategories") or []
            target_ids = [str(sc.get("id")) for sc in subcats if sc.get("id")] or [cat_id]

            for tid in target_ids:
                prods = fetch_category_products(session, store_code, tid)
                for p in prods:
                    if p["id"] not in seen_ids:
                        p["icon"] = icon
                        seen_ids.add(p["id"])
                        cat_items.append(p)

            if cat_items:
                parsed_categories.append({
                    "id": cat_id,
                    "name": cat_name,
                    "icon": icon,
                    "items": cat_items
                })
                total_products += len(cat_items)
                logger.info(f"Собрана категория «{cat_name}»: {len(cat_items)} поз.")

        # Если витринный API вернул пустой ответ (например, из-за геоблокировки зарубежного IP Render),
        # пробуем резервный эндпоинт Пятёрочки
        if not parsed_categories:
            logger.info("Основной API витрины недоступен с текущего IP, пробуем резервный эндпоинт 5ka.ru...")
            parsed_categories = fetch_special_offers_fallback(session)
            total_products = sum(len(c.get("items", [])) for c in parsed_categories)

        if parsed_categories and total_products > 0:
            payload = {
                "updated_at": datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S MSK"),
                "source": "https://5ka.ru/catalog/",
                "store_code": store_code,
                "total_categories": len(parsed_categories),
                "total_items": total_products,
                "categories": parsed_categories
            }
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            logger.info(
                f"=== [УСПЕШНО] Каталог 5ka.ru обновлен! Категорий: {len(parsed_categories)}, "
                f"Товаров: {total_products}. Данные сохранены в {CATALOG_FILE} ==="
            )
            return {
                "ok": True,
                "status": "success",
                "updated_at": payload["updated_at"],
                "categories_count": len(parsed_categories),
                "items_count": total_products
            }
        else:
            logger.warning(
                "=== [ВНИМАНИЕ] Сайт 5ka.ru не отдал открытые данные (возможна защита от зарубежных IP дата-центра Render). "
                "Сохраняем действующий локальный каталог без потери данных. ==="
            )
            return {
                "ok": False,
                "status": "blocked_or_empty",
                "error": "Сервер 5ka.ru отклонил запрос с IP Render (Geoblock/Cloudflare). Активен сохраненный каталог."
            }

    except Exception as e:
        logger.error(f"=== [ОШИБКА ПАРСИНГА 5KA.RU]: {str(e)} ===", exc_info=True)
        return {
            "ok": False,
            "status": "error",
            "error": str(e)
        }
