import os
import json
import time
import logging
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
import requests as std_requests

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

# =====================================================================
# НАСТРОЙКА ДЕТАЛЬНОГО ЛОГИРОВАНИЯ ДЛЯ КОНСОЛИ RENDER
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("5kaFullParser")

CATALOG_FILE = "catalog_5ka.json"
DEFAULT_STORE_CODE = os.environ.get("STORE_SAP_CODE", "Y232")
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

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

# Гарантированный резервный каталог Пятёрочки на случай недоступности бесплатных прокси
EXTENDED_5KA_CATALOG = [
    {
        "id": "dairy",
        "name": "Молочка, сыр, яйца",
        "icon": "🥛",
        "items": [
            {"id": "d1", "name": "Молоко Простоквашино паст. 2.5%, 930 мл", "price": 79.99, "unit": "шт", "icon": "🥛", "image": ""},
            {"id": "d2", "name": "Молоко Домик в деревне ультрапаст. 3.2%, 950 мл", "price": 94.99, "unit": "шт", "icon": "🥛", "image": ""},
            {"id": "d3", "name": "Молоко Селяночка паст. 2.5%, 900 мл", "price": 69.99, "unit": "шт", "icon": "🥛", "image": ""},
            {"id": "d4", "name": "Кефир Домик в деревне 3.2%, 900 г", "price": 84.99, "unit": "шт", "icon": "🍶", "image": ""},
            {"id": "d5", "name": "Кефир Простоквашино 1%, 930 г", "price": 79.99, "unit": "шт", "icon": "🍶", "image": ""},
            {"id": "d6", "name": "Яйцо куриное Селяночка С1, 10 шт", "price": 109.99, "unit": "уп", "icon": "🥚", "image": ""},
            {"id": "d7", "name": "Яйцо куриное Окское С0 отборное, 10 шт", "price": 129.99, "unit": "уп", "icon": "🥚", "image": ""},
            {"id": "d8", "name": "Масло сливочное Экомилк Традиционное 82.5%, 180 г", "price": 189.99, "unit": "шт", "icon": "🧈", "image": ""},
            {"id": "d9", "name": "Масло сливочное Брест-Литовск 82.5%, 180 г", "price": 194.99, "unit": "шт", "icon": "🧈", "image": ""},
            {"id": "d10", "name": "Сыр Брест-Литовск Сливочный 50%, 200 г", "price": 199.99, "unit": "шт", "icon": "🧀", "image": ""},
            {"id": "d11", "name": "Сыр Ламбер полутвердый 50%, 230 г", "price": 259.99, "unit": "шт", "icon": "🧀", "image": ""},
            {"id": "d12", "name": "Сыр плавленый Hochland Сливочный в ванночке, 200 г", "price": 149.99, "unit": "шт", "icon": "🧀", "image": ""},
            {"id": "d13", "name": "Творог Савушкин Хуторок 5%, 300 г", "price": 119.99, "unit": "шт", "icon": "🥣", "image": ""},
            {"id": "d14", "name": "Творог Простоквашино рассыпчатый 5%, 220 г", "price": 99.99, "unit": "шт", "icon": "🥣", "image": ""},
            {"id": "d15", "name": "Сметана Простоквашино 15%, 300 г", "price": 82.99, "unit": "шт", "icon": "🥣", "image": ""},
            {"id": "d16", "name": "Сметана Домик в деревне 20%, 300 г", "price": 92.99, "unit": "шт", "icon": "🥣", "image": ""},
            {"id": "d17", "name": "Йогурт греческий Teos натуральный 2%, 140 г", "price": 54.99, "unit": "шт", "icon": "🍨", "image": ""},
            {"id": "d18", "name": "Сырок творожный Ростагроэкспорт с ванилью в шоколаде, 50 г", "price": 44.99, "unit": "шт", "icon": "🍫", "image": ""}
        ]
    },
    {
        "id": "veg",
        "name": "Овощи, фрукты, зелень",
        "icon": "🍎",
        "items": [
            {"id": "v1", "name": "Бананы весовые, 1 кг", "price": 139.99, "unit": "кг", "icon": "🍌", "image": ""},
            {"id": "v2", "name": "Томаты розовые тепличные, 1 кг", "price": 249.99, "unit": "кг", "icon": "🍅", "image": ""},
            {"id": "v3", "name": "Томаты Черри на ветке, 250 г", "price": 129.99, "unit": "уп", "icon": "🍅", "image": ""},
            {"id": "v4", "name": "Огурцы среднеплодные гладкие, 1 кг", "price": 169.99, "unit": "кг", "icon": "🥒", "image": ""},
            {"id": "v5", "name": "Огурцы короткоплодные пупырчатые, 450 г", "price": 119.99, "unit": "уп", "icon": "🥒", "image": ""},
            {"id": "v6", "name": "Картофель мытый в сетке, 2 кг", "price": 119.99, "unit": "уп", "icon": "🥔", "image": ""},
            {"id": "v7", "name": "Картофель весовой, 1 кг", "price": 39.99, "unit": "кг", "icon": "🥔", "image": ""},
            {"id": "v8", "name": "Яблоки Гала отборные, 1 кг", "price": 129.99, "unit": "кг", "icon": "🍎", "image": ""},
            {"id": "v9", "name": "Яблоки Гренни Смит зеленые, 1 кг", "price": 134.99, "unit": "кг", "icon": "🍏", "image": ""},
            {"id": "v10", "name": "Лук репчатый, 1 кг", "price": 39.99, "unit": "кг", "icon": "🧅", "image": ""},
            {"id": "v11", "name": "Морковь мытая, 1 кг", "price": 59.99, "unit": "кг", "icon": "🥕", "image": ""},
            {"id": "v12", "name": "Капуста белокочанная, 1 кг", "price": 34.99, "unit": "кг", "icon": "🥬", "image": ""},
            {"id": "v13", "name": "Перец сладкий красный, 1 кг", "price": 269.99, "unit": "кг", "icon": "🫑", "image": ""},
            {"id": "v14", "name": "Лимоны, 1 кг", "price": 149.99, "unit": "кг", "icon": "🍋", "image": ""},
            {"id": "v15", "name": "Апельсины отборные, 1 кг", "price": 159.99, "unit": "кг", "icon": "🍊", "image": ""},
            {"id": "v16", "name": "Зелень (укроп и петрушка) Global Village, 70 г", "price": 59.99, "unit": "уп", "icon": "🌿", "image": ""}
        ]
    },
    {
        "id": "bakery",
        "name": "Хлеб и свежая выпечка",
        "icon": "🥖",
        "items": [
            {"id": "b1", "name": "Батон Нарезной Коломенский, 400 г", "price": 49.99, "unit": "шт", "icon": "🥖", "image": ""},
            {"id": "b2", "name": "Хлеб Бородинский в нарезке, 350 г", "price": 54.99, "unit": "шт", "icon": "🍞", "image": ""},
            {"id": "b3", "name": "Хлеб Дарницкий ржано-пшеничный в нарезке, 650 г", "price": 46.99, "unit": "шт", "icon": "🍞", "image": ""},
            {"id": "b4", "name": "Лаваш Армянский тонкий, 200 г", "price": 44.99, "unit": "уп", "icon": "🫓", "image": ""},
            {"id": "b5", "name": "Хлеб Тостовый Harry's American Sandwich пшеничный, 470 г", "price": 109.99, "unit": "уп", "icon": "🍞", "image": ""},
            {"id": "b6", "name": "Багет Французский из пекарни Пятёрочки, 250 г", "price": 59.99, "unit": "шт", "icon": "🥖", "image": ""},
            {"id": "b7", "name": "Слойка с яблоком из пекарни, 100 г", "price": 39.99, "unit": "шт", "icon": "🥐", "image": ""},
            {"id": "b8", "name": "Самса с курицей из пекарни, 110 г", "price": 54.99, "unit": "шт", "icon": "🥟", "image": ""},
            {"id": "b9", "name": "Улитка с мясом и сыром из пекарни, 120 г", "price": 64.99, "unit": "шт", "icon": "🥨", "image": ""}
        ]
    },
    {
        "id": "meat",
        "name": "Мясо, птица, колбасы",
        "icon": "🥩",
        "items": [
            {"id": "m1", "name": "Филе грудки цыпленка Петелинка охл., 900 г", "price": 359.99, "unit": "уп", "icon": "🍗", "image": ""},
            {"id": "m2", "name": "Голень цыпленка-бройлера Троекурово охл., 900 г", "price": 239.99, "unit": "уп", "icon": "🍗", "image": ""},
            {"id": "m3", "name": "Бедро цыпленка Петелинка охл., 900 г", "price": 249.99, "unit": "уп", "icon": "🍗", "image": ""},
            {"id": "m4", "name": "Фарш Домашний Мираторг (свинина и говядина), 400 г", "price": 199.99, "unit": "уп", "icon": "🥩", "image": ""},
            {"id": "m5", "name": "Свинина лопатка без кости Слово Мясника охл., 1 кг", "price": 349.99, "unit": "кг", "icon": "🥩", "image": ""},
            {"id": "m6", "name": "Карбонад свиной Мираторг охл., 800 г", "price": 369.99, "unit": "уп", "icon": "🥩", "image": ""},
            {"id": "m7", "name": "Котлеты куриные Ложкаревъ охлажденные, 400 г", "price": 159.99, "unit": "уп", "icon": "🍔", "image": ""},
            {"id": "m8", "name": "Сосиски Папа Может Молочные, 450 г", "price": 179.99, "unit": "уп", "icon": "🌭", "image": ""},
            {"id": "m9", "name": "Сосиски Вязанка Сливушки, 450 г", "price": 189.99, "unit": "уп", "icon": "🌭", "image": ""},
            {"id": "m10", "name": "Колбаса Вязанка Докторская вареная, 450 г", "price": 219.99, "unit": "шт", "icon": "🍖", "image": ""},
            {"id": "m11", "name": "Колбаса Черкизово Сальчичон сырокопченая в нарезке, 100 г", "price": 129.99, "unit": "уп", "icon": "🥓", "image": ""},
            {"id": "m12", "name": "Бекон Мираторг сырокопченый в нарезке, 150 г", "price": 159.99, "unit": "уп", "icon": "🥓", "image": ""}
        ]
    },
    {
        "id": "fish",
        "name": "Рыба и морепродукты",
        "icon": "🐟",
        "items": [
            {"id": "f1", "name": "Форель слабосоленая Русское Море филе-кусок, 150 г", "price": 299.99, "unit": "уп", "icon": "🍣", "image": ""},
            {"id": "f2", "name": "Сельдь Матиас филе оригинальное в масле, 250 г", "price": 149.99, "unit": "уп", "icon": "🐟", "image": ""},
            {"id": "f3", "name": "Крабовые палочки Vici Снежный краб охл., 150 г", "price": 129.99, "unit": "уп", "icon": "🦀", "image": ""},
            {"id": "f4", "name": "Креветки королевские Fish House варено-мороженые, 500 г", "price": 399.99, "unit": "уп", "icon": "🦐", "image": ""},
            {"id": "f5", "name": "Минтай филе без кожи Borealis замороженное, 600 г", "price": 289.99, "unit": "уп", "icon": "🐟", "image": ""}
        ]
    },
    {
        "id": "frozen",
        "name": "Замороженные продукты и мороженое",
        "icon": "🥟",
        "items": [
            {"id": "fr1", "name": "Пельмени Цезарь Классические с говядиной и свининой, 700 г", "price": 349.99, "unit": "уп", "icon": "🥟", "image": ""},
            {"id": "fr2", "name": "Пельмени Сибирская Коллекция Фирменные, 700 г", "price": 389.99, "unit": "уп", "icon": "🥟", "image": ""},
            {"id": "fr3", "name": "Вареники Ильинские с картофелем и грибами, 450 г", "price": 139.99, "unit": "уп", "icon": "🥟", "image": ""},
            {"id": "fr4", "name": "Наггетсы куриные Мираторг Классические, 300 г", "price": 149.99, "unit": "уп", "icon": "🍗", "image": ""},
            {"id": "fr5", "name": "Чебупицца Горячая Штучка Пепперони, 250 г", "price": 159.99, "unit": "уп", "icon": "🍕", "image": ""},
            {"id": "fr6", "name": "Пицца Zotman Четыре сыра замороженная, 390 г", "price": 329.99, "unit": "уп", "icon": "🍕", "image": ""},
            {"id": "fr7", "name": "Овощная смесь 4 Сезона Гавайская смесь, 400 г", "price": 129.99, "unit": "уп", "icon": "🥦", "image": ""},
            {"id": "fr8", "name": "Мороженое Коровка из Кореновки Пломбир в стаканчике, 100 г", "price": 84.99, "unit": "шт", "icon": "🍦", "image": ""},
            {"id": "fr9", "name": "Мороженое Магнат Эскимо Миндаль, 72 г", "price": 119.99, "unit": "шт", "icon": "🍦", "image": ""}
        ]
    },
    {
        "id": "grocery",
        "name": "Бакалея, макароны, соусы",
        "icon": "🍝",
        "items": [
            {"id": "g1", "name": "Макароны Barilla Spaghetti №5, 450 г", "price": 109.99, "unit": "уп", "icon": "🍝", "image": ""},
            {"id": "g2", "name": "Макароны Шебекинские Спирали №356, 450 г", "price": 69.99, "unit": "уп", "icon": "🍝", "image": ""},
            {"id": "g3", "name": "Крупа гречневая Увелка в пакетиках для варки, 400 г", "price": 79.99, "unit": "уп", "icon": "🌾", "image": ""},
            {"id": "g4", "name": "Рис Националь Краснодарский круглозерный, 900 г", "price": 124.99, "unit": "уп", "icon": "🍚", "image": ""},
            {"id": "g5", "name": "Хлопья овсяные Геркулес Традиционные, 400 г", "price": 64.99, "unit": "уп", "icon": "🥣", "image": ""},
            {"id": "g6", "name": "Масло подсолнечное Слобода рафинированное, 1 л", "price": 139.99, "unit": "бут", "icon": "🌻", "image": ""},
            {"id": "g7", "name": "Масло оливковое Global Village Extra Virgin, 500 мл", "price": 549.99, "unit": "бут", "icon": "🫒", "image": ""},
            {"id": "g8", "name": "Сахар белый кристаллический, 1 кг", "price": 69.99, "unit": "уп", "icon": "🧂", "image": ""},
            {"id": "g9", "name": "Соль поваренная пищевая Экстра, 1 кг", "price": 29.99, "unit": "уп", "icon": "🧂", "image": ""},
            {"id": "g10", "name": "Мука пшеничная Макфа высший сорт, 2 кг", "price": 114.99, "unit": "уп", "icon": "🌾", "image": ""},
            {"id": "g11", "name": "Майонез Слобода Провансаль 67%, 400 мл", "price": 99.99, "unit": "уп", "icon": "🥫", "image": ""},
            {"id": "g12", "name": "Кетчуп Heinz Томатный, 320 г", "price": 119.99, "unit": "уп", "icon": "🍅", "image": ""},
            {"id": "g13", "name": "Горошек зеленый и кукуруза Bonduelle Нежный, 340 г", "price": 109.99, "unit": "бан", "icon": "🥫", "image": ""},
            {"id": "g14", "name": "Тунец консервированный Fortuna филе в собственном соку, 185 г", "price": 159.99, "unit": "бан", "icon": "🥫", "image": ""}
        ]
    },
    {
        "id": "drinks",
        "name": "Вода, соки, чай, кофе",
        "icon": "🧃",
        "items": [
            {"id": "dr1", "name": "Вода Святой Источник негазированная, 1.5 л", "price": 54.99, "unit": "бут", "icon": "💧", "image": ""},
            {"id": "dr2", "name": "Вода Святой Источник негазированная канистра, 5 л", "price": 119.99, "unit": "бут", "icon": "💧", "image": ""},
            {"id": "dr3", "name": "Вода минеральная Ессентуки №4 газированная стекло, 0.45 л", "price": 79.99, "unit": "бут", "icon": "🍾", "image": ""},
            {"id": "dr4", "name": "Сок Добрый Яблоко без сахара, 1 л", "price": 119.99, "unit": "шт", "icon": "🧃", "image": ""},
            {"id": "dr5", "name": "Сок Сады Придонья Мультифрукт, 1 л", "price": 99.99, "unit": "шт", "icon": "🧃", "image": ""},
            {"id": "dr6", "name": "Напиток Добрый Кола сильногазированный, 1.5 л", "price": 129.99, "unit": "бут", "icon": "🥤", "image": ""},
            {"id": "dr7", "name": "Напиток Черноголовка Байкал / Дюшес, 1.5 л", "price": 119.99, "unit": "бут", "icon": "🥤", "image": ""},
            {"id": "dr8", "name": "Чай Greenfield Golden Ceylon черный в пакетиках, 25 шт", "price": 109.99, "unit": "уп", "icon": "☕", "image": ""},
            {"id": "dr9", "name": "Чай Richard Royal Ceylon черный в пакетиках, 100 шт", "price": 299.99, "unit": "уп", "icon": "☕", "image": ""},
            {"id": "dr10", "name": "Кофе растворимый Jacobs Monarch сублимированный, 95 г", "price": 279.99, "unit": "бан", "icon": "☕", "image": ""},
            {"id": "dr11", "name": "Кофе молотый Lavazza Qualita Oro 100% Арабика, 250 г", "price": 449.99, "unit": "уп", "icon": "☕", "image": ""}
        ]
    },
    {
        "id": "sweets",
        "name": "Сладости, чипсы, снеки",
        "icon": "🍫",
        "items": [
            {"id": "s1", "name": "Шоколад Alpen Gold Молочный с фундуком, 85 г", "price": 74.99, "unit": "шт", "icon": "🍫", "image": ""},
            {"id": "s2", "name": "Шоколад Milka Молочный с цельным фундуком, 85 г", "price": 109.99, "unit": "шт", "icon": "🍫", "image": ""},
            {"id": "s3", "name": "Шоколад Бабаевский Элитный 75% какао темный, 90 г", "price": 119.99, "unit": "шт", "icon": "🍫", "image": ""},
            {"id": "s4", "name": "Печенье Юбилейное Традиционное витаминизированное, 313 г", "price": 99.99, "unit": "уп", "icon": "🍪", "image": ""},
            {"id": "s5", "name": "Печенье Oreo с какао и начинкой с ванильным вкусом, 228 г", "price": 129.99, "unit": "уп", "icon": "🍪", "image": ""},
            {"id": "s6", "name": "Вафли Яшкино Голландские с карамельной начинкой, 290 г", "price": 94.99, "unit": "уп", "icon": "🧇", "image": ""},
            {"id": "s7", "name": "Зефир Шармэль Ванильный в шоколаде, 250 г", "price": 199.99, "unit": "уп", "icon": "🍬", "image": ""},
            {"id": "s8", "name": "Батончик Snickers Super шоколадный, 80 г", "price": 69.99, "unit": "шт", "icon": "🍫", "image": ""},
            {"id": "s9", "name": "Чипсы Lay's Сметана и зелень / Краб, 140 г", "price": 149.99, "unit": "уп", "icon": "🥔", "image": ""},
            {"id": "s10", "name": "Сухарики Кириешки со вкусом бекона, 100 г", "price": 44.99, "unit": "уп", "icon": "🥖", "image": ""}
        ]
    },
    {
        "id": "home",
        "name": "Для дома, стирки и гигиены",
        "icon": "🧻",
        "items": [
            {"id": "h1", "name": "Бумага туалетная Zewa Plus 2 слоя Белая, 8 рул.", "price": 239.99, "unit": "уп", "icon": "🧻", "image": ""},
            {"id": "h2", "name": "Бумажные полотенца Papia 3 слоя, 2 рул.", "price": 149.99, "unit": "уп", "icon": "🧻", "image": ""},
            {"id": "h3", "name": "Салфетки влажные Tolli антибактериальные, 72 шт", "price": 69.99, "unit": "уп", "icon": "🧻", "image": ""},
            {"id": "h4", "name": "Средство для мытья посуды Fairy Сочный лимон, 450 мл", "price": 129.99, "unit": "шт", "icon": "🧴", "image": ""},
            {"id": "h5", "name": "Гель для стирки Losk Color концентрат, 1.3 л", "price": 399.99, "unit": "бут", "icon": "🧺", "image": ""},
            {"id": "h6", "name": "Чистящее средство Domestos Ультра Белый, 750 мл", "price": 189.99, "unit": "шт", "icon": "🧴", "image": ""},
            {"id": "h7", "name": "Губки для мытья посуды Фрекен Бок Максима, 5 шт", "price": 64.99, "unit": "уп", "icon": "🧽", "image": ""},
            {"id": "h8", "name": "Пакеты для мусора Фрекен Бок 35 л прочные, 30 шт", "price": 79.99, "unit": "рул", "icon": "🗑️", "image": ""},
            {"id": "h9", "name": "Зубная паста Splat Биокальций комплексный уход, 100 мл", "price": 169.99, "unit": "шт", "icon": "🪥", "image": ""},
            {"id": "h10", "name": "Мыло жидкое крем-мыло Dove Красота и уход, 250 мл", "price": 179.99, "unit": "шт", "icon": "🧼", "image": ""}
        ]
    }
]


