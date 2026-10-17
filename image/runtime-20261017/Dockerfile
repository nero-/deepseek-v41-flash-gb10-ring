# syntax=docker/dockerfile:1
ARG SELECTED_IMAGE=dsv41-runtime-toolchain-parent:20261017
FROM ${SELECTED_IMAGE} AS selected
FROM eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595

# Keep the qualified CUDA compiler/runtime and switchless-aware NCCL together.
COPY --from=selected /usr/local/cuda-13.4/ /usr/local/cuda-13.4/
COPY --from=selected /opt/sparkring/toolchain/nccl/ /opt/sparkring/toolchain/nccl/
COPY --from=selected /opt/sparkring/toolchain/python/ /opt/sparkring/toolchain/python/
COPY toolchain.py toolchain.json /opt/sparkring/toolchain/
COPY external-base.py /opt/sparkring/bin/external-base.py
COPY transports/ /opt/sparkring/transports/
COPY python/ /opt/sparkring/python/
COPY composition.json candidate-encoding.py install.py /opt/sparkring/runtime-20261017/
COPY LICENSE.sparkring LICENSE.deepseek /opt/sparkring/runtime-20261017/
ENV PYTHONDONTWRITEBYTECODE=1
RUN python3 /opt/sparkring/runtime-20261017/install.py && \
    python3 /opt/sparkring/toolchain/toolchain.py seal && \
    python3 /opt/sparkring/toolchain/toolchain.py verify
ENTRYPOINT ["python3", "/opt/sparkring/toolchain/toolchain.py"]
CMD ["verify"]
