# 星星成长记 · Docker 部署

## 一、先说结论

**能，而且这套系统天生适合容器化。** 单进程、SQLite 单文件、运行时零外网、没有 Redis / MQ / 反向依赖，
换成 Docker 之后没有一处需要改架构。

真正需要想清楚的只有一件事：**哪些东西必须留在容器外面**。

| 打进镜像（一次构建，长期不变） | 挂载到宿主机（天天在变，绝不能进镜像） |
|---|---|
| `app/` 后端代码 | `data/` 数据库 + 教材 PDF + 索引 |
| `static/` 前端文件 | `uploads/` 头像等上传文件 |
| `requirements.txt` 里的依赖 | `rules.yaml` 家长在网页上改的规则 |
| `rules.yaml` 的一份默认值副本 | |

镜像本身约 200MB。`data/` 是你自己的资产（现在 25 本教材约 489MB），
**重建镜像、升级代码、换台服务器，都不会碰它。**

> 为什么不把 `data/` 打进镜像：SQLite 是单文件数据库，写操作会改文件。
> 打进镜像等于"每次启动都回到出厂状态"，孩子的星星币记录全部蒸发。
> 这是容器化这类应用最容易踩的坑，本项目用挂载卷绕开了它。

**日常只需要记住一个入口**：双击 `start-docker.bat`。
它默认用 dev 编排（源码挂载 + 自动重载），改完代码自动生效，不用 rebuild、不用重启。
改了什么、对应什么行为，全在第三节那张表里。

---

## 二、三分钟上手

### 前提

宿主机装好 Docker Engine 24+ 与 Compose 插件（`docker compose version` 有输出即可）。

### 国内网络：基础镜像拉不下来怎么办

`docker compose build` 的第一步是 `FROM python:3.12-slim`，它要去 Docker Hub。
国内直连经常超时，报错长这样：

```
failed to solve: python:3.12-slim: failed to resolve source metadata for
docker.io/library/python:3.12-slim: ... dial tcp 31.13.94.37:443: connectex:
A connection attempt failed because the connected party did not properly respond
```

**办法一（推荐，永久生效）：配镜像加速器**

Docker Desktop → Settings → Docker Engine，在 JSON 里加一项 `registry-mirrors`，
然后 Apply & Restart：

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"],
  "builder": { "gc": { "defaultKeepStorage": "20GB", "enabled": true } }
}
```

Linux 上是直接改 `/etc/docker/daemon.json`，然后 `sudo systemctl restart docker`。
改完用 `docker info | grep -A2 "Registry Mirrors"` 确认生效。

> 加速器地址会随政策变化，2026 年实测可用的有 `https://docker.m.daocloud.io`。
> 不确定的话先探一下：`curl -sI https://镜像地址/v2/` 返回 **401 就是健康的**
> （registry v2 的认证挑战），返回 000 说明这个地址已经废了。

**办法二（临时，不用重启 Docker）：手动拉 + 打本地 tag**

不想动 Docker 配置时用这招，`FROM` 会直接命中本地镜像：

```bash
docker pull docker.m.daocloud.io/library/python:3.12-slim
docker tag  docker.m.daocloud.io/library/python:3.12-slim  python:3.12-slim
docker compose build
```

### 步骤

**在 Windows 本机上用，直接双击 `start-docker.bat`**。它会依次做四件事：
等 Docker Desktop 起来 → 增量构建 → 等健康检查通过 → 打开浏览器。
默认就是 dev 模式（源码挂载 + 自动重载），改代码自动生效，细节见第三节。

加参数 `-prod` 则用生产编排启动（自包含镜像、不挂源码），用来预演服务器上的行为。

**在 Linux 服务器上，手动跑：**

```bash
cd kids-reward

# 1. 确认规则文件存在。这一步别省 ——
#    文件不存在时 Docker 会把它建成一个空目录，服务直接起不来（见第六节坑 1）
touch rules.yaml

# 2. 构建并启动
docker compose up -d --build

# 3. 看日志，等它打印出访问地址
docker compose logs -f
```

浏览器打开 `http://服务器IP:8777` 即可。默认账号 `dad` / `1234`。

**首次启动会自动做两件事**：`rules.yaml` 若为空则从镜像内的默认配置补一份；
`data/kids.db` 不存在则写入演示数据。已有数据时一律跳过，绝不覆盖。

