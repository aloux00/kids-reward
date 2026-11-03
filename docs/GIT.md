# 代码版本管理 · Git + GitHub

这份文档回答两件事：**改动怎么提交到 GitHub**、**服务器怎么从 GitHub 拿到更新**。
不需要你懂 git 的全部，日常只会用到四条命令。

---

## 零、一句话结论

```
Windows 上改代码 → git commit → git push
                                    ↓
Linux 服务器 → git pull → docker compose up -d --build   （约 5~30 秒）
```

**仓库里只有代码，约 5 MB。数据（484 MB 教材 + 数据库 + 孩子的照片）永远不进仓库。**
这条规矩定下来之后，git 用起来就没有任何心理负担了。

---

## 一、仓库里有什么、没有什么

`.gitignore` 已经按下面这张表配置好了，你不需要每次自己挑文件。

| 内容 | 进仓库 | 为什么 |
|---|---|---|
| `app/`、`static/`、`run.py`、`seed.py` | ✅ | 代码本身 |
| `docker/`、`docker-compose*.yml`、`requirements.txt` | ✅ | 部署定义。**这是"能一键重建"的全部依赖** |
| `deploy/`、`docs/`、`*.md` | ✅ | 部署脚本和说明。换台机器照着做就行 |
| `smoke_test*.py`、`tools/` | ✅ | 回归测试和运维小工具，属于代码 |
| `rules.yaml` | ✅ | 应用的默认配置。没有它全新 clone 下来起不来 |
| `data/`（数据库 + 484 MB 教材） | ❌ | 运行期数据。进了仓库，git 会把每一版教材都存下来，仓库迅速涨到几个 GB |
| `uploads/`（孩子上传的照片） | ❌ | 同上，而且是隐私数据 |
| `backups/` | ❌ | 备份的意义是"放在另一台设备上"，不是放回仓库 |
| `.env` | ❌ | 只对某台机器成立的路径/端口。模板 `.env.example` 才提交 |

> 判断标准只有一条：**换一台机器重新 clone 之后，它是不是应该自动重新生成？**
> 是 → 不进仓库；不是 → 进仓库。

---

## 二、第一次建仓（只做一次）

### 1. 本地初始化

在 `kids-reward` 目录里执行（注意是 **这个目录**，不是它的上一层）：

```bash
git init -b main
git add .
git status            # 关键一步：确认列表里没有 data/ uploads/ backups/
git commit -m "chore: 初始化仓库，纳入代码与部署脚本"
```

`git status` 那一步别省。如果看到 `data/` 下面的文件，说明 `.gitignore` 没生效，
**这时候停下来**——一旦提交进去，后面很难彻底清掉（见第六节坑 1）。

### 2. 在 GitHub 建一个空仓库

网页上操作：<https://github.com/new>

- Repository name：`kids-reward`
- 选 **Private**（私有）。这套系统里有孩子的名字、积分规则，没必要公开
- **不要**勾 "Add a README file"、**.gitignore**、**license**

勾了会生成一个提交，和本地首次提交撞车，push 时会报
`Updates were rejected because the remote contains work that you do not have locally`。

### 3. 关联并推送

```bash
# 把 <你的用户名> 换成自己的
git remote add origin https://github.com/<你的用户名>/kids-reward.git
git push -u origin main
```

第一次 push 会弹出一个浏览器窗口让你登录 GitHub（Windows 上的 Git Credential Manager），
授权一次之后就记住了，以后不再问。

> GitHub 早就不支持账号密码推送了，走的是浏览器授权或个人访问令牌（PAT）。
> 弹窗里选 "Sign in with your browser" 最省事。

### 4. 提交身份（如果 git 抱怨不知道你是谁）

```bash
git config --global user.name  "你的名字"
git config --global user.email "你的邮箱"
```

想隐藏真实邮箱的话，用 GitHub 给的匿名地址（在 Settings → Emails 里能看到）：
`12345678+<用户名>@users.noreply.github.com`。

---

## 三、日常改动怎么提交（天天用的就这四条）

```bash
git status -s                  # ① 我改了哪些文件
git diff                       # ② 具体改了什么（确认没把调试代码提交上去）
git add app static             # ③ 挑要提交的（也可以 git add -A 全都要）
git commit -m "fix(打卡): 修复跨零点重复计数"
git push                       # ④ 推到 GitHub
```

### 提交信息怎么写

不要求多规范，但**别写 "update"、"修改"**——三个月后你自己也看不懂。
建议 `<类型>(<范围>): <做了什么>`：

| 类型 | 用在 |
|---|---|
| `feat` | 新功能，比如"新增愿望截止日期" |
| `fix` | 修 bug |
| `style` | 只动样式、文案 |
| `refactor` | 改结构但行为不变 |
| `docs` | 文档 |
| `chore` | 依赖、脚本、杂项 |

