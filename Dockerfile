FROM python:3.13-slim

COPY . .

EXPOSE 10000

CMD python start.py