FROM ds41:csf-base
COPY . /tmp/sparkring-update/
RUN python3 -m pip install --no-deps --no-build-isolation --target /tmp/status-install /tmp/sparkring-update/status && python3 /tmp/sparkring-update/apply.py && python3 /opt/dsv41-csf/runtime.py seal && rm -rf /tmp/sparkring-update /tmp/status-install
ENTRYPOINT ["python3", "/opt/dsv41-csf/runtime.py"]
CMD ["verify"]
LABEL io.local.deepseek-upgrade="csf-sparkring-721db585"