例子：

```
feat(教材): 书架支持按科目筛选
fix(积分): 撤销奖励时没有回滚账本
docs(deploy): 补充 Linux 服务器 git 部署流程
```

### 什么时候提交

**一个能独立说清楚的小改动 = 一次提交。** 不要攒三天再一起提交——
真出问题时，`git log` 里一行行看得懂，才能准确定位、精确回滚。

---

## 四、服务器上怎么拿到更新

### 路线 A · Docker（推荐）

核心是**代码和数据分开放**，这样 `git pull` 永远不会跟运行中的写入打架：

```
/opt/kids-reward/          ← git clone 下来的代码，只读不写
└── docker-compose.yml

/srv/star-kids/            ← 数据，git 完全不管
├── data/                    数据库 + 教材
├── uploads/                 孩子上传的照片
└── rules.yaml               家长端会写回的文件
```

#### 首次部署

```bash
# 1. 数据目录先建好（Docker 的坑：宿主机路径不存在时会建成目录，rules.yaml 就废了）
sudo mkdir -p /srv/star-kids/data /srv/star-kids/uploads
sudo touch   /srv/star-kids/rules.yaml
sudo chown -R 1000:1000 /srv/star-kids

# 2. 拉代码
sudo git clone https://github.com/<你的用户名>/kids-reward.git /opt/kids-reward
cd /opt/kids-reward

# 3. 告诉 compose 数据在哪
cp .env.example .env
nano .env        # 取消注释并填写 KIDS_HOST_DATA / KIDS_HOST_UPLOADS / KIDS_HOST_RULES

# 4. 起服务
sudo docker compose up -d --build
sudo docker compose logs -f          # 看到访问地址就可以 Ctrl+C
```

#### 把本机的数据搬过去

```bash
# 在 Windows 上执行（先停掉本机服务，两边不能同时跑）
scp -r data uploads rules.yaml root@服务器IP:/srv/star-kids/
```

数据库文件建议先在家长端做一次备份再传（`VACUUM INTO` 出来的是干净快照），
理由和 `deploy/linux/README.md` 第五节说的一样。

#### 以后每次更新

```bash
cd /opt/kids-reward
git pull
sudo docker compose up -d --build
```

- 只改了 `app/` 或 `static/`：**增量构建 3~8 秒**，中断 2~3 秒
- 改了 `requirements.txt`：30~90 秒（只有依赖层失效）
- `data/`、`uploads/`、`rules.yaml` 在 `/srv/star-kids/`，重建镜像碰不到

想更省事，把这三条存成 `~/.bashrc` 里的别名：

```bash
alias kids-up='cd /opt/kids-reward && git pull && sudo docker compose up -d --build && docker compose ps'
```

### 路线 B · systemd 原生部署（不装 Docker）

代码放 `/opt/star-kids-src`（git 仓库），服务跑在 `/opt/star-kids`，用脚本同步：

```bash
# 首次
sudo git clone https://github.com/<你的用户名>/kids-reward.git /opt/star-kids-src
sudo bash /opt/star-kids-src/deploy/linux/install.sh

# 以后每次更新（自动同步 → 重启 → 健康检查 → 失败自动回滚）
sudo bash /opt/star-kids-src/deploy/linux/update.sh

# 只想看看有没有新版本，不动服务
sudo bash /opt/star-kids-src/deploy/linux/update.sh --check
```

`update.sh` 做的事和重要保证：

| 它做什么 | 说明 |
|---|---|
| `git pull --ff-only` | 源码目录有本地改动时直接报错，不会悄悄合并出乱子 |
| 整个替换 `app/` `static/` | 而不是覆盖拷贝，这样删掉的旧文件不会残留 |
| `requirements.txt` 变了才装依赖 | 没变就跳过，省 10~60 秒 |
| 重启后等 `/health` 最多 40 秒 | 起不来就 **自动回滚到上一个提交**，不会留下一个打不开的家 |
| 永不碰 `data/` `uploads/` `rules.yaml` | 这三个是数据，不是代码 |

---

## 五、回滚：改坏了怎么办

分三种情况，从轻到重。

**① 只改坏一个文件**

```bash
git checkout HEAD -- app/main.py     # 恢复到上次提交的样子
git push                              # 如果已经把坏的推上去了，再补一个"回到上一版"的提交
```

**② 整体退回上一个版本**

```bash
git log --oneline -5                  # 找到要回去的那个提交号
git revert <提交号>                   # 生成一个"反向提交"，历史仍然完整
git push
```

