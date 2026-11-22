ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project && useradd --create-home --uid 10001 app
COPY src/backend /app/src/backend
USER app
EXPOSE 8000
CMD ["python","-m","uvicorn","src.backend.api.main:app","--host","0.0.0.0","--port","8000"]