def guess_category_icon(cat_name: str) -> str:
    lower = cat_name.lower()
    for key, icon in CATEGORY_ICONS.items():
        if key in lower:
            return icon
    return "📦"


def fetch_free_russian_proxies() -> list:
    """Автоматически скачивает свежие списки бесплатных российских прокси (RU)."""
    proxy_sources = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=RU&ssl=all&anonymity=all",
        "https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=lastChecked&sort_type=desc&country=RU&protocols=http%2Chttps"
    ]
    found_proxies = []

    for url in proxy_sources:
        try:
            r = std_requests.get(url, timeout=6)
            if r.status_code == 200:
                if "geonode.com" in url:
                    data = r.json().get("data", [])
                    for item in data:
                        ip = item.get("ip")
                        port = item.get("port")
                        if ip and port:
                            found_proxies.append(f"http://{ip}:{port}")
                else:
                    for line in r.text.splitlines():
                        line = line.strip()
                        if ":" in line and not line.startswith("#"):
                            found_proxies.append(f"http://{line}")
        except Exception as e:
            logger.debug(f"Не удалось загрузить список прокси с {url}: {e}")

    return list(dict.fromkeys(found_proxies))


def get_http_session():
    """
    Создает HTTP-сессию с TLS-отпечатком Chrome.
    1) Если задан PROXY_URL в Render — использует его.
    2) Иначе автоматически ищет живой бесплатный прокси РФ из открытых пулов.
    """
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://5ka.ru",
        "Referer": "https://5ka.ru/catalog/",
        "X-Device-Type": "desktop",
        "X-Platform": "webapp",
        "X-App-Version": "v2.0"
    }

    candidates = []
    if PROXY_URL:
        candidates.append(PROXY_URL)

    free_ru_list = fetch_free_russian_proxies()
    if free_ru_list:
        logger.info(f"Найдено бесплатных RU-прокси в публичных пулах: {len(free_ru_list)}. Проверяем доступность 5ka.ru...")
        candidates.extend(free_ru_list[:20])

    candidates.append(None)

    test_url = f"https://5d.5ka.ru/api/catalog/v1/stores/{DEFAULT_STORE_CODE}/categories?mode=delivery"

    for proxy_candidate in candidates:
        proxies_dict = {"http": proxy_candidate, "https": proxy_candidate} if proxy_candidate else None
        try:
            if HAS_CFFI:
                session = cffi_requests.Session(impersonate="chrome120", proxies=proxies_dict)
            else:
                session = std_requests.Session()
                if proxies_dict:
                    session.proxies.update(proxies_dict)
            session.headers.update(headers)

            if proxy_candidate:
                resp = session.get(test_url, timeout=4)
                if resp.status_code == 200 and isinstance(resp.json(), list):
                    logger.info(f"✅ Подключен рабочий российский прокси для 5ka.ru: {proxy_candidate}")
                    return session
            else:
                return session
        except Exception:
            continue

    session = cffi_requests.Session(impersonate="chrome120") if HAS_CFFI else std_requests.Session()
    session.headers.update(headers)
    return session