`git revert` 比 `git reset --hard` 安全：**它不改写已经推上去的历史**，
不会让服务器和本机对不上。只有在自己一个人用的仓库、且确定没人拉过时，才考虑 `reset`。

**③ 服务器上急着恢复服务**

```bash
cd /opt/kids-reward
git log --oneline -3
git checkout <上一个好的提交号>
sudo docker compose up -d --build
```

数据一直在 `/srv/star-kids/`，回滚代码从来不会丢孩子的记录。
真出大事了，`/srv/star-kids` 整个目录拷走就是完整备份。

---

## 六、五个坑（都是踩过才知道的）

### 坑 1 · 误把 `data/` 提交了

**现象**：`git push` 卡几分钟然后失败，或者仓库突然变成几个 GB。

**处理**：

```bash
git rm -r --cached data uploads backups     # 只从索引里移除，磁盘文件不动
git commit -m "chore: 数据目录移出版本控制"
```

如果**已经 push 上去了**，历史里仍然躺着这些大文件，仓库还是很大。
这时要么重建仓库（删掉 GitHub 上的仓库重新 push 一次，最省事），
要么用 `git filter-repo` 清理历史（需要额外安装，且会重写所有提交号）。

**预防**：`.gitignore` 已经配好了，`git add .` 之前瞄一眼 `git status` 就够了。

### 坑 2 · `.env` 提交上去了

里面有服务器路径，不含密钥，问题不大，但仍然是"不该进仓库的东西"。
`git rm --cached .env` + 确认 `.gitignore` 里有 `.env` 即可。

真正的密钥（`KIDS_SECRET`）在服务器的 `/etc/star-kids.env` 里，
由 `install.sh` 随机生成，**从来不在仓库里**，这一点是安全的。

### 坑 3 · `rules.yaml` 一直是"已修改"状态

家长端在网页上改规则会写回 `rules.yaml`，于是 `git status` 里它永远是脏的。

两个处理方式，任选：

- **服务器**：按路线 A 用 `.env` 把它指到 `/srv/star-kids/rules.yaml`，仓库目录里那份就没人动了
- **Windows 本机**：提交前 `git checkout -- rules.yaml` 丢弃本地改动（注意这会丢掉你在网页上改的规则，
  所以更推荐的做法是：本机的个性化规则本来就该只存在数据库旁边，不该提交）

### 坑 4 · Windows 上写的 `.sh` 到 Linux 上跑不了

**现象**：`install.sh: line 12: $'\r': command not found`。

**原因**：Windows 用 CRLF 换行，Linux 的 bash 不认。

本项目已经在 `.gitattributes` 里定好了规则：文本文件在仓库里一律存 LF，
`*.bat` 例外（cmd.exe 需要 CRLF），字体图片等二进制不做任何转换。
**所以这个坑你不用管**，clone 到 Linux 上就是能跑的。

顺带说明为什么不靠"每个人本地配 `core.autocrlf`"：本地配置只管自己那台机器，
换个人、换台机器就又乱了。规则写进仓库才对新克隆生效。

### 坑 5 · GitHub 单文件 100 MB 限制

`data/textbooks/` 里单个 PDF 可能超过 100 MB，push 会直接被拒。
这些文件本来就在 `.gitignore` 里，正常不会碰上。
如果哪天要给项目加素材，走"网盘 + 下载脚本"（`tools/fetch_textbooks.py` 就是这个思路），
不要往仓库里塞。

---

## 七、可选：让 GitHub 顺手帮你做两件事

**① 给版本打标签**，出问题能一句话说清"孩子在用的那版是哪个"：

```bash
git tag -a v1.2.0 -m "开学季：新增愿望截止日期"
git push --tags
```

**② GitHub Actions 自动跑回归**（家庭自用可选，不是必需）。
仓库里的 `smoke_test*.py` 需要真实的数据库和运行中的服务，
要在 CI 里跑得先起服务、灌测试数据，配置下来得花点时间。
**日常手动在容器里跑一次更划算**：

```bash
sudo docker compose exec kids python smoke_test.py
```

---

## 附：命令速查

| 想做什么 | 命令 |
|---|---|
| 看改了哪些文件 | `git status -s` |
| 看具体改了什么 | `git diff` |
| 提交 | `git add -A && git commit -m "feat(x): ..."` |
| 推上去 | `git push` |
| 看历史 | `git log --oneline -10` |
| 撤销没提交的改动 | `git checkout -- <文件>` |
| 退回某次提交（安全） | `git revert <提交号>` |
| 服务器更新（Docker） | `cd /opt/kids-reward && git pull && sudo docker compose up -d --build` |
| 服务器更新（systemd） | `sudo bash /opt/star-kids-src/deploy/linux/update.sh` |
