FROM python:3-alpine

RUN adduser -D -H -u 10000 netlink

VOLUME /netlink

COPY . /netlink-src

RUN cd /netlink-src && pip3 install --no-cache-dir -r requirements-docker.txt
RUN cd /netlink-src && python3 setup.py install
RUN rm -r /netlink-src

USER netlink
WORKDIR /netlink

# Run in no-PID file mode by default
CMD ["netlink", "-n"]
