FROM python:3.13-slim
COPY . .
EXPOSE 10000
CMD python -m pip install --no-cache-dir -r requirements.txt && python start.py