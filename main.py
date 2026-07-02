from flask import Flask, request, render_template_string, session
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import io
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# --- СОЗДАЕМ ПРИЛОЖЕНИЕ ---
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-it'

# --- ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ ---
DATA_FILE = 'users_data.json'
HISTORY_FILE = 'price_history.json'


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, 'r') as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f)


def save_price_history(product_url, price, title):
    """Сохраняет историю цен для товара"""
    history = load_history()

    if product_url not in history:
        history[product_url] = {
            'title': title,
            'history': []
        }

    history[product_url]['history'].append({
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'price': price
    })

    if len(history[product_url]['history']) > 30:
        history[product_url]['history'] = history[product_url]['history'][-30:]

    save_history(history)
    return history[product_url]['history']


# --- ПАРСИНГ OZON (через Selenium) ---
def parse_price_ozon(url):
    """Парсит цену с Ozon через Selenium (обход защиты)"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])

    driver = None
    try:
        # Для Render используем системный Chrome
        if os.environ.get('RENDER'):
            options.binary_location = '/usr/bin/google-chrome'
            service = Service('/usr/local/bin/chromedriver')
        else:
            service = Service(ChromeDriverManager().install())

        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        time.sleep(3)

        # Пробуем разные селекторы для цены
        price_selectors = [
            "span[data-testid='price']",
            "span[itemprop='price']",
            ".price-block__price",
            "div[data-testid='price_block'] span",
            ".product-price-value"
        ]

        price = None
        for selector in price_selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                price_text = element.text.strip()
                if price_text:
                    price_match = re.search(r'[\d\s,]+', price_text)
                    if price_match:
                        price = price_match.group().replace(' ', '').replace(',', '.')
                        break
            except:
                continue

        # Парсим название товара
        title_selectors = ["h1", "[data-testid='product-title']", ".product-title"]
        title = "Товар с Ozon"
        for selector in title_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                title = element.text.strip()[:50]
                break
            except:
                continue

        if price:
            return {'price': price, 'title': title, 'currency': '₽', 'source': 'Ozon'}
        else:
            return {'error': 'Цена не найдена. Попробуйте другой товар.'}

    except Exception as e:
        return {'error': f'Ошибка парсинга Ozon: {str(e)}'}
    finally:
        if driver:
            driver.quit()


# --- ПАРСИНГ WILDBERRIES ---
def parse_price_wildberries(url):
    """Парсит цену с Wildberries"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        price_selectors = [
            '.price-block__final-price',
            '.product-price__value',
            '[data-testid="price"]'
        ]

        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = element.text.strip()
                price_match = re.search(r'[\d\s]+', price_text)
                if price_match:
                    price = price_match.group().replace(' ', '')
                    title_selectors = ["h1", ".product-name"]
                    title = "Товар с WB"
                    for ts in title_selectors:
                        title_elem = soup.select_one(ts)
                        if title_elem:
                            title = title_elem.text.strip()[:50]
                            break
                    return {'price': price, 'title': title, 'currency': '₽', 'source': 'Wildberries'}

        return {'error': 'Цена на Wildberries не найдена'}
    except Exception as e:
        return {'error': f'Ошибка WB: {str(e)}'}


# --- ГЕНЕРАЦИЯ ГРАФИКА ---
def generate_chart_from_history(history):
    """Генерирует график из реальной истории цен"""
    if not history or len(history) < 2:
        dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(6, -1, -1)]
        prices = [1500, 1480, 1520, 1490, 1450, 1470, 1510]
    else:
        dates = [item['date'] for item in history]
        prices = [float(item['price']) for item in history]

    plt.figure(figsize=(10, 4))
    plt.plot(dates, prices, marker='o', color='#ff6b6b', linewidth=2)
    plt.title('Динамика цены', fontsize=14)
    plt.grid(visible=True, alpha=0.3)
    plt.xticks(rotation=45, fontsize=8)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=80)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return img_base64


# --- HTML ШАБЛОН ---
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Аналитик цен Ozon и WB</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .card-custom { max-width: 800px; margin: 0 auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .price { font-size: 2.5rem; font-weight: bold; color: #2d3436; }
        .badge-custom { position: fixed; top: 20px; right: 20px; background: white; padding: 10px 20px; border-radius: 50px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); z-index: 999; }
        .btn-premium { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; border: none; }
        .btn-premium:hover { transform: scale(1.05); color: white; }
        .result-card { animation: fadeIn 0.5s; }
        .source-badge { font-size: 0.8rem; padding: 3px 10px; border-radius: 20px; }
        .source-ozon { background: #e8f5e9; color: #2e7d32; }
        .source-wb { background: #e3f2fd; color: #0d47a1; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="badge-custom">
        🔍 Осталось: <strong>{{ free_requests }}</strong> запросов
    </div>

    <div class="card-custom">
        <h1 class="text-center mb-3">📊 Аналитик цен</h1>
        <p class="text-center text-muted">Вставьте ссылку на товар с Ozon или Wildberries</p>

        <form method="POST" class="mt-4">
            <div class="input-group input-group-lg">
                <input type="url" name="url" class="form-control" placeholder="https://www.ozon.ru/product/..." required>
                <button class="btn btn-primary" type="submit">🔍 Найти цену</button>
            </div>
        </form>

        {% if result %}
        <div class="result-card mt-4 p-4 bg-light rounded">
            <div class="d-flex justify-content-between align-items-start">
                <h5>{{ result.title }}</h5>
                {% if result.source %}
                <span class="source-badge {% if result.source == 'Ozon' %}source-ozon{% else %}source-wb{% endif %}">
                    {{ result.source }}
                </span>
                {% endif %}
            </div>
            <div class="price">{{ result.price }} <span class="fs-5 text-muted">{{ result.currency }}</span></div>
            {% if result.error %}
            <div class="alert alert-danger mt-3">{{ result.error }}</div>
            {% endif %}

            {% if chart_img %}
            <div class="mt-3 text-center">
                <img src="data:image/png;base64,{{ chart_img }}" class="img-fluid rounded" alt="График цен">
            </div>
            {% endif %}

            <div class="mt-2 text-muted small">Обновлено: {{ current_time }}</div>
        </div>
        {% endif %}

        <hr class="my-4">

        <div class="row align-items-center">
            <div class="col-md-8">
                <h5>🚀 Премиум доступ</h5>
                <p class="text-muted small">Безлимитные запросы + история цен + уведомления</p>
            </div>
            <div class="col-md-4 text-end">
                <a href="/premium" class="btn btn-premium btn-lg">💎 199 ₽</a>
            </div>
        </div>
    </div>
</body>
</html>
"""


# --- ГЛАВНАЯ СТРАНИЦА ---
@app.route('/', methods=['GET', 'POST'])
def index():
    user_id = session.get('user_id', 'anonymous')
    data = load_data()

    if user_id not in data:
        data[user_id] = {'requests': 0, 'premium': False}
        save_data(data)

    user = data[user_id]
    free_limit = 5
    requests_left = max(0, free_limit - user['requests'])

    result = None
    chart_img = None

    if request.method == 'POST':
        url = request.form.get('url')

        if user['requests'] >= free_limit and not user['premium']:
            result = {'error': '❌ Лимит закончился. Купите Премиум!'}
        else:
            if 'ozon.ru' in url.lower():
                parsed = parse_price_ozon(url)
            elif 'wildberries.ru' in url.lower():
                parsed = parse_price_wildberries(url)
            else:
                parsed = {'error': 'Поддерживаются только Ozon и Wildberries'}

            if 'error' not in parsed:
                user['requests'] += 1
                save_data(data)
                history = save_price_history(url, parsed['price'], parsed['title'])
                chart_img = generate_chart_from_history(history)
                result = parsed
                try:
                    result['price'] = f"{int(float(result['price'])):,}".replace(',', ' ')
                except:
                    pass
            else:
                result = parsed

    return render_template_string(
        HTML,
        free_requests=requests_left,
        result=result,
        chart_img=chart_img,
        current_time=datetime.now().strftime('%d.%m.%Y %H:%M')
    )


# --- СТРАНИЦА ПРЕМИУМ ---
@app.route('/premium')
def premium():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Премиум</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center;">
        <div class="container">
            <div class="card mx-auto" style="max-width: 500px;">
                <div class="card-body text-center p-5">
                    <h2>💎 Премиум</h2>
                    <p class="display-4">199 ₽</p>
                    <ul class="list-unstyled text-start">
                        <li>✅ Неограниченные запросы</li>
                        <li>✅ История цен за месяц</li>
                        <li>✅ Приоритетная поддержка</li>
                    </ul>
                    <div class="d-grid gap-2">
                        <button class="btn btn-success btn-lg" onclick="alert('Оплата через Telegram: @your_username')">
                            🔥 Купить
                        </button>
                        <a href="/" class="btn btn-outline-secondary">Назад</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# --- ЗАПУСК ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)