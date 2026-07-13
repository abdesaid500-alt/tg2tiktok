FROM python:3.13-slim

WORKDIR /app

COPY . .

EXPOSE 10000

CMD python start.py