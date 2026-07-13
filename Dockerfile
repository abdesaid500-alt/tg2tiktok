FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --only-binary :all: --timeout 120 -r requirements.txt

COPY . .

EXPOSE 10000

CMD python start.py