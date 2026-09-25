# 推送状态与后续操作

## 当前状态：已全部推送完成

```
远程  https://github.com/Neiyako/MCMtools
分支  main
最新  2f225d0  修复空项目上变动参数被静默丢弃，补齐命名/位置与使用指南
```

本地和远程的提交号一致，工作区干净。**不需要再做任何推送操作。**

验证一下：

```bash
git status -sb          # 应该显示 ## main...origin/main，没有 ahead
git ls-remote origin refs/heads/main | cut -c1-7
git rev-parse --short HEAD     # 两个值应该一样
```

---

## 后续怎么推

改完东西之后：

```bash
git add -A
git commit -m "说明这次改了什么"
git push
```

**前提是这台机器能连上 github.com。** 之前推不上去是因为沙箱没有外网，
现在网络通了。如果又推不动，先看是不是网络问题：

```bash
git ls-remote origin        # 能列出 HEAD 就说明连得通
```

### 认证

如果 `git push` 要求输密码，**密码栏要填 Personal Access Token**，
不是账号密码（GitHub 从 2021 年起就不接受密码了）。

没有 Token 的话：

1. 打开 https://github.com/settings/tokens
2. 「Generate new token」→ 选 **classic**
3. 勾选 **repo** 权限
4. 生成后复制那串 `ghp_...`，粘贴到密码栏

想省掉每次输入，可以用 SSH：

```bash
git remote set-url origin git@github.com:Neiyako/MCMtools.git
```

然后把 `~/.ssh/id_ed25519.pub` 加到 GitHub 的 SSH keys 里。

---

## 提交历史

| 提交 | 内容 |
|---|---|
| `2f225d0` | 修复空项目变动参数丢失；补命名/位置文档与使用指南 |
| `60cb557` | 更新项目 |
| `85f2e04` | 更新项目 |
| `bbdc7b2` | update |
| `e886d12` | 修复：选题第一步卡死 —— 界面根本没有锁定的入口 |
| `7f6a689` | 补充推送说明 |
| `22d32aa` | MCMtools 0.5.0：面向 MCM/ICM 的离线建模工具链 |

---

## 仓库里有什么

284 个文件，主要是：

```
core/          核心代码 + 628 项 Python 测试
web/           面板 + 8 个 jsdom 测试
templates/     101 个模板（图 38、模型 17、表 13、实验 9、论文 8、代码 16）
docs/          16 份文档
examples/      示例项目
```

**没进仓库的东西**（`.gitignore` 挡掉了）：

- 433 篇论文语料（1.1G，版权作品，只在本机 `/tmp/mcmtools_archive/`）
- `node_modules/`、`build/`、`runs/`、`__pycache__/`
- `MCMtools.app/`（本机签名产物，换机器要重新 `./build-app.sh`）

> `/tmp` 会在重启后清空。语料如果还要用，挪到别的地方存好 ——
> 但**别提交进仓库**。

---

## 如果远程有别人的提交

推的时候报 `non-fast-forward`，说明远程比你新：

```bash
git pull --rebase origin main
git push
```

`--rebase` 把你的提交摞到远程最新之上，历史是一条直线，比 merge 干净。

**别用 `--force`**，除非确定远程那些提交你确实不要了。

---

## 打标签（可选）

想标记版本：

```bash
git tag -a v0.5.0 -m "MCMtools 0.5.0"
git push origin v0.5.0
```

版本号的唯一来源是 `core/mcmcore/__init__.py` 里的 `__version__`，
改版本时**只改那一处**，`./core/mcm --version` 会自动带上 git 提交号。
