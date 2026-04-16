FROM python:3.12-slim
WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# LLMBase 核心
COPY tools/ ./tools/
COPY llmbase.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# KWiki 定制
COPY kwiki/ ./kwiki/
COPY custom/ ./custom/
COPY startup.py ./
COPY wsgi_web.py ./
COPY wsgi_agent.py ./
COPY config.yaml .

# 前端静态文件
COPY static/dist/ ./static/dist/

# kwiki 数据库操作（需要 psycopg2）
RUN pip install --no-cache-dir psycopg2-binary

EXPOSE 5551 5552

CMD ["python", "startup.py"]
