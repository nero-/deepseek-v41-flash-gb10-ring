ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY . /opt/ds41-1017-parser
RUN python3 /opt/ds41-1017-parser/install.py && \
    python3 /opt/sparkring/toolchain/toolchain.py verify && \
    python3 -m pip install --no-index --no-deps --target /opt/ds41-1017-parser/testdeps /opt/ds41-1017-parser/wheels/*.whl && \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=/opt/ds41-1017-parser/testdeps:/opt/ds41-1017-parser python3 -m pytest -q --disable-warnings \
      /opt/ds41-1017-parser/tests/parser/engine/test_deepseek_v4.py \
      /opt/ds41-1017-parser/tests/parser/engine/test_deepseek_v41.py
