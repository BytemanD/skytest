FROM python:3.11.0-slim

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list \
    && apt update \
    && apt install -y gcc pkg-config libvirt-dev

COPY skytest-0.1.0-py3-none-any.whl /tmp
COPY skytest.template.toml /tmp

RUN python -m pip install --upgrade pip \
    && PKG=$(ls /tmp/skytest-*.whl |tail -n1) \
    && python -m pip install ${PKG} --progress-bar off

RUN mkdir -p /etc/skytest \
    && mv /tmp/skytest.template.toml /etc/skytest \
    && cp /etc/skytest/skytest.template.toml /etc/skytest/skytest.toml \
    && apt clean all \
    && pip cache purge
