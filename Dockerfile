FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home monitor \
    && mkdir /app/data && chown monitor:monitor /app/data
COPY monitor ./monitor
COPY config ./config
COPY demo ./demo
USER monitor
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "monitor.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
