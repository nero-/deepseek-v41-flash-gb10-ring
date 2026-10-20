# syntax=docker/dockerfile:1
ARG SELECTED_IMAGE=ds41-rocenante-switch:20261020-v2
FROM ${SELECTED_IMAGE}
COPY staged/ /opt/sparkring/moe-20261020/staged/
COPY install.py /opt/sparkring/moe-20261020/
RUN python3 /opt/sparkring/moe-20261020/install.py && \
    python3 /opt/sparkring/toolchain/toolchain.py seal && \
    python3 /opt/sparkring/toolchain/toolchain.py verify
