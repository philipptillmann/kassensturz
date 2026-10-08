FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    PORT=8080 \
    OMP_THREAD_LIMIT=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 kassensturz \
    && useradd --uid 10001 --gid 10001 --no-create-home kassensturz \
    && mkdir /data && chown 10001:10001 /data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py server.py receipts.py bank_providers.py datasets.py ./
COPY sample-data ./sample-data
COPY static ./static
COPY tests ./tests
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"
CMD ["python", "server.py"]
