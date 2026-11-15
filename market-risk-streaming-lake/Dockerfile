FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[kafka]"

ENTRYPOINT ["risk-lake"]
CMD ["demo", "--bus", "kafka", "--bootstrap-servers", "broker:19092", "--lake", "/lake"]
