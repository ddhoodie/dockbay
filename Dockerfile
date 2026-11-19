FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Isključujemo testni SQLite režim unutar kontejnera kako bi aplikacija koristila PostgreSQL i Redis
ENV UKS_TEST_DB=""

WORKDIR /app

# Sistemske zavisnosti za psycopg2 i curl (koristan za Docker healthcheck na /health/)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Priprema direktorijuma za statičke fajlove i organizacione slike (media/)
RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

# 1. Skuplja statičke fajlove za NGINX
# 2. Pokreće migracije (pri čemu generiše superadmin_password.txt ako ne postoji)
# 3. Pokreće ship_logs u pozadini (&) za slanje dockbay.log u Elasticsearch
# 4. Pokreće Gunicorn server u prvom planu (exec prosleđuje signale za gašenje)
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate && python manage.py ship_logs & exec gunicorn dockbay.wsgi:application --bind 0.0.0.0:8000"]