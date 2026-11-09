FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/      ./core/
COPY user_bot/  ./user_bot/
COPY manager_bot/ ./manager_bot/

RUN useradd -m bot && mkdir -p /app/data /app/logs && chown -R bot /app
USER bot

# default overridden per-service; kept for `docker compose run` convenience
CMD ["python", "-m", "user_bot.main"]