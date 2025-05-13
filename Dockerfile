FROM python:3.9-slim

RUN apt-get update && apt-get install -y git
RUN apt-get update && apt-get install -y \
    pkg-config \
    libmariadb-dev \
    build-essential \
    mariadb-client \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY . /app

RUN pip install mysqlclient
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install git+https://github.com/doarmario/mangadex.git



EXPOSE 5000
CMD ["gunicorn", "app:create_app()", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "gevent"]
