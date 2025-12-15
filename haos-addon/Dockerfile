ARG BUILD_FROM
FROM ${BUILD_FROM}

# install python deps
RUN apk add --no-cache python3 py3-pip py3-requests py3-beautifulsoup4

# create app directory
WORKDIR /app

# copy requirements and install
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# copy app code
COPY api.py config.py daemon.py cli.py setup_user.py ./
COPY db/ db/
COPY scoutd/ scoutd/
COPY matchd/ matchd/
COPY introd/ introd/

# create data directory
RUN mkdir -p /data/db /data/cache

# copy run script
COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
