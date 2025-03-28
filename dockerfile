FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /app/data  

COPY ./bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./bot /app

VOLUME /app/data

CMD ["python", "main.py"]