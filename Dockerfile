FROM python:3.11-slim

WORKDIR /app

# install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy app
COPY . .

# create data directories
RUN mkdir -p /app/data /app/db/cache

# default command runs daemon
CMD ["python", "daemon.py"]