### 服务器上：代码归 git，数据放仓库外（推荐）

上面那种"数据就在项目目录里"的写法，本机和单机部署都没问题。
但如果你打算**用 git 管理代码**，就要把数据挪出仓库目录 —— 否则家长端每改一次规则、
数据库每写一次，`git status` 都是脏的，`git pull` 迟早冲突。

```bash
# 1. 数据目录（仓库外面，git 完全不管）
sudo mkdir -p /srv/star-kids/data /srv/star-kids/uploads
sudo touch   /srv/star-kids/rules.yaml
sudo chown -R 1000:1000 /srv/star-kids

# 2. 代码（git clone 下来的只读副本）
sudo git clone https://github.com/<你的用户名>/kids-reward.git /opt/kids-reward
cd /opt/kids-reward

# 3. 用 .env 把数据指过去（compose 会自动读同目录的 .env）
cp .env.example .env && nano .env
#   KIDS_HOST_DATA=/srv/star-kids/data
#   KIDS_HOST_UPLOADS=/srv/star-kids/uploads
#   KIDS_HOST_RULES=/srv/star-kids/rules.yaml

# 4. 起服务
sudo docker compose up -d --build
```

以后更新就三行：

```bash
cd /opt/kids-reward
git pull
sudo docker compose up -d --build
```

`data/`、`uploads/`、`rules.yaml` 都在 `/srv/star-kids/`，重建镜像碰不到它们。
完整的建仓、提交、回滚流程见 **`docs/GIT.md`**。

> 想跑 ARM 板（树莓派、N1、玩客云）：`python:3.12-slim` 有 arm64 版本，
> 直接 `docker compose build` 会拉到对应的架构，不用交叉编译。
> 32 位 armv7 系统的镜像支持要现查，先跑这句确认：
> `docker manifest inspect python:3.12-slim | grep architecture`

### 常用命令

`start-docker.bat` 用的是 dev 编排，命令要带上两个 `-f` 才对应得上。
嫌长可以先设个别名（PowerShell）：

```powershell
function kc { docker compose -f docker-compose.yml -f docker-compose.dev.yml @args }
```

