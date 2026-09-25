# 推送到 GitHub

代码已经全部提交到本地 `main` 分支，**只差最后一步 push**。

我在沙箱里没有外网（连 github.com:443 超时），所以推不出去。

---

## 你只需要跑这一条

在本目录下：

```bash
git push -u origin main
```

会提示输入 GitHub 用户名和密码。**密码栏要填 Personal Access Token**，
不是账号密码（GitHub 从 2021 年起就不接受密码了）。

### 没有 Token 的话

1. 打开 https://github.com/settings/tokens
2. 「Generate new token」→ 选 **classic**
3. 勾选 **repo** 权限
4. 生成后复制那串 `ghp_...`，粘贴到密码栏

想省掉每次输入，可以用 SSH：

```bash
git remote set-url origin git@github.com:Neiyako/MCMtools.git
git push -u origin main
```

---

## 推送前建议确认一下

```bash
git log --oneline -1        # 应该是 22d32aa 这次提交
git status                  # 应该是 clean
git diff --stat HEAD~0      # 看这次提交动了什么
```

当前提交：**278 个文件，51973 行**，不含 `node_modules`、
`.app`、运行产物。

---

## 如果远程仓库已经有内容了

`Neiyako/MCMtools` 若已有提交（比如建仓时勾了 README），
直接 push 会被拒。两个选择：

```bash
# 方案 A：远程内容不要了，用本地覆盖（谨慎）
git push -u origin main --force

# 方案 B：先合并远程，再推（保留远程历史）
git pull --rebase origin main
git push -u origin main
```

选 A 之前确认远程那些提交确实不需要。

---

## 推送后

打一个版本 tag，这样用户报 bug 时能对上具体版本：

```bash
git tag -a v0.5.0 -m "MCMtools 0.5.0"
git push origin v0.5.0
```

之后 `./core/mcm --version` 会输出 `0.5.0+git.<提交号>`，
诊断报告里也带上这个值。
