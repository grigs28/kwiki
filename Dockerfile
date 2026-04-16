FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# 克隆 LLMBase 源码
RUN git clone https://github.com/Hosuke/llmbase.git /tmp/llmbase \
    && cp -r /tmp/llmbase/tools /app/ \
    && cp /tmp/llmbase/llmbase.py /app/ \
    && rm -rf /tmp/llmbase

# 安装 Python 依赖
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary

# 复制 kwiki 定制代码
COPY kwiki/ ./kwiki/
COPY custom/ ./custom/
COPY startup.py .
COPY config.yaml .

# 创建数据目录
RUN mkdir -p raw wiki/_meta wiki/concepts wiki/outputs
RUN mkdir -p /root/.config/llmbase
RUN echo 'LLMBASE_API_KEY=sk-placeholder\nLLMBASE_BASE_URL=http://localhost/v1\nLLMBASE_MODEL=gpt-4o' > /root/.config/llmbase/.env

# 暴露双端口
EXPOSE 5551 5552

CMD ["python", "startup.py"]