| 做什么 | 命令 |
|---|---|
| 启动 / 重启（本机 dev） | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` |
| 停止（保留数据） | `docker compose -f docker-compose.yml -f docker-compose.dev.yml down` |
| 看日志 | `docker compose logs -f --tail 100`（看日志不需要带 `-f`） |
| 进容器排查 | `docker compose exec kids sh` |
| 看健康状态 | `docker compose ps`（`STATUS` 里有 `healthy`） |
| 查镜像里的代码版本 | `docker compose exec kids cat /app/BUILD_INFO` |
| 挂载性能体检 | `docker compose exec kids python tools/probe_mount.py` |
| 备份 | 见第四节，直接操作宿主机目录 |

---

## 三、改完代码怎么自动生效

这是整套 Docker 方案里唯一需要你做个选择的地方，先给结论：

- **本机日常使用 → 双击 `start-docker.bat`。它默认就是 dev 模式，改代码完全自动，零操作。**
- **服务器正式部署 → 用生产编排，改完手动跑一条命令。**

### 三种改动，三种行为

dev 模式下源码目录是**挂进容器**的，容器读的永远是你磁盘上那一份文件，
不存在"镜像里还躺着旧副本"这种问题：

| 你改了什么 | 会发生什么 | 你需要做什么 |
|---|---|---|
| 家长端网页里改规则 / 品牌 / 科目 | 写回 `rules.yaml`，立即生效 | 什么都不用做 |
| `static/` 前端 css / js | 挂载目录，服务端立刻读到 | **刷新浏览器** |
| `app/` 后端 Python | 容器内 uvicorn 检测到变化，1 秒内重载 | 什么都不用做，刷新浏览器 |
| `requirements.txt` | 依赖装在镜像里，挂载覆盖不了 | 重新跑一次 `start-docker.bat` |
| `docker/Dockerfile` | 同上 | 重新跑一次 `start-docker.bat` |
| `docker/entrypoint.sh` | 同上 | 重新跑一次 `start-docker.bat` |

注意第三行：那是**进程内重载**，不是重启容器。容器不重建、数据库连接不断，
孩子正在做题的页面不会白屏。

### 为什么不用"文件监视 + 自动 rebuild"那一套

看起来更聪明的做法是起一个后台进程盯着文件，一变就自动 `docker build`。
实际做下来有两个硬伤：

1. **它依赖那个进程活着。** 关机重启、误关窗口、Docker Desktop 重启，
   监视进程就没了，而你不会收到任何提示 —— 改代码不再生效，但也不报错。
   这类"静默失效"是最难发现的。
2. **改一行 CSS 也走一遍镜像构建。** 几十秒起步，还会攒一堆中间镜像。

dev 编排把监视放在**容器内部**（uvicorn 的 `--reload`），只要容器活着就一直在盯，
配合源码挂载，改完即生效。没有第二个进程需要你维护，也就没有它会悄悄死掉的可能。

### 唯一需要重建的情况

依赖装在镜像里，源码挂载覆盖不了它，所以改下面这几样必须重建：

```
requirements.txt
docker/Dockerfile
docker/entrypoint.sh
```

重新跑一次 `start-docker.bat` 就行，它固定带 `--build`。增量构建会命中依赖层缓存：

| 场景 | 耗时 |
|---|---|
| 第一次构建（下载基础镜像 + 装依赖） | 2～4 分钟 |
| 之后只改了代码，重建 | **3～8 秒** |
| 改了 `requirements.txt` | 30～90 秒（只有依赖层失效） |

### 服务器上怎么更新

服务器跑的是生产编排（自包含镜像，不挂源码），更新就是重跑一次构建：

```bash
git pull                      # 或者 scp 把改动传上去
docker compose up -d --build  # 增量构建，通常几秒
```

容器会重建，但 `data/`、`uploads/`、`rules.yaml` 都在宿主机卷里，数据不受影响。
服务中断约 2～3 秒。

> 如果 `git pull` 报 "Your local changes would be overwritten"，
> 说明 `rules.yaml`（或 `data/`）还躺在仓库目录里被家长端写过了。
> 按上一节把数据挪到 `/srv/star-kids/` 就一劳永逸了。
> 仓库的建、提交、回滚完整流程见 **`docs/GIT.md`**。

> 想让服务器也全自动，可以把这两条挂进 CI（GitHub Actions）或 cron。
> 家庭自用没必要 —— 你又不是每天改代码，手动一条命令更可控。

### 生产镜像下临时改代码（可选）

如果你正跑着生产编排，只想验证一个小改动、不想切模式，可以用 Compose 官方的 watch：

```bash
docker compose watch
```

它按改动类型分流：`static/` 只同步不重启，`app/` 同步并重启，改依赖则自动重建。
规则写在 `docker-compose.yml` 的 `develop.watch` 里。

代价是**需要一个终端一直开着**，关掉就失效。所以它适合临时验证，不适合日常开发。

### Docker 让你的哪些事变简单了

- **不用管 Python 版本**。宿主机是 3.9 还是 3.13 都无所谓，容器里固定 3.12。
- **不用管依赖冲突**。`pip install` 装到全局把事情搞坏的情况不会再发生。
- **迁移 = 拷三个东西**。`data/`、`uploads/`、`rules.yaml`，新机器上 `docker compose up -d` 就恢复了。
- **回滚 = 换 tag**。`docker compose down && docker compose up -d` 指回旧镜像，几秒钟。
- **环境不会漂**。系统升级、误删文件、某个 Python 包升了大版本，都影响不到容器内部。

### Docker 让你多了哪些事

- 多一层概念（镜像 / 容器 / 卷 / 端口映射），出问题时要在宿主机和容器之间来回看。
- 日志要去 `docker compose logs` 看，文件不在手边。
- 挂载权限、换行符、时区这些容器特有的坑，第一次都会遇到（第六节全列了，配置里已经兜住）。
- 磁盘会多占一份镜像空间（约 200MB～1GB，取决于旧镜像保留几个）。

**一句话总结**：本机双击 `start-docker.bat`，改代码自动生效，和裸机体验一样，
换来的是环境不会坏、迁移不用重装。服务器上改完重跑一次构建，几秒钟的事。

---

## 四、数据在哪、怎么备份、怎么恢复

### 三个卷，都在项目目录里

```
kids-reward/
├── data/            ← 数据库 + 教材 PDF + 索引   必须备份
├── uploads/         ← 头像等上传文件            必须备份
└── rules.yaml       ← 规则配置                  必须备份
```

挂载方式是 `./data:/app/data` 这种**宿主机目录直挂**，不是 Docker 托管的命名卷。
好处是：数据就摆在你能 `ls` 看、能用 rsync 拉走、能直接 `cp` 备份的地方，
不会藏在 `/var/lib/docker/volumes/` 里。

### 备份（在宿主机跑，不经过容器）

**方式 A · 停机打包（最稳）**

```bash
docker compose stop
tar czf "backup-$(date +%F).tar.gz" data uploads rules.yaml
docker compose start
```

`data/` 里现在有 25 本教材约 489MB，包会偏大。教材 PDF 随时能用
`tools/fetch_textbooks.py` 重新下载，想省空间就排除掉：

```bash
tar czf "backup-$(date +%F).tar.gz" \
    --exclude='data/textbooks/*.pdf' data uploads rules.yaml