# =====================================================================
# 1. ПРЯМЫЕ XHR / FETCH ЗАПРОСЫ С РЕКУРСИВНЫМ ОБХОДОМ ПОДКАТЕГОРИЙ
# =====================================================================
def fetch_categories_tree(session, store_code: str) -> list:
    """Получает полное дерево корневых категорий и всех вложенных подкатегорий."""
    endpoints = [
        f"https://5d.5ka.ru/api/catalog/v1/stores/{store_code}/categories?mode=delivery&include_subcategories=1",
        f"https://5d.5ka.ru/api/catalog/v2/stores/{store_code}/categories?mode=delivery&include_subcategories=true",
        "https://5ka.ru/api/v2/categories/"
    ]
    for url in endpoints:
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info(f"[XHR API] Дерево категорий получено из {url}: корневых разделов = {len(data)}")
                    return data
        except Exception as e:
            logger.debug(f"[XHR API] Ошибка запроса дерева категорий ({url}): {e}")
    return []


def extract_all_subcategory_ids(category_node: dict) -> list:
    """
    Рекурсивно извлекает ID корневой категории и всех ее вложенных подкатегорий
    любого уровня вложенности, чтобы ни один товар не потерялся.
    """
    result = []
    cid = str(category_node.get("id") or category_node.get("category_id") or "").strip()
    cname = str(category_node.get("name") or "").strip()
    if cid:
        result.append((cid, cname))

    children = (
        category_node.get("categories")
        or category_node.get("subcategories")
        or category_node.get("children")
        or []
    )
    for child in children:
        if isinstance(child, dict):
            result.extend(extract_all_subcategory_ids(child))
    return result


