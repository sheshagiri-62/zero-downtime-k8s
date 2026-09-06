FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN apk add --no-cache libpq \
    && apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY src/ ./src/
COPY static/ ./static/

ARG FAIL_RATE_DEFAULT=0.0
ARG LATENCY_DEFAULT=0
ENV FAIL_RATE=${FAIL_RATE_DEFAULT}
ENV EXTRA_LATENCY_MS=${LATENCY_DEFAULT}

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
