"""参考文献：从 BibTeX 解析、校验、生成。

为什么需要这个模块
------------------
`Reference` 数据结构和 `references.bib` 生成器本来就有，但**没有入口**：
用户得手工编辑 `paper/references.yaml`，一个个填 key/title/authors 字段。
而现实里没人手写 BibTeX —— 都是从期刊页面或 Google Scholar 复制一段
BibTeX 贴进来。所以缺的是"粘贴"这一步。

这里不做联网检索：比赛期间可能断网，而且自动抓来的文献条目一旦错了，
用户不会逐条核对。宁可让他粘贴，粘进来的至少是他自己看过的。

两个真实约束决定了实现
----------------------
1. **COMAP 要求 AI 工具列进参考文献**，不只是正文提一句。所以
   `ai_generated` 是一等字段，不是备注。
2. **每条文献都要在正文被引用**（语料 707/707）。所以这里提供
   交叉核对：哪些条目从没被 \cite 过、哪些 \cite 找不到条目 ——
   这两类都是实打实的缺陷，而且人眼很难查。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# BibTeX 的条目类型 -> 中文说明。面板要给中文提示。
ENTRY_TYPES: Dict[str, str] = {
    "article": "期刊论文",
    "inproceedings": "会议论文",
    "conference": "会议论文",
    "book": "专著",
    "inbook": "专著章节",
    "phdthesis": "博士论文",
    "mastersthesis": "硕士论文",
    "techreport": "技术报告",
    "misc": "数据集 / 网站 / 软件 / AI 工具",
    "online": "网络资源",
    "unpublished": "未发表",
}

# 必填字段按类型区分。缺了这些，条目在读者眼里就是不完整的。
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "conference": ["author", "title", "booktitle", "year"],
    "book": ["author", "title", "publisher", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["title"],
    "online": ["title", "url"],
}

_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)


def _split_fields(body: str) -> Dict[str, str]:
    """把 BibTeX 的字段体切成键值。

    不能简单按逗号分 —— 标题里就有逗号，花括号里还有嵌套
    （``{A {B} C}``）。所以要跟踪花括号深度，只在深度 0 的逗号处切。
    """
    out: Dict[str, str] = {}
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in body:
        if ch == "{":
            depth += 1
            buf.append(ch)
        elif ch == "}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))

    for part in parts:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = k.strip().lower()
        val = v.strip().rstrip(",").strip()
        # 去掉最外层花括号或引号
        if len(val) >= 2 and val[0] == "{" and val[-1] == "}":
            val = val[1:-1]
        elif len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            val = val[1:-1]
        # 去掉 BibTeX 用来保护大小写的花括号：{Wordle} -> Wordle
        val = re.sub(r"[{}]", "", val).strip()
        if key and val:
            out[key] = val
    return out


def parse_bibtex(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解析一段 BibTeX，返回 (条目列表, 警告列表)。

    容错优先：用户从网页复制的东西格式五花八门，因为一个字段
    不规范就整段拒绝，会让人以为工具坏了。能解析出来的先给，
    有疑问的在警告里说清楚。
    """
    entries: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not (text or "").strip():
        return entries, ["没有内容可以解析。"]

    # 先按 @ 切成块，再逐块解析。比一次性正则稳，出错能定位到第几条。
    chunks = re.split(r"(?=@\w+\s*\{)", text)
    for raw in chunks:
        raw = raw.strip()
        if not raw.startswith("@"):
            continue
        m = _ENTRY_RE.match(raw)
        if not m:
            warnings.append(f"这一段看不懂，跳过了：{raw[:50]}...")
            continue
        etype = m.group(1).lower()
        key = m.group(2).strip()
        body = raw[m.end():]
        # 去掉结尾的右花括号
        body = body.rstrip()
        if body.endswith("}"):
            body = body[:-1]
        fields = _split_fields(body)

        entry: Dict[str, Any] = {
            "key": key,
            "type": {"conference": "inproceedings"}.get(etype, etype),
            "title": fields.get("title"),
            "year": None,
            "venue": fields.get("journal") or fields.get("booktitle")
                     or fields.get("publisher") or fields.get("institution"),
            "url": fields.get("url") or fields.get("doi"),
            "bibtex": raw,
            "ai_generated": False,
        }
        if fields.get("year"):
            try:
                entry["year"] = int(re.sub(r"[^0-9]", "", fields["year"])[:4])
            except (ValueError, TypeError):
                warnings.append(f"{key}：年份「{fields['year']}」读不出数字。")

        if fields.get("author"):
            # BibTeX 用 " and " 分隔作者。写成逗号的话条目会错，
            # 而这是从网页复制时最常见的走样。
            authors = re.split(r"\s+and\s+", fields["author"])
            if len(authors) == 1 and authors[0].count(",") >= 1 \
                    and " and " not in fields["author"]:
                warnings.append(
                    f"{key}：作者用逗号分隔了。BibTeX 要求用 and 连接，"
                    "已按 and 处理，请核对。")
                authors = re.split(r",\s*(?=[A-Z])", fields["author"])
            entry["authors"] = [a.strip() for a in authors if a.strip()]

        # AI 工具要能一眼认出来 —— COMAP 要求它出现在参考文献里
        blob = " ".join(str(v) for v in fields.values()).lower()
        if any(t in blob for t in ("chatgpt", "gpt-4", "gpt-5", "claude",
                                   "gemini", "copilot", "deepseek", "llm")):
            entry["ai_generated"] = True

        entries.append(entry)
    return entries, warnings


