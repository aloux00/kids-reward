# 部署到 serv00（能跑，但请先看完第一节）

## 一、先说结论：技术上可行，但不建议给孩子的日常系统用

| 项目 | 实际情况 |
|---|---|
| 系统 | FreeBSD jail（**不是 Linux**，没有 apt / systemd / Docker） |
| 资源 | 3 GB SSD、**512 MB 内存**、3 个 TCP/UDP 端口、15 个进程 |
| Python | 支持，能装 venv + pip + uvicorn，跑得动 |
| 费用 | 免费 |
| **致命条款** | **账号必须至少 90 天登录一次面板或 SSH，否则账号和数据被永久删除** |
| 服务器位置 | 波兰，从国内访问延迟不可预测 |
| SLA | 无，仅论坛支持 |

**技术上一次就跑得起来**，我们的依赖全是纯 Python，512 MB 内存足够（常驻约 80–120 MB）。

但真正的问题在最后一栏。**这是个每天都要给孩子打卡的系统**，想象一下：

> 某天孩子兴冲冲攒够星星币，攒了三个月准备兑换愿望，打开 App 发现一切都空了 ——
> 因为你半年前注册的账号，中间忘了登录一次。

这不是危言耸听，是它明文写在各项条款里的规则。**它适合自己的小 Bot、签到脚本、练手测试，
不适合承载一个孩子三个月的努力记录。**

如果你只是想找个免费环境**验证系统在公网能不能跑**，那它很合适；
如果打算长期给家里用，请看 `deploy/linux/`（Armbian）。

## 二、如果还是要试

### 0. 两个必须先知道的前提

**① 别用面板里的「Python 类型」网站，它跑不了这个项目。**

网上所有 serv00 教程都是 Flask —— 面板的 Python 类型底层是 **Phusion Passenger**，
它只认 **WSGI** 接口。而这套系统是 FastAPI，走的是 **ASGI**（uvicorn），
两者的调用签名根本不同。照着 Flask 教程写 `passenger_wsgi.py`，
得到的只会是一个 500。

正确做法是**自己起进程 + 面板建 Proxy 类型网站指向端口**，也就是下面这两节。

**② 先打开「Run your own applications」。**

面板 → **Additional Services** → 找到 *Run your own applications* → 设为 **Enabled**。

不开这一项，**你自己目录下的任何文件都加不了可执行权限**，
连虚拟环境里的 `venv/bin/python` 都跑不起来，后面每一步都会失败。

### 1. 申请端口

登录 DevilWEB 面板 → **Additional Services**（或在 SSH 里用 `devil` 命令）申请一个 TCP 端口。
免费档一共只有 3 个，注意别浪费。记下分配的端口号，比如 `12345`。

```bash
ssh 你的用户名@你的 SSH 主机
devil info                 # 看自己的资源配额
devil port list            # 看已放行端口
```

### 2. 上传代码

```bash
# 本机（Windows / Linux 都一样）
scp -r "C:/WD/code/good study/kids-reward" 你的用户名@你的SSH主机:~/kids-reward
```

或者直接在服务器上 `git clone`（serv00 免费档给 3 个 Git 仓库）。

### 3. 装依赖

```bash
cd ~/kids-reward
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -r requirements.txt
```

> FreeBSD 上的 pip 有时会把某些包拉去编译。**我们刻意只用纯 Python 依赖**
> （fastapi / uvicorn / sqlalchemy / ruamel.yaml / python-multipart），
> 正常情况下不会触发编译，几秒到一分钟装完。万一卡住，通常是某个包在拉 cffi/argon2 之类的，
> 回头检查 requirements.txt 有没有被改动。

### 4. 初始化并挂到后台

先前台跑一次，确认真的能起来（Ctrl+C 停）：

```bash
cd ~/kids-reward
source venv/bin/activate

# 随机密钥。千万别用代码里的默认值，它等于把登录令牌交给任何人
export KIDS_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
export KIDS_PORT=12345

python seed.py
python run.py --port $KIDS_PORT
```

> 注意这里**故意不加 `--lan`**：进程只听 127.0.0.1，端口不对外暴露，
> 外面一律通过后面第 5 步的 Proxy 域名进来。这是推荐姿势。

确认没问题后，把密钥和端口固化下来，省得每次 export：

```bash
cat > ~/kids-reward/kids.env <<EOF
KIDS_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
KIDS_PORT=12345
EOF
chmod 600 ~/kids-reward/kids.env
```

#### 方式 A · 纯 shell 保活（推荐，省内存）

serv00 免费档只有 **512 MB 内存、15 个进程**，pm2 光 daemon 就吃掉几十 MB，
而这个保活脚本的开销基本是 0：

```bash
cat > ~/kids-reward/keepalive.sh <<'EOF'
#!/usr/bin/env bash
# serv00 没有 systemd，靠 cron 每分钟拉一次。进程在就什么都不做。
set -u
APP=~/kids-reward
if ! pgrep -f "run.py --port" >/dev/null 2>&1; then
    cd "$APP" || exit 0
    set -a; . "$APP/kids.env"; set +a
    nohup "$APP/venv/bin/python" run.py --port "$KIDS_PORT" \
        >> "$APP/app.log" 2>&1 &
fi
EOF
chmod +x ~/kids-reward/keepalive.sh
~/kids-reward/keepalive.sh
```

然后在面板 **Cron jobs** 里加一条（也可以用 `crontab -e`）：

```
* * * * * /usr/home/你的用户名/kids-reward/keepalive.sh
```

