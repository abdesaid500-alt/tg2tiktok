FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ffmpeg binary so it doesn't download at startup
RUN python -c "import static_ffmpeg; static_ffmpeg.add_paths()"

COPY . .

EXPOSE 8080

CMD ["python", "start.py"]
