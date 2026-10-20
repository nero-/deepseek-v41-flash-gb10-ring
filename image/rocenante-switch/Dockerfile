# syntax=docker/dockerfile:1
ARG SELECTED_IMAGE=dsv41-switch-parent:20261020
FROM ${SELECTED_IMAGE}
COPY staged/ /opt/sparkring/switched-20261020/staged/
COPY install.py ds41_switch_guard.py entrypoint.py /opt/sparkring/switched-20261020/
ENV PYTHONDONTWRITEBYTECODE=1
RUN python3 /opt/sparkring/switched-20261020/install.py && \
    python3 /opt/sparkring/toolchain/toolchain.py seal && \
    python3 /opt/sparkring/toolchain/toolchain.py verify
ENTRYPOINT ["python3", "/opt/sparkring/switched-20261020/entrypoint.py"]
CMD ["verify"]
