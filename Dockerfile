FROM python:3.8-slim

WORKDIR /app

COPY requirements.txt .
# 容器内走国内镜像源安装依赖
RUN pip config set global.index-url http://mirrors.ustc.edu.cn/pypi/simple && \
    pip config set install.trusted-host mirrors.ustc.edu.cn && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "pipeline/app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
