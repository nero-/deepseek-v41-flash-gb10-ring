ARG BASE
FROM ${BASE}
COPY . /opt/ds41-1017-prompt/
RUN python3 /opt/ds41-1017-prompt/install.py && python3 /opt/sparkring/toolchain/toolchain.py verify