这样进程被杀、机器重启，一分钟内都会自己回来。

#### 方式 B · pm2（内存够的话更省心）

```bash
npm install -g pm2
cd ~/kids-reward
KIDS_SECRET=$(grep KIDS_SECRET kids.env | cut -d= -f2) \
KIDS_PORT=12345 \
  pm2 start "venv/bin/python run.py --port 12345" --name kids
pm2 save
```

> `pm2 startup` 在没有 systemd 的 FreeBSD 上帮不上忙，
> 自启仍然要靠面板里的 cron `@reboot` 任务。内存紧张时直接用方式 A。

### 5. 建 Proxy 类型网站，用域名访问（推荐）

直接访问 `http://用户名.serv00.net:12345` 能用，但**带端口就没法用 HTTPS**。
正确做法是在面板里加一个 Proxy 类型的网站：

面板 → **WWW Websites** → **Add new website** → 展开 **Advanced settings**：

| 项 | 填什么 |
|---|---|
| Domain | 你的域名，或 serv00 送的 `用户名.serv00.net`（也可以用它的子域） |
| Website type | **Proxy** |
| Proxy target | **localhost** |
| Proxy port | 你申请到的那个端口，比如 `12345` |

命令行等价写法：

```bash
devil www add 你的域名 proxy localhost 12345
devil www options 你的域名 sslonly on      # 强制跳 HTTPS
```

然后去 **SSL** → **Add certificate** → **Let's Encrypt** 申请免费证书。

搞定后用 `https://你的域名` 访问，干净、加密、不带端口。

> Proxy 类型是支持 WebSocket 的，虽然这套系统目前没用上，
> 但意味着以后加实时功能也不用改部署方式。

### 6. 每天自动备份到本地（强烈建议）

免费主机的数据随时可能消失，必须有一份在自己手上。在你**自己的电脑**上放一个定时任务：

```bash
# Linux / macOS crontab，每天早上 6:10 把数据库拉回家
# 用 VACUUM INTO 取一致性快照，别直接复制运行中的 .db（WAL 模式下会拿到损坏状态）
10 6 * * * ssh 你的用户名@你的SSH主机 \
  "sqlite3 ~/kids-reward/data/kids.db \"VACUUM INTO '/tmp/kids-today.db';\"" && \
  rsync -az 你的用户名@你的SSH主机:/tmp/kids-today.db \
        /你家目录/star-kids-backup/$(date +\%F).db
```

Windows 的话可以用任务计划程序 + WinSCP 的命令行，或直接手动定期下载。

**在服务端也可以留一份本地快照**（FreeBSD 自带 `sqlite3`）：

```bash
# 同目录的 backup.sh 会跳过教材 PDF，不会撑爆 3 GB 配额
cp ~/kids-reward/deploy/serv00/backup.sh ~/kids-reward/backup.sh
APP_DIR=~/kids-reward KEEP_DAYS=7 bash ~/kids-reward/backup.sh
# 面板 Cron jobs 里加一条：每天 03:17
17 3 * * * APP_DIR=/usr/home/你的用户名/kids-reward /usr/home/你的用户名/kids-reward/backup.sh
```

但要记得**同一台机器上的备份不算备份**，仍然要把压缩包同步走。

### 7. 90 天保号提醒

在你的日历里设一个**每 60 天重复**的提醒，内容是"去 serv00 面板登录一下"。

不推荐用社区流传的自动保活脚本去模拟登录——那既违反其使用条款，
也把孩子的数据押在一个随时可能被封停的账号上。

## 三、必须做的安全设置

因为是公网可访问，至少做这些：

1. **改掉所有默认口令**（`dad` / `mom` / 孩子的 `1234`），家长账号建议 8 位以上
2. **设置一个强 `KIDS_SECRET`** 并写进 `kids.env`（权限 600）
3. 别在论坛或任何公开场合贴你的访问地址
4. 面板里给绑定域名开免费 SSL 并打开 `sslonly`，**不要用 http 明文长期使用**
5. 教材 PDF 是磁盘大头（小学全套主科约 450 MB），3 GB 配额下别贪多

## 四、常见问题

**面板里选了 Python 类型，页面 500 或打不开。**
看第 2 节第 0 条：Passenger 只支持 WSGI，这个项目是 ASGI。
删掉那个网站，改用 Proxy 类型（`devil www del 域名` 再 `devil www add 域名 proxy localhost 端口`）。

**venv 里的 python 报 Permission denied。**
Additional Services 里的 *Run your own applications* 没开，回去打开。

**进程莫名消失？** 多半是内存超了 512 MB，表现为日志里出现 `Killed`。
先看 `tail -50 ~/kids-reward/app.log`。
思路是别上 pm2（省下 daemon 的几十 MB）、教材少装几本，
或者给 pm2 加 `--max-memory-restart 300M` 让它自己重启而不是被系统杀。

**挂了却没自动回来？** 检查 cron 那条有没有真的生效：

```bash
crontab -l | grep keepalive
tail -5 ~/kids-reward/app.log
```

**端口连不上？** 确认用的是面板分配的那个端口，且数量没超过 3 个。
另外 Proxy 站点指向的端口必须和你实际监听的一致。

**中文乱码？** FreeBSD 的 locale 默认是 C，执行 python 前先：

```bash
export PYTHONIOENCODING=utf-8
export LANG=C.UTF-8
```

**pip 装不上？** 试试加 `--no-cache-dir`，或者换个 pypi 源。
