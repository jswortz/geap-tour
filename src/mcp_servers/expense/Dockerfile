FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastmcp>=2.0.0
COPY . .
EXPOSE 8003
CMD ["python", "-m", "server"]
