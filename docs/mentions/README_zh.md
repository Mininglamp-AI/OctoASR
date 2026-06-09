<h1 align="center">@提及替换 · Mention</h1>

<p align="center">
  把转写结果里口语化的称呼、音译人名，自动替换成你想要的规范写法。<br>
  例如：语音说「艾特小明」 →  转写并替换为 <code>@王小明</code>
</p>

<p align="center">
  <b>中文</b> | <a href="README.md">English</a>
</p>

<p align="center">
  <a href="#-简介">简介</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-工作原理">工作原理</a> ·
  <a href="#-手动编辑配置">手动编辑</a> ·
  <a href="#-开发者接口">开发者接口</a> ·
  <a href="#-常见问题">常见问题</a>
</p>

---

## 📖 简介

ASR 在转写时，对人名、英文专有名词常输出成音译或不统一的写法（如「冯诺伊曼」「冯·诺伊曼」），对团队内部昵称也无法识别。

**mention 功能**在转写完成后做一次后处理：扫描文本中的 `@提及`，按映射表把别名替换成规范名。

替换来源分三层，**优先级从低到高**依次叠加，同名时后者覆盖前者：

| 优先级 | 来源 | 文件 | 适用场景 |
| :---: | :--- | :--- | :--- |
| 低 | 内置表 | 代码内置 `MENTION_MAP` | 预置常见音译人名 |
| 中 | OpenClaw | `~/.mano-asr/mentions/openclaw.json` | 一个规范名配多个别名 |
| **高** | **用户表** | `~/.mano-asr/mentions/user.json` | **自定义昵称，最常用** |

> 💡 配置文件**首次使用时自动创建**为空模板，无需手动建目录。

---

## 🚀 快速开始

> 面向所有用户，**无需编辑任何 JSON 文件**。

**1. 启动服务并打开管理页**

```bash
mano-asr start        # 启动服务（若尚未启动）
mano-asr mentions     # 自动打开词条管理网页
```

浏览器会自动打开管理页面 `http://127.0.0.1:<端口>/mentions`。

**2. 在页面上管理词条**

| 操作 | 步骤 |
| :--- | :--- |
| ➕ 添加 | 填入 **Nickname**（昵称）与 **Canonical name**（规范名），点 **Add** |
| ✏️ 编辑 | 点某行的 **Edit**，行内修改后点 **Save** |
| 🗑️ 删除 | 点某行的 **Delete** |

> ✅ 改动**即时生效**，下一次转写立即采用，无需重启服务。
> 🔗 只想拿到链接、不自动开浏览器：`mano-asr mentions --no-browser`

---

## ⚙️ 工作原理

转写完成后，服务端按以下两步处理文本（见 `server.py`）：

```
原始转写：  艾特小明确认一下
              │
              ▼  ① 「艾特」归一化  →  @
            @小明确认一下
              │
              ▼  ② mention 替换   →  按映射表查 user.json
            @王小明确认一下        ✓
```

**① 「艾特」归一化** — ASR 常把语音里的 `@`（读音 at）转写成中文「艾特」，服务先把它（含紧随空格）还原成 `@`：

| 转写输入 | 归一化后 |
| :--- | :--- |
| `艾特小明` | `@小明` |
| `艾特 小明` | `@小明` |

**② mention 替换** — 调用 `replace()`，把 `@别名` 换成 `@规范名`（前提：`user.json` 配置了 `小明 → 王小明`）：

| 归一化后 | 最终结果 |
| :--- | :--- |
| `@小明` | `@王小明` |

### 匹配规则要点

- 🎯 只替换以 `@` 开头的提及；正文中未带 `@` 的同名文字**不会**被改动。
- ↔️ `@` 后的名字需有自然边界（空格、标点或中英文切换）。如 `@维杰 确认` 可正确替换；若紧跟其它中文且整体不在映射表中，则可能匹配失败。
- 🔤 支持去括号后缀再匹配：`@达·芬奇(davinci)` → 先去掉 `(davinci)` 再查表。
- 🛟 别名在映射表中找不到时**原样保留**，不会报错。