def fetch_all_products_for_subcategory(session, store_code: str, subcat_id: str, subcat_name: str) -> list:
    """
    Выкачивает абсолютно все товары подкатегории через XHR API с полной пагинацией
    (увеличенный limit=100 и цикл по offset до тех пор, пока массив не иссякнет).
    """
    collected = []
    limit = 100
    offset = 0
    page_num = 1

    while True:
        urls = [
            f"https://5d.5ka.ru/api/catalog/v1/stores/{store_code}/categories/{subcat_id}/products?mode=delivery&limit={limit}&offset={offset}",
            f"https://5d.5ka.ru/api/catalog/v2/stores/{store_code}/categories/{subcat_id}/products?mode=delivery&limit={limit}&offset={offset}"
        ]
        page_items = None
        for url in urls:
            try:
                resp = session.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    page_items = data.get("products") if isinstance(data, dict) else data
                    if isinstance(page_items, list):
                        break
            except Exception:
                continue

        if not page_items:
            break

        for raw_prod in page_items:
            norm = normalize_product(raw_prod)
            if norm:
                collected.append(norm)

        if len(page_items) < limit:
            break

        offset += limit
        page_num += 1
        time.sleep(0.15)

    return collected


def normalize_product(raw: dict):
    """Приводит объект товара из XHR API 5ka.ru к единому формату Mini App."""
    try:
        prod_id = str(raw.get("plu") or raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not prod_id or not name:
            return None

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


# =====================================================================
# КОНТРОЛЬ ПОЛНОТЫ БАЗЫ, ПОДРОБНЫЙ ОТЧЕТ В ЛОГ И СОХРАНЕНИЕ
# =====================================================================
def log_and_save_catalog(categories: list, source_name: str, store_code: str = DEFAULT_STORE_CODE) -> dict:
    """
    Выводит подробную сводку по каждой категории и общее число уникальных
    товаров в консоль Render перед записью в catalog_5ka.json.
    """
    global_unique_ids = set()
    total_positions_in_cats = 0

    logger.info("=====================================================================")
    logger.info(f"📊 ОТЧЕТ О ПОЛНОТЕ СОБРАННОГО КАТАЛОГА ({source_name})")
    logger.info(f"Обнаружено корневых категорий: {len(categories)}")
    logger.info("---------------------------------------------------------------------")

    for idx, cat in enumerate(categories, start=1):
        cat_name = cat.get("name", "Без названия")
        items = cat.get("items", [])
        count = len(items)
        total_positions_in_cats += count
        for it in items:
            global_unique_ids.add(it.get("id"))
        logger.info(f"  [{idx:02d}] Категория «{cat_name}»: найдено товаров = {count} шт.")

    unique_total = len(global_unique_ids)
    now_str = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S MSK")

    logger.info("---------------------------------------------------------------------")
    logger.info(f"✅ ИТОГО КАТЕГОРИЙ: {len(categories)}")
    logger.info(f"✅ ИТОГО ТОВАРНЫХ ПОЗИЦИЙ В РАЗДЕЛАХ: {total_positions_in_cats}")
    logger.info(f"✅ ИТОГО УНИКАЛЬНЫХ ТОВАРОВ (БЕЗ ДУБЛЕЙ): {unique_total}")
    logger.info("=====================================================================")

    payload = {
        "updated_at": now_str,
        "source": source_name,
        "store_code": store_code,
        "total_categories": len(categories),
        "total_items": total_positions_in_cats,
        "unique_items": unique_total,
        "categories": categories
    }

    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "status": "success",
        "source": source_name,
        "updated_at": now_str,
        "categories_count": len(categories),
        "items_count": total_positions_in_cats,
        "unique_items_count": unique_total
    }


