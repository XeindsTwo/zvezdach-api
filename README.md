# Звездач — отдельный backend блога

Основан на chatus_api, с той же CMS, редактором, загрузкой медиа и API.
Палитра и логотип взяты из проекта zvezdach. База, секреты, пользователи,
медиа, зависимости и Git-история Chatus не переносились.

## Локальный запуск
Создайте новый venv, установите requirements.txt, скопируйте .env.example
в .env и задайте собственный секрет. Выполните npm ci, npm run css:build,
python manage.py migrate и python manage.py createsuperuser.
Запускайте python manage.py runserver 8001.

## Размещение рядом с Chatus
Используйте отдельные /opt/zvezdach-blog/app и /opt/zvezdach-blog/venv,
пользователя ОС, базу zvezdach_blog и роль PostgreSQL zvezdach_blog.
Создайте новый systemd-сервис с Gunicorn на 127.0.0.1:8001.
Сервис Chatus на 8000 не меняйте.
Для отдельного поддомена Caddy должен отдавать /media/ и /static/
из каталогов нового проекта, а остальные пути проксировать на 8001.
Домен, DNS, ресурсы VPS и имя сервиса нужно определить до выкладки.
Настройте свои ALLOWED_HOSTS, CORS, CSRF и FRONTEND_URL.
Production требует DEBUG=false, собственного SECRET_KEY и PostgreSQL.

Для общего домена задайте DJANGO_URL_PREFIX=/zvezdach и используйте Caddy handle_path /zvezdach/*, снимающий префикс перед проксированием на 8001
Статика и медиа должны обслуживаться отдельными маршрутами /zvezdach/static/* и /zvezdach/media/*
Имена и пути cookies изолированы от Chatus
Демонстрационные материалы Chatus не скопированы — seed_demo_articles
не запускайте. На production не копируйте чужую базу или .env.
