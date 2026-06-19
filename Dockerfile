FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py parser.py categories.py validation.py viewers.py ./
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /data/viewers /data/uploads

VOLUME ["/data"]
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "app:app"]
