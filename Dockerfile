FROM python:3.12-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --timeout 120 -r requirements.txt && yt-dlp --version

COPY . .

EXPOSE 10000

CMD python start.py