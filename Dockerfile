FROM python:3.13-slim

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 10000

CMD python start.py