def check_entries(entries: List[Dict[str, Any]]) -> List[str]:
    """检查条目本身的问题。返回人类可读的问题列表。"""
    problems: List[str] = []
    seen: Dict[str, int] = {}
    for e in entries:
        key = e.get("key") or "(无 key)"
        seen[key] = seen.get(key, 0) + 1
    for key, n in seen.items():
        if n > 1:
            problems.append(f"「{key}」出现了 {n} 次，key 必须唯一 —— "
                            "重复的 key 会让 \\cite 指向不确定的那条。")

    for e in entries:
        key = e.get("key") or "(无 key)"
        etype = (e.get("type") or "misc").lower()
        need = REQUIRED_FIELDS.get(etype, ["title"])
        have = {
            "author": bool(e.get("authors")),
            "title": bool(e.get("title")),
            "year": bool(e.get("year")),
            "journal": bool(e.get("venue")) if etype == "article" else True,
            "booktitle": bool(e.get("venue")) if etype.startswith("inproc") else True,
        }
        missing = [f for f in need if f in have and not have[f]]
        if missing:
            zh = {"author": "作者", "title": "标题", "year": "年份",
                  "journal": "期刊名", "booktitle": "会议名"}
            problems.append(
                f"「{key}」缺 {'、'.join(zh.get(f, f) for f in missing)}"
                f"（{ENTRY_TYPES.get(etype, etype)} 需要这些字段才完整）。")
        if not e.get("year") and etype not in ("misc", "online"):
            problems.append(f"「{key}」没有年份，评审无法核实。")
    return problems


def cross_check(entries: List[Dict[str, Any]],
                prose: str) -> Dict[str, List[str]]:
    """正文里的 \\cite 和条目列表对不上。这是人眼最难查的一类错。

    两个方向都要查：
    * 引了但没条目 —— 编译出来是 [?]，而且 LaTeX 只给一个 warning
    * 有条目但没引 —— 语料里 707/707 都被引过，没被引的条目是缺陷
    """
    keys = {e.get("key") for e in entries if e.get("key")}
    cited: set = set()
    for m in re.finditer(r"\\cite[a-z]*\{([^}]*)\}", prose or ""):
        for k in m.group(1).split(","):
            k = k.strip()
            if k:
                cited.add(k)

    missing_entry = sorted(cited - keys)   # 引了但没条目
    uncited = sorted(keys - cited)         # 有条目但没引
    return {"missing_entry": missing_entry, "uncited": uncited}


def to_bibtex(entries: List[Dict[str, Any]]) -> str:
    """把条目导回 BibTeX，方便用户复制到别处或存档。"""
    out: List[str] = []
    for e in entries:
        etype = e.get("type") or "misc"
        out.append(f"@{etype}{{{e.get('key', 'unknown')},")
        if e.get("title"):
            out.append(f"  title = {{{e['title']}}},")
        if e.get("authors"):
            out.append(f"  author = {{{' and '.join(e['authors'])}}},")
        if e.get("year"):
            out.append(f"  year = {{{e['year']}}},")
        if e.get("venue"):
            field = "journal" if etype == "article" else "booktitle"
            out.append(f"  {field} = {{{e['venue']}}},")
        if e.get("url"):
            out.append(f"  url = {{{e['url']}}},")
        if e.get("ai_generated"):
            out.append("  note = {AI tool, disclosed per COMAP policy},")
        out.append("}")
        out.append("")
    return "\n".join(out)


def starter_bibtex() -> str:
    """给面板一个可粘贴的示例。

    和示例数据一样的道理：空文本框配上"请填 BibTeX"等于没给说明。
    用户看到的应该是一段能直接对照着改的真实条目。
    """
    return """@article{wordle2022,
  title = {Wordle and the attention economy},
  author = {Smith, Jane and Chen, Wei},
  journal = {Journal of Digital Culture},
  year = {2022},
  volume = {14},
  pages = {101--118}
}

@misc{wordle_data2023,
  title = {Daily Wordle results, 2022-01 to 2023-01},
  author = {Tracy, Michael and Park, Soo-Jin},
  year = {2023},
  url = {https://www.kaggle.com/datasets/...},
  note = {accessed 2023-02-01}
}

@misc{chatgpt2023,
  title = {ChatGPT (GPT-4) [Large language model]},
  author = {OpenAI},
  year = {2023},
  url = {https://openai.com/chatgpt},
  note = {Used for language editing only}
}
"""


def guidance() -> Dict[str, Any]:
    """给面板的说明素材。前端不硬编码这些，避免两处不一致。"""
    return {
        "entry_types": [{"value": k, "label": v}
                        for k, v in ENTRY_TYPES.items()],
        "starter": starter_bibtex(),
        "rules": [
            "每条文献都要在正文里 \\cite 过 —— 语料 707/707 都做到了。",
            "用了 AI 工具，必须在参考文献里列出，不能只在正文或致谢里提一句。",
            "不要设「文献综述」章节，语料 415 篇里一次都没出现过。相关工作写在引言。",
            "正文引用统一用 \\cite{key}，不要手写 [1]：增删条目后手写编号会错位。",
            "机构报告、数据集、网站也要进参考文献，不能只在正文提一句。",
            "网络资源写访问日期，否则评审无法核实。",
        ],
    }
