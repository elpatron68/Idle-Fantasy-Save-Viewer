FROM python:3.12-slim

WORKDIR /app

ARG GIT_COMMIT=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TRUST_PROXY=1 \
    DISABLE_LOCAL_VIEWER=1 \
    PREFERRED_URL_SCHEME=https \
    MAX_UPLOAD_MB=10

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py parser.py categories.py validation.py viewers.py security.py game_data.py house_data.py prestige_data.py advisor.py version.py ./
COPY game_data/ game_data/
COPY templates/ templates/
COPY static/ static/

RUN echo "$GIT_COMMIT" > BUILD_REF \
    && mkdir -p /data/viewers /data/uploads \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data

USER appuser

VOLUME ["/data"]
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
