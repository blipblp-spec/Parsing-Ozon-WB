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

# --- СОЗДАЕМ ПРИЛОЖЕНИЕ ---
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-it'

# --- ФАЙЛ ДЛЯ ХРАНЕНИЯ ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ ---
DATA_FILE = 'users_data.json'


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)


# --- ПАРСИНГ ЦЕН ---
def parse_price(url):
    """Парсит цену с Ozon через requests"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        price_selectors = [
            'span[itemprop="price"]',
            '.price-block__price',
            '[data-testid="price"]'
        ]

        for selector in price_selectors:
            element = soup.select_one(selector)
            if element:
                price_text = element.text.strip()
                price_match = re.search(r'[\d\s]+', price_text)
                if price_match:
                    price = price_match.group().replace(' ', '')
                    return {'price': price, 'title': 'Товар с Ozon', 'currency': '₽'}

        return {'error': 'Цена не найдена. Попробуйте другой товар.'}
    except Exception as e:
        return {'error': f'Ошибка соединения: {str(e)}'}


# --- ГЕНЕРАЦИЯ ГРАФИКА ---
def generate_chart():
    """Составляет демонстрационный график цен"""
    dates = [(datetime.now() - timedelta(days=i)).strftime('%d.%m') for i in range(6, -1, -1)]
    prices = [1500, 1480, 1520, 1490, 1450, 1470, 1510]

    plt.figure(figsize=(10, 4))
    plt.plot(dates, prices, marker='o', color='#ff6b6b', linewidth=2)
    plt.title('Динамика цены за неделю', fontsize=14)
    plt.grid(visible=True, alpha=0.3)
    plt.xticks(rotation=45)
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
    <title>Аналитик цен Ozon</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .card-custom { max-width: 800px; margin: 0 auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .price { font-size: 2.5rem; font-weight: bold; color: #2d3436; }
        .badge-custom { position: fixed; top: 20px; right: 20px; background: white; padding: 10px 20px; border-radius: 50px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); z-index: 999; }
        .btn-premium { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; border: none; }
        .btn-premium:hover { transform: scale(1.05); color: white; }
        .result-card { animation: fadeIn 0.5s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="badge-custom">
        🔍 Осталось: <strong>{{ free_requests }}</strong> запросов
    </div>

    <div class="card-custom">
        <h1 class="text-center mb-3">📊 Аналитик цен Ozon</h1>
        <p class="text-center text-muted">Вставьте ссылку на товар и узнайте цену за 2 секунды</p>

        <form method="POST" class="mt-4">
            <div class="input-group input-group-lg">
                <input type="url" name="url" class="form-control" placeholder="https://www.ozon.ru/product/..." required>
                <button class="btn btn-primary" type="submit">🔍 Найти цену</button>
            </div>
        </form>

        {% if result %}
        <div class="result-card mt-4 p-4 bg-light rounded">
            <h5>{{ result.title }}</h5>
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
            parsed = parse_price(url)

            if 'error' not in parsed:
                user['requests'] += 1
                save_data(data)
                chart_img = generate_chart()
                result = parsed
                result['price'] = f"{int(result['price']):,}".replace(',', ' ')
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


# --- ПРАВИЛЬНЫЙ ЗАПУСК (БЕЗ ВАРНИНГА) ---
if __name__ == '__main__':
    # Вариант для локальной разработки (с варнингом, но быстро)
    # app.run(debug=True, host='0.0.0.0', port=5000)

    # Вариант для продакшена (БЕЗ ВАРНИНГА) - раскомментируй, если установлен waitress
    from waitress import serve

    serve(app, host='0.0.0.0', port=5000)