FROM python:3.11-slim

WORKDIR /app

# install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy app
COPY . .

# create data directories (db files stored in /data, not /app/db)
RUN mkdir -p /data/db /data/cache

# set DB path via env
ENV DB_PATH=/data/db/connectd.db
ENV CACHE_DIR=/data/cache

# default command runs daemon
CMD ["python", "daemon.py"]