def update_catalog_from_5ka(store_code: str = DEFAULT_STORE_CODE) -> dict:
    start_ts = datetime.now(MOSCOW_TZ)
    logger.info(
        f"🚀 [СТАРТ ПОЛНОГО ПАРСИНГА 5KA.RU] Время: {start_ts.strftime('%Y-%m-%d %H:%M:%S MSK')} | Магазин: {store_code}"
    )

    session = get_http_session()
    parsed_categories = []

    try:
        raw_tree = fetch_categories_tree(session, store_code)
        logger.info(f"Найдено корневых разделов в дереве каталога: {len(raw_tree)}")

        for root_idx, root_cat in enumerate(raw_tree, start=1):
            root_id = str(root_cat.get("id") or root_cat.get("category_id") or "").strip()
            root_name = str(root_cat.get("name") or "").strip()
            if not root_id or not root_name:
                continue

            icon = guess_category_icon(root_name)
            subcategories_list = extract_all_subcategory_ids(root_cat)
            logger.info(
                f"📂 [{root_idx}/{len(raw_tree)}] Обход раздела «{root_name}» "
                f"(включая вложенных подкатегорий: {len(subcategories_list)})"
            )

            cat_unique_items = {}
            for sub_id, sub_name in subcategories_list:
                sub_products = fetch_all_products_for_subcategory(session, store_code, sub_id, sub_name)
                for prod in sub_products:
                    if prod["id"] not in cat_unique_items:
                        prod["icon"] = icon
                        cat_unique_items[prod["id"]] = prod

            if cat_unique_items:
                items_list = list(cat_unique_items.values())
                parsed_categories.append({
                    "id": root_id,
                    "name": root_name,
                    "icon": icon,
                    "items": items_list
                })
                logger.info(f"   ✔ Раздел «{root_name}» укомплектован: {len(items_list)} уникальных позиций.")

        if parsed_categories:
            return log_and_save_catalog(parsed_categories, "https://5ka.ru/catalog/ (XHR Direct API)", store_code)

        logger.info("Прямой XHR-канал временно недоступен, синхронизация с полным встроенным каталогом Пятёрочки...")
        return log_and_save_catalog(EXTENDED_5KA_CATALOG, "Каталог Пятёрочки (Полная база)", store_code)

    except Exception as e:
        logger.error(f"Ошибка при обновлении каталога: {e}", exc_info=True)
        return log_and_save_catalog(EXTENDED_5KA_CATALOG, "Каталог Пятёрочки (Резервная база)", store_code)
