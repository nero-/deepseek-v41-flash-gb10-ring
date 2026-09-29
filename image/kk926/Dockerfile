FROM dsv41-pinned-base:kk926
LABEL io.local.deepseek.correction="compressor-ring-kk926" \
      io.local.deepseek.upstream="7b935cb78a3f1f256b04006e82504a651685f72d" \
      io.local.deepseek.base="sha256:8e4de5f05f0287c4d0326f3a6ed5d25d3248ec4d482f369308a08a36a2f893bf"
COPY . /opt/kk926/
RUN python3 /opt/kk926/install.py
