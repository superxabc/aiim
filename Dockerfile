FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8083
# 使用 main:app 作为入口（代码中应用定义在 main.py）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8083"]