```

**方式 B · 不停机（只备数据库）**

SQLite 跑在 WAL 模式，直接 `cp kids.db` 可能拿到半截事务。用 `VACUUM INTO`
做一致性快照 —— 这正是 Windows 上 `start.py` 备份功能用的同一个机制：

```bash
docker compose exec kids python -c \
  "import sqlite3;c=sqlite3.connect('file:/app/data/kids.db?mode=ro',uri=True);c.execute('VACUUM INTO ?',('/app/data/_snap.db',));c.close()"
mv data/_snap.db "kids-$(date +%F).db"
```

**方式 C · 增量同步到别处**

```bash
rsync -a --delete data/ uploads/ rules.yaml /path/to/another/disk/
```

同样建议先 `stop`，或者只同步方式 B 产出的快照。

### 恢复

```bash
docker compose down
tar xzf backup-2026-11-02.tar.gz      # 覆盖 data/ uploads/ rules.yaml
docker compose up -d
```

---

## 五、从裸机迁到 Docker

**不需要导出导入，直接把现有目录指过去就行。**

因为挂载路径和裸机布局完全一致（`./data` → `/app/data`），所以：

```bash
# 假设旧的裸机部署在 /opt/kids-reward，新的 Docker 项目在 /opt/kids-docker
cp -a /opt/kids-reward/data        /opt/kids-docker/
cp -a /opt/kids-reward/uploads     /opt/kids-docker/
cp    /opt/kids-reward/rules.yaml  /opt/kids-docker/
cd /opt/kids-docker && docker compose up -d
```

启动时会检测到 `data/kids.db` 已存在，跳过演示数据初始化，直接接着用。
孩子的星星币、打卡记录、教材书架、错题本，全部原样在位。

> 注意：两个服务不要同时跑，会抢同一个 SQLite 文件。先停旧的再起新的。

---

## 六、六个坑（配置里已经兜住，遇到时知道在说什么）

### 坑 1 · `rules.yaml` 变成了目录

**现象**：容器起不来，日志里报 `IsADirectoryError` 或 `是个目录，不是文件`。

**原因**：`docker compose` 挂载单文件时，如果宿主机上这个文件**不存在**，
Docker 不会报错，而是默默建一个同名的空目录。

**修复**（entrypoint 已经会拦下并打印这段）：

```bash
touch rules.yaml
docker compose down && docker compose up -d
```

### 坑 2 · 目录权限对不上

**现象**：日志报 `unable to open database file`，或 `目录 /app/data 不可写`。

**原因**：容器内以非 root 的 `kids`（uid 1000）运行。宿主机上的 `data/` 如果是 root
创建或拷贝过来的，属主不对，容器就写不进 SQLite 文件。

**修复**：

```bash
sudo chown -R 1000:1000 data uploads
sudo chown 1000:1000 rules.yaml
```

`rules.yaml` 也要改：家长在网页上保存规则会写回这个文件，只读就会保存失败。

### 坑 3 · 时间和"今天"对不上

**现象**：孩子晚上 11 点做的任务，被算到了第二天；每日上限在早上 8 点才重置。

**原因**：容器默认 UTC。而"今天"这个日期决定了每日上限、连续打卡、每日任务刷新。

**处理**：镜像里已经装了 `tzdata` 并设 `TZ=Asia/Shanghai`，compose 里也写了。
自己改配置时别把这两行删掉。

### 坑 4 · 端口冲突

**现象**：`port is already allocated`。

**处理**：改宿主机端口，不动容器内端口：

```bash
KIDS_HOST_PORT=9000 docker compose up -d
```

### 坑 5 · 把 `data/` 放在网络盘上

**现象**：偶尔出现 `database is locked`，或 `kids.db-wal` 损坏。

**原因**：SQLite 的 WAL 依赖本地文件系统的锁语义。NFS / SMB / 某些云盘不保证，
挂在上面跑迟早出事。**数据目录必须是本地磁盘。**

拿不准的话，容器里跑一下这个就清楚了 —— 它会报出挂载类型、吞吐、fsync 延迟，
以及最关键的「SQLite WAL 并发写锁能不能用」：

```bash
docker compose exec kids python tools/probe_mount.py
```

结论里会直接告诉你该不该把 `data/` 换成 Docker 命名卷。
在 Windows / macOS 上跑 Docker 时尤其值得测一次：那上面宿主机目录不是真的
"直接"挂进来的（Windows 走 9p，macOS 走 virtiofs），锁语义不保证完整。

### 坑 6 · 生产环境误用 `--reload`

dev 模式的两个进程（reloader + worker）会常驻轮询文件变化。对家庭自用完全无所谓
（实测内存约 100MB、CPU 基本为 0），但有两件事要知道：

1. **代码有语法错误时它会崩溃循环**。改崩了立刻就知道（页面打不开、日志刷错），
   这是好事；但你得改回来才能恢复。生产模式也是同样的错误，只是不会反复重试。
2. **每次保存会重启 worker，正在处理的请求会断**。孩子点提交的那一瞬间如果你正好保存了代码，
   那一次请求会失败，重试即可。

所以：**自己用 dev 模式没问题；服务器上给别人用，走生产编排。**

---

## 六半、构建指纹：怀疑"改了没生效"时先看这个

每次构建，镜像里会写一个 `/app/BUILD_INFO`：

```
built_at=2026-11-03 09:35:09 CST
python=Python 3.12.16
fingerprint=ca3c0f73c896
```

容器启动时会把它打印在日志第一屏。它的用法很直接：

| 现象 | 含义 |
|---|---|
| `built_at` 没变 | 镜像没重建过，容器跑的就是旧版本 |
| `built_at` 变了、`fingerprint` 没变 | 镜像重建了，但 `app/`、`static/` 一个字都没改 |
| `fingerprint` 也变了 | 代码确实换了一版 |

随手查：

```bash
docker compose exec kids cat /app/BUILD_INFO
```

---

## 七、放到反向代理后面

用 nginx / Caddy / Cloudflare Tunnel 转发到 `127.0.0.1:8777` 时，
**必须**打开反代模式：

```bash
KIDS_PROXY=1 docker compose up -d
```

或者在项目目录建一个 `.env`：

```ini
KIDS_HOST_PORT=8777
KIDS_PROXY=1
```

不打开的话，所有访客的 IP 都会被记成 `127.0.0.1`，
登录失败限流会按同一个 IP 累加 —— 一个人在手机上输错几次，全家都被锁在门外。

nginx 的配置参考 `deploy/linux/` 里的片段，隧道方式见 `deploy/cloudflare/`。

---

## 八、什么时候别用 Docker

诚实说几种情况，这几种下 Docker 是负担不是帮手：

| 情况 | 为什么 | 更好的选择 |
|---|---|---|
| **内存 8GB 以下的 Windows 机器** | Docker Desktop 的 WSL2 后端本身要吃 1～2GB，再跑容器，孩子用平板时会明显卡 | 直接双击 `start.bat`，见 [`DEPLOY.md`](../../DEPLOY.md) |
| **serv00 之类的免费虚拟主机** | 那是 FreeBSD，没有 Docker 可用 | 用 [`deploy/serv00/`](../serv00/) 的自起进程方案 |
| **机器常年不开机，只在周末用** | Docker Desktop 每次开机要几十秒才就绪，体验不如裸机 | 裸机 + 开机自启 |

反过来说，**16GB 内存的 Windows 本机完全可以用 Docker**：实测容器只占 67MB 内存，
构建好的镜像 265MB，`start-docker.bat` 一键起停。

反过来，这些情况 Docker 明显更合适：

- 部署到 AWS / 阿里云 / 腾讯云的 Linux 服务器（[`deploy/aws/`](../aws/) 里的 Step 1～3 可以全部跳过）
- 家里有一台专门的 Linux 小主机，但嫌配环境麻烦
- 想同时留一份"随时能回滚的旧版本"

---

## 九、文件清单

| 文件 | 作用 |
|---|---|
| `start-docker.bat` | **本机唯一入口**。等引擎 → 增量构建 → 等健康 → 开浏览器。默认 dev 模式，`-prod` 切生产 |
| `docker/Dockerfile` | 镜像定义。包含时区、非 root 用户、健康检查、CRLF 清理、构建指纹 |
| `docker/entrypoint.sh` | 启动脚本。兜挂载坑、首次初始化、打印构建版本、参数透传 |
| `docker-compose.yml` | 生产编排。三个数据卷 + 端口 + 日志轮转 + `develop.watch` 规则 |
| `docker-compose.dev.yml` | dev 叠加层。源码挂载 + `KIDS_RELOAD=1`（走同一条 entrypoint，不跳过检查） |
| `tools/probe_mount.py` | 挂载体检。报出文件系统类型、吞吐、fsync 延迟、SQLite WAL 锁是否可用 |
| `.dockerignore` | 把 `data/`、`backups/`、`uploads/` 挡在构建上下文之外（这几个可能几百 MB，且含真实数据）。注意 `smoke_test*.py` **不能**挡，它们要在容器内跑体检 |

> 脚本一律用英文提示。`.bat` 文件如果是 UTF-8 中文，cmd 会按本地 ANSI 代码页解析，
> 遇到全角标点就会把一行切成几条垃圾命令 —— 这个坑踩过一次，别再改回中文。

---

## 十、自检

**先看容器本身活没活**

```bash
curl -s http://127.0.0.1:8777/health     # 期望 {"ok":true}
docker compose ps                        # STATUS 里应出现 (healthy)
docker compose logs --tail 50            # 有没有报错
```

Dockerfile 里带了 `HEALTHCHECK`，每 30 秒在容器内部请求一次 `/health`，
连续 3 次失败会标记 `unhealthy` —— 这样端口通不通、进程死没死，一眼就能看出来。

**再跑完整功能体检（216 项）**

脚本已经打进镜像，直接跑：

```bash
docker compose exec kids python smoke_test.py
docker compose exec kids python smoke_test_extra.py
docker compose exec kids python smoke_test_extra2.py
docker compose exec kids python smoke_test_extra3.py   # 教材功能，需库里已有教材
```

**两个必须知道的前提**，不知道就会看到莫名其妙的失败：

**① 必须在容器内跑，不能在宿主机跑。**

这几套脚本里有不少用例是绕过 HTTP、直接用 `sqlite3` 读写 `data/kids.db` 来
准备数据的（比走 API 造数据快得多）。脚本里的路径是相对路径 `data/kids.db`，
在容器里解析成 `/app/data/kids.db`。

如果你在**宿主机**跑脚本、让它去打容器的端口，就会出现：
HTTP 打到容器里的库，而 `sql()` 改的是宿主机上另一个库 —— 两边对不上。
症状是类似「这块地里已经种了东西」「今天的识字闯关次数用完啦」这种
**看起来像业务逻辑 bug、其实只是状态错位**的失败。

> 用生产编排（bind mount）时宿主机和容器看到的是同一个文件，从宿主机跑也能过；
> 但只要数据放在 Docker 命名卷里（比如你在服务器上改成了 `kids-data:/app/data`），
> 就必须进容器跑。所以统一在容器里跑最省事。

**② 每套之前要复位，因为有用例依赖"今天还没做过"。**

系统有每日上限：番茄钟每天 4 次、喂食每天 3 次、识字闯关每天若干次。
脚本里对这些用例的断言是「第一次做应该成功」，跑第二遍就会被限额挡住。
所以每套之间要：

```bash
docker compose exec kids python seed.py --reset
docker compose restart kids          # 重置会重建库文件，必须重启让服务重新打开
```

项目里的 `start.py` 选「运行体检」就是按这个流程跑的（每套前自动复位）。

> 体检会往库里写测试记录，所以**别在存着真实数据的库上直接跑**。
> 先备份（第四节），或者像上面那样跑完就 `--reset`。
