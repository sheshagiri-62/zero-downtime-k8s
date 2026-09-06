FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ARG FAIL_RATE_DEFAULT=0.0
ARG LATENCY_DEFAULT=0
ENV FAIL_RATE=${FAIL_RATE_DEFAULT}
ENV EXTRA_LATENCY_MS=${LATENCY_DEFAULT}

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
