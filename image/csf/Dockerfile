FROM ds41:csf-parent
RUN python3 -m pip install --no-cache-dir --no-deps nvidia-cutlass-dsl==4.7.1 nvidia-cutlass-dsl-libs-base==4.7.1 nvidia-cutlass-dsl-libs-core==4.7.1 nvidia-cutlass-dsl-libs-cu12==4.7.1 nvidia-cutlass-dsl-libs-cu13==4.7.1
COPY src/ /tmp/csf-src/
RUN python3 -m pip install --no-deps --no-build-isolation /tmp/csf-src && cp -a /tmp/csf-src/vllm/. /usr/local/lib/python3.12/dist-packages/vllm/ && rm -rf /tmp/csf-src
COPY runtime.py manifest.json rebind-transport.py /opt/dsv41-csf/
RUN python3 -c "import importlib.metadata as m;from pathlib import Path;p=Path(m.distribution('vllm')._path)/'METADATA';s=p.read_text();s=s.replace('Version: '+m.version('vllm'),'Version: 0.1.dev21510+g00a33e231.csf.sparkring');p.write_text(s)" && python3 /opt/dsv41-csf/rebind-transport.py && python3 /opt/dsv41-csf/runtime.py seal
ENTRYPOINT ["python3", "/opt/dsv41-csf/runtime.py"]
CMD ["verify"]
LABEL io.local.deepseek-upgrade="csf-20261004"
