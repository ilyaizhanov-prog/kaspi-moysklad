# -*- coding: utf-8 -*-
"""
Минимальный веб-сервер, который отдаёт файл kaspi_feed.xml и папку с фото
товаров по постоянным ссылкам, и сам обновляет их по расписанию.

Этот файл нужен только если у вас пока нет своего сервера/хостинга, на
котором можно разместить готовый kaspi_feed.xml и фото. Если у вас уже есть
сайт или хостинг — проще запускать export_stock_to_kaspi.py и
export_images_to_kaspi.py по cron и обычным FTP/SFTP заливать результат на
хостинг, без этого сервера.

Запуск:
    pip install flask apscheduler
    python server.py

Сервер слушает 0.0.0.0:8000. Снаружи его нужно открыть через постоянный
домен/IP с https (например, через nginx + сертификат, либо через любой
PaaS/VPS). Ссылку вида https://ваш-домен/kaspi_feed.xml указываете в
кабинете Kaspi (Товары -> Загрузить прайс-лист -> Автоматическая загрузка),
а ссылку вида https://ваш-домен/kaspi_images/<артикул>.jpg - в
KASPI_IMAGES_BASE_URL в config.py.
"""
from flask import Flask, send_file, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

import config
import export_stock_to_kaspi
import export_images_to_kaspi

app = Flask(__name__)


def regenerate_feed():
    try:
        export_stock_to_kaspi.main()
    except Exception as exc:
        print(f"Ошибка при обновлении фида: {exc}")


def regenerate_images():
    try:
        export_images_to_kaspi.main()
    except Exception as exc:
        print(f"Ошибка при обновлении фото: {exc}")


@app.route("/kaspi_feed.xml")
def kaspi_feed():
    return send_file(config.KASPI_FEED_FILE_PATH, mimetype="application/xml")


@app.route("/kaspi_images/<path:filename>")
def kaspi_image(filename):
    return send_from_directory(config.KASPI_IMAGES_DIR, filename)


if __name__ == "__main__":
    regenerate_feed()    # сгенерировать файл сразу при старте
    regenerate_images()  # и скачать фото сразу при старте

    scheduler = BackgroundScheduler()
    scheduler.add_job(regenerate_feed, "interval", minutes=20)
    # фото меняются редко - обновляем реже, чтобы не дёргать МойСклад зря
    scheduler.add_job(regenerate_images, "interval", hours=6)
    scheduler.start()

    app.run(host="0.0.0.0", port=8000)
