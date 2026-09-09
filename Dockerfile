FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --requirement requirements.txt

COPY max_bot.py ./
COPY certificates/ ./certificates/

RUN useradd --create-home --uid 10001 botuser \
    && chown -R botuser:botuser /app
USER botuser

CMD ["python", "max_bot.py"]