---

## 📝 手动编辑配置

> 进阶用法。若你更习惯直接改文件，配置位于 `~/.mano-asr/mentions/`。

### user.json — 推荐，简单键值

一个数组，每项含 `nickname`（昵称）与 `canonical_name`（规范名）：

```json
[
  { "nickname": "小明", "canonical_name": "王小明" },
  { "nickname": "小红", "canonical_name": "张小红" }
]
```

### openclaw.json — 结构化，一名多别名

适合一个人有多个别名的场景，`aliases` 与 `uncertain_aliases` 都会被收录：

```json
{
  "persons": {
    "p1": {
      "canonical_name": "王小明",
      "aliases": [
        { "alias": "小明" },
        { "alias": "明儿" }
      ],
      "uncertain_aliases": [
        { "alias": "晓明" }
      ]
    }
  }
}
```

> ✅ 编辑后**无需重启**：`replace()` 每次转写都会重新读取，保存即生效。
> 🛡️ 若 JSON 格式损坏，该文件会被跳过（仅用其余来源），**不影响**转写主流程。

---

## 🧩 开发者接口

### Python 函数 · `utils/mention.py`

| 函数 | 作用 |
| :--- | :--- |
| `replace(text) -> str` | 对整段文本做 `@提及` 替换，返回替换后文本 |
| `extract(text) -> list` | 抽取文本中所有 `@提及`（不替换） |
| `list_user_mentions() -> list` | 读取 user.json 全部词条 |
| `add_user_mention(nickname, canonical_name) -> list` | 新增/更新（昵称存在则更新），返回完整列表 |
| `update_user_mention(index, nickname, canonical_name) -> list` | 按索引更新 |
| `delete_user_mention(index) -> list` | 按索引删除 |

```python
from utils import mention

mention.add_user_mention("小明", "王小明")
print(mention.list_user_mentions())   # [{'nickname': '小明', 'canonical_name': '王小明'}]
print(mention.replace("hi @小明"))     # hi @王小明
```

> ⚠️ `nickname` / `canonical_name` 为空抛 `ValueError`；索引越界抛 `IndexError`。

### HTTP API · 集成于 8787 服务

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET` | `/mentions` | 管理页面 |
| `GET` | `/v1/mentions` | 列出全部词条 |
| `POST` | `/v1/mentions` | 新增/更新，body `{nickname, canonical_name}` |
| `PUT` | `/v1/mentions/{index}` | 按索引更新 |
| `DELETE` | `/v1/mentions/{index}` | 按索引删除 |

```bash
# 查看全部
curl http://127.0.0.1:8787/v1/mentions

# 新增一条
curl -X POST http://127.0.0.1:8787/v1/mentions \
  -H "Content-Type: application/json" \
  -d '{"nickname":"小明","canonical_name":"王小明"}'
```

> 返回统一格式 `{"ok": true, "items": [...]}`；出错时返回对应 4xx / 5xx 与错误信息。

---

## ❓ 常见问题

<details>
<summary><b>目录 <code>~/.mano-asr/mentions</code> 不存在？</b></summary>

正常。首次转写或首次访问管理页时会自动创建空模板，无需手动建。
</details>

<details>
<summary><b>在页面改了但转写没生效？</b></summary>

确认服务在运行、且转写走的是同一台机器的同一服务。替换是即时读取的，通常无需重启；如仍异常，可 `mano-asr restart` 后重试。
</details>

<details>
<summary><b>语音说「艾特某某」没被替换成 <code>@</code>？</b></summary>

归一化只处理「艾特」字样。请确认转写结果里确实出现了「艾特」，且该昵称已在 user.json / 页面中配置了对应的规范名。
</details>

<details>
<summary><b>会误伤口语里的「艾特一下」吗？</b></summary>

会。当前为无条件把「艾特」归一化为 `@`，因此「艾特一下」会变成「@一下」。若该别名无映射，则后续 mention 替换不动它，但 `@` 符号会保留。
</details>
