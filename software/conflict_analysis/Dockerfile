FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY . .

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[dev]" \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "conflict_analysis.wsgi:application", "--bind", "0.0.0.0:8000"]
