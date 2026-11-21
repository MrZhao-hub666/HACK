ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/leads.sqlite3
WORKDIR /app
COPY src/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
COPY src/api /app/src/api
USER app
EXPOSE 8000
CMD ["python","-m","uvicorn","src.api.main:app","--host","0.0.0.0","--port","8000"]
