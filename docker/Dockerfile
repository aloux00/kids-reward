# 星星成长记 · 儿童成长激励系统
#
#   构建： docker compose build
#   运行： docker compose up -d
#
# 镜像里只有代码和 Python 依赖（约 200MB），数据一律不进镜像：
#   data/        数据库 + 教材 PDF（可能几百 MB）
#   uploads/     孩子头像等上传文件
#   rules.yaml   家长在网页上改的规则，会被写回，必须挂出来
# 这三样通过 docker-compose.yml 挂载，重建镜像不会碰它们。

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# tzdata 是必须的，不是可选优化：
# 容器默认 UTC，而"今天"这个日期决定了每日上限、打卡、连击的翻篇时刻。
# 不装的话，北京时间早上 8 点才换日 —— 孩子晚上 11 点做的任务会被算到第二天。
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime \
 && echo "${TZ}" > /etc/timezone \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY static ./static
COPY tools ./tools
COPY run.py seed.py rules.yaml ./

# 自检脚本也打进镜像，这样容器起来后能直接跑 docker compose exec kids python smoke_test.py。
# 必须打进去而不是临时挂：这几套脚本会用 sqlite3 直接读写 data/kids.db 做前置数据准备，
# 挂在宿主机上跑的话，脚本改的是宿主机的库、HTTP 打的是容器里的库，两边对不上，必然误报失败。
COPY smoke_test.py smoke_test_extra.py smoke_test_extra2.py smoke_test_extra3.py ./

# 默认配置留一份副本：容器里 rules.yaml 万一被清空，一条 cp 就能恢复
RUN cp rules.yaml rules.yaml.default

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
# 在 Windows 上编辑过这个脚本可能会带 CRLF，容器里会报
# "cannot execute: required file not found" 或 "/bin/sh^M: bad interpreter"，
# 报错信息完全看不出是换行符问题。统一抹掉，省得以后排查。
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
 && chmod 0755 /usr/local/bin/entrypoint.sh

# 构建指纹：记下这份镜像里烤的是哪一版代码。
# 用途很实际 —— "我明明改了代码怎么没生效" 这种问题，先看这个时间就知道
# 是代码改得不对，还是镜像压根没重建（容器跑的是镜像里的旧副本）。
#
# 位置很关键，必须同时满足两个条件：
#   1. 在所有 COPY app / COPY static 之后 —— 否则算出来的指纹是空的
#   2. 在上面 COPY entrypoint.sh 之后 —— 否则改 entrypoint 时会命中缓存，
#      镜像明明重建了、时间戳却是旧的，反而误导排查
RUN { \
      echo "built_at=$(date '+%Y-%m-%d %H:%M:%S %Z')"; \
      echo "python=$(python -V 2>&1)"; \
      echo "fingerprint=$(find app static -type f \
            \( -name '*.py' -o -name '*.js' -o -name '*.css' -o -name '*.html' \) \
            -exec md5sum {} + | LC_ALL=C sort -k2 | md5sum | cut -c1-12)"; \
    } > /app/BUILD_INFO

# 非 root 运行。uid 固定 1000，宿主机挂载目录属主要对得上（见 entrypoint 的检查）。
RUN useradd --create-home --uid 1000 --shell /bin/bash kids \
 && mkdir -p /app/data /app/uploads \
 && chown -R kids:kids /app

USER kids

EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8777/health',timeout=3).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
