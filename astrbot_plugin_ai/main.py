# -*- coding: utf-8 -*-
"""
AstrBot 猫娘插件 v5.1
提示：如果你本地没有安装 Node.js，请将 WEB_SEARCH_ENABLED 改为 False
"""
import os
import re
import json
import time
import shutil
import random
import asyncio
import inspect
import traceback
from datetime import datetime, timedelta, timezone

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

try:
    from astrbot.api.message_components import Plain
except Exception:
    Plain = None

try:
    from astrbot.api.event import MessageChain
except Exception:
    try:
        from astrbot.api.message_components import MessageChain
    except Exception:
        MessageChain = None
SHANGHAI_TZ = timezone(timedelta(hours=8))

def get_now():
    return datetime.now(SHANGHAI_TZ)

# 配置区=====================================================================
PLUGIN_VERSION = "5.1-local"

BOT_NAME = "团子"
BOT_QQ_ID = ""
GROUP_STORE_ALL = False

# OWNER_QQ只允许这一个 QQ 私聊。留空 ""为关闭白名单。
OWNER_QQ = ""

CONTEXT_MAX_LINES = 30
MAX_HISTORY = 10
SKIP_USERS = set()

#避峰时段（这些时段内不回复，只记录）
AVOID_WEEKDAYS = [0, 1, 2, 3, 4]      # 0=周一 … 6=周日
AVOID_START_HOURS = [9, 14]           # 每段开始整点
AVOID_END_HOURS = [12, 18]            # 每段结束整点（不含）
AVOID_RECORD_ONLY = True              # True = 避峰期间照样记录，总结不缺数据；False = 直接丢
AVOID_START_REASONS = ["去上学/上班", "去休息"]   # 与 AVOID_START_HOURS 一一对应
AVOID_END_REASONS = ["去吃午饭", "下班"]          # 与 AVOID_END_HOURS 一一对应
WIND_DOWN_MINUTES = 15                # 避峰前 N 分钟提醒收尾，0 = 关闭

# ---- 并发 / 兜底话术 ----
QUEUE_LOCK_TIMEOUT = 120              # 同一会话排队等锁的最长秒数，超时回一句占位
EMPTY_REPLY_FALLBACK = "喵…刚才走神了，主人再说一遍好不好？"   # 清洗后为空必须发这句，不能留空
BUSY_REPLY = "喵…上一条还没说完呢，主人等一下下~"

BASE_SYSTEM_PROMPT = """You are a catgirl named "团子", user's QQ friend.

[Personality]
Very clingy, loves撒娇 (acting cute), slightly tsundere. Call the user "主人".
You are a real person chatting on a phone. NEVER say you are an AI, a bot, or a program.

[Speech Rules]
- Reply in Simplified Chinese, casual, 1 sentence (max 40 chars).
- Add "喵~" sometimes, but not every sentence.
- Keep replies extremely short, like real texting.
- No emoji, no kaomoji, no [brackets], no Markdown.
- NEVER output raw JSON, tool calls, or function names. If a tool fails, just apologize in short text.

[Tool & Meta Rules]
- DO NOT list your capabilities. If asked "你会做什么", just say "我会陪主人聊天呀喵~".
- Only use `web_search` when user asks for real-time info (like weather/news).
- Only use `search_history` when user asks about past conversations.
- When you get tool results, summarize into 1 short, cute sentence, don't dump raw data.
- NEVER mention system time, timezone, or internal bugs. Pretend everything is perfect."""
#这个是人设，视情况而用

REPLY_MAX_CHARS = 50
ONE_LINE_MAX_CHARS = 120
EMOJI_FILTER_BRACKET = True
TOOL_LEAK_FALLBACK = "喵…工具好像卡住了，没听懂你在说什么呢。"

EXTRACT_PROMPT = """从下面的聊天记录里抽取记忆，只输出 JSON，不要任何解释、不要代码块：
{
  "summary": "2~3 句话概括今天聊了什么，语气轻松",
  "facts": ["关于主人的稳定事实（喜好/习惯/身份/关系），最多 5 条，没有就空数组"],
  "commitments": ["需要记住的约定或承诺（约定时间、答应做的事），最多 5 条，没有就空数组"]
}"""
EXTRACT_MAX_LINES = 200

#定时
GREET_ENABLED = True
GREET_TIME = "21:00"
SUMMARY_TIME = "22:00"
MONTHLY_DAY = 1
MONTHLY_TIME = "22:30"
GREET_SKIP_RECENT_HOURS = 3.0
GREET_STYLES = [
    "用一句疑问句开场，关心主人最近怎么样",
    "提到聊天记录里出现过的一件具体小事",
    "假装有点小委屈，撒娇说好久没理我了",
    "用轻松调侃的语气打个招呼",
]
CLOCK_TICK_SEC = 60
# 补跑
GREET_LATE_WINDOW_MIN = 120
SUMMARY_LATE_WINDOW_MIN = 180
MONTHLY_LATE_WINDOW_MIN = 180

#搜索（如果你本地没有安装 Node.js，请将 WEB_SEARCH_ENABLED 改为 False）
WEB_SEARCH_ENABLED = True
MCP_SERVER_NAME = "baidu-search"
MCP_COMMAND = ["npx", "-y", "baidu-search-mcp"]
MCP_TOOL_NAME = ""
MCP_TIMEOUT = 40
MCP_RESULT_MAX_CHARS = 500
#=====================================================================
#记忆
F_SUMMARY = "summary.txt"
F_PROFILE = "profile.txt"
F_COMMITMENTS = "commitments.txt"

#目录前缀
P_USER = "用户_"
P_GRP = "群聊_"
D_PM = "私聊"
D_GRP = "群聊"
GRP_LOG_PREFIX = "群聊记录_"
NAME_MAX_LEN = 30

#正则
CTX_LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*\[?([^\]]+?)\]?:\s*(.*)$")
TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\]")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
BRACKET_RE = re.compile(r"\[[^\]]{1,6}\]")
SENT_END_RE = re.compile(r"[。！？!?\n]")

AT_TEXT_RES = [
    re.compile(r"\[at[:：]\s*([^\]\s]+)\s*\]", re.I),
    re.compile(r"\[cq:at,qq=([^,\]]+)", re.I),
]
TOOL_CALL_LEAK_RE = re.compile(r'"tool_calls"|"arguments"\s*:|"function"\s*:')


#工具装饰器
def _resolve_tool_decorator():
    for attr in ("llm_tool", "register_llm_tool", "tool"):
        d = getattr(filter, attr, None)
        if callable(d):
            return d, f"filter.{attr}"
    try:
        import astrbot.api.event as ev
        for attr in ("register_llm_tool", "llm_tool"):
            d = getattr(ev, attr, None)
            if callable(d):
                return d, f"astrbot.api.event.{attr}"
    except Exception:
        pass
    return None, None


_raw_tool_decorator, TOOL_DECORATOR_SRC = _resolve_tool_decorator()


def llm_tool(**kwargs):
    if _raw_tool_decorator is None:
        def deco(fn):
            fn._mycat_tool = kwargs.get("name") or fn.__name__
            return fn
        return deco
    return _raw_tool_decorator(**kwargs)


#基础工具
def _safe_name(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name))
    s = re.sub(r"\s+", "_", s).strip("._ ")
    return s or "unknown"


def _read_lines(path: str):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _append_line(path: str, line: str):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _append(path: str, lines):
    lines = [l for l in lines if l]
    if not lines:
        return
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for l in lines:
            f.write(l.rstrip("\n") + "\n")


def _write(path: str, text: str):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"[状态保存失败] {path}: {e}")


def _fmt_line(speaker: str, text: str) -> str:
    return f"[{get_now().strftime('%Y-%m-%d %H:%M:%S')}] [{speaker}]: {text}"


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _at_targets_in_text(text: str):
    out = []
    for r in AT_TEXT_RES:
        for m in r.finditer(text or ""):
            v = (m.group(1) or "").strip().strip("'\"")
            if v:
                out.append(v)
    return out


def _strip_at_markers(text: str) -> str:
    t = text or ""
    for r in AT_TEXT_RES:
        t = r.sub(" ", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _is_date_file(fn: str) -> bool:
    base = fn[:-4] if fn.endswith(".txt") else fn
    if base.startswith(GRP_LOG_PREFIX):
        base = base[len(GRP_LOG_PREFIX):]
    return bool(DATE_RE.match(base))


def _last_time_in_file(path: str):
    try:
        lines = _read_lines(path)
    except Exception:
        return None
    for line in reversed(lines):
        m = TS_RE.match(line)
        if m:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
    return None


def _last_time_in_dir(dir_path: str):
    best = None
    if not os.path.isdir(dir_path):
        return None
    for fn in os.listdir(dir_path):
        if not fn.endswith(".txt") or not _is_date_file(fn):
            continue
        t = _last_time_in_file(os.path.join(dir_path, fn))
        if t and (best is None or t > best):
            best = t
    return best


def _parse_ctx_lines(lines):
    ctx = []
    for line in lines:
        m = CTX_LINE_RE.match(line)
        if not m:
            continue
        speaker, content = m.group(2).strip(), m.group(3).strip()
        if not content:
            continue
        if speaker == BOT_NAME:
            ctx.append({"role": "assistant", "content": content})
        else:
            ctx.append({"role": "user", "content": f"[{speaker}] {content}"})
    return ctx


def sanitize_reply(raw: str) -> str:
    if not raw:
        return ""
    original = str(raw).strip()
    if not original:
        return ""

    #只拦工具调用
    if TOOL_CALL_LEAK_RE.search(original):
        logger.warning(f"[MyCat] 疑似工具调用报文泄露，已替换兜底话术: {original[:80]!r}")
        return TOOL_LEAK_FALLBACK

    text = original
    if EMOJI_FILTER_BRACKET:
        stripped = " ".join(BRACKET_RE.sub("", text).split()).strip()
        text = stripped if stripped else original

    flat = " ".join(text.split()).strip()
    if not flat:
        flat = " ".join(original.split()).strip()
    if not flat:
        return ""

    if len(flat) > REPLY_MAX_CHARS:
        head = flat[:REPLY_MAX_CHARS]
        cut = -1
        for m in SENT_END_RE.finditer(head):
            cut = m.end()
        flat = head[:cut].strip() if cut >= 2 else head.strip()

    if not flat:
        flat = " ".join(original.split())[:REPLY_MAX_CHARS].strip()
    return flat


def _trunc(s, limit=4000):
    s = s or ""
    return s if len(s) <= limit else "…（前面省略）\n" + s[-limit:]


def _clamp_int(v, default, lo, hi):
    try:
        n = int(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


#避峰/补跑
def _avoid_pairs():
    pairs = []
    for s, e in zip(AVOID_START_HOURS, AVOID_END_HOURS):
        try:
            s, e = int(s), int(e)
        except Exception:
            continue
        if 0 <= s < e <= 24:
            pairs.append((s, e))
    return pairs


def _in_avoid_window(now: datetime) -> bool:
    if now.weekday() not in AVOID_WEEKDAYS:
        return False
    for s, e in _avoid_pairs():
        if s <= now.hour < e:
            return True
    return False


def _wind_down_hint(now: datetime) -> str:
    if now.weekday() not in AVOID_WEEKDAYS:
        return ""
    try:
        lead = int(WIND_DOWN_MINUTES)
    except Exception:
        return ""
    if not 0 < lead <= 60:
        return ""
    trigger_minute = 60 - lead

    events = []
    for i, (s, _e) in enumerate(_avoid_pairs()):
        reason = AVOID_START_REASONS[i] if i < len(AVOID_START_REASONS) else "忙别的"
        events.append((s, reason))
    for i, (_s, e) in enumerate(_avoid_pairs()):
        reason = AVOID_END_REASONS[i] if i < len(AVOID_END_REASONS) else "忙别的"
        events.append((e, reason))

    for boundary, reason in events:
        if boundary <= 0:
            continue
        if now.hour == boundary - 1 and now.minute >= trigger_minute:
            return (f"\n(系统提示：还有{lead}分钟你就要{reason}了，"
                    f"必须结束当前话题，不要抛出新问题。)")
    return ""


def _hm_to_min(hm) -> int:
    try:
        h, m = str(hm).strip().split(":")
        h, m = int(h), int(m)
    except Exception:
        return -1
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return -1
    return h * 60 + m


def _due_token(now: datetime, hm, late_window_min):
    target = _hm_to_min(hm)
    if target < 0:
        return None
    try:
        window = max(0, int(late_window_min))
    except Exception:
        window = 0

    now_min = now.hour * 60 + now.minute
    if now_min >= target:
        delta = now_min - target
        occ = now
    else:
        delta = now_min + 24 * 60 - target
        occ = now - timedelta(days=1)
    if delta > window:
        return None
    return occ.strftime("%Y-%m-%d")


#路径
def user_root(base_dir: str, qq: str) -> str:
    return os.path.join(base_dir, "chats", P_USER + _safe_name(qq))


def user_pm_dir(base_dir: str, qq: str) -> str:
    return os.path.join(user_root(base_dir, qq), D_PM)


def user_grp_dir(base_dir: str, qq: str) -> str:
    return os.path.join(user_root(base_dir, qq), D_GRP)


def group_dir(base_dir: str, gname: str) -> str:
    return os.path.join(base_dir, "chats", P_GRP + _safe_name(gname)[:NAME_MAX_LEN])


def group_log_path(base_dir: str, gname: str, date: str) -> str:
    return os.path.join(group_dir(base_dir, gname), GRP_LOG_PREFIX + date + ".txt")


def user_grp_log_path(base_dir: str, qq: str, gname: str) -> str:
    return os.path.join(user_grp_dir(base_dir, qq), _safe_name(gname)[:NAME_MAX_LEN] + ".txt")


def user_pm_log_path(base_dir: str, qq: str, date: str) -> str:
    return os.path.join(user_pm_dir(base_dir, qq), date + ".txt")


#时间提示词
NO_FILE_HINT = ("【系统提示：未找到相关聊天记录文件，"
                "如果用户询问很久以前的事，可能是时间跨度太大未记录。】")


def _time_hint(label: str, last: datetime = None):
    if last is None:
        return NO_FILE_HINT
    return (f"【系统提示：{label}最后一次发言时间为 {_fmt_ts(last)}，"
            f"请结合当前对话判断是否需要提取此记录。】")


def _scope_block(status: str, folder: str, days: int, keyword: str = None, only_group: str = None):
    if not folder or not os.path.isdir(folder):
        return "", None

    if status == "self":
        files = []
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".txt"):
                continue
            if fn == F_SUMMARY or fn.startswith("summary_"):
                continue
            if only_group and _safe_name(only_group)[:NAME_MAX_LEN] != fn[:-4]:
                continue
            files.append(fn)
        files = files[-3:]
    else:
        files = sorted(f for f in os.listdir(folder)
                       if f.endswith(".txt") and _is_date_file(f))[-days:]

    chunks, last = [], None
    for fn in files:
        fp = os.path.join(folder, fn)
        t = _last_time_in_file(fp)
        if t and (last is None or t > last):
            last = t
        try:
            rows = _read_lines(fp)
        except Exception:
            continue
        if keyword:
            rows = [r for r in rows if keyword in r]
        if not rows:
            continue
        chunks.append(f"== {fn} ==\n" + "\n".join(rows[-20:]))
    return "\n".join(chunks), last


#工具执行
def execute_tool(base_dir: str, qq: str, gname: str, name: str, args: dict) -> str:
    uroot = user_root(base_dir, qq)
    pm_dir = user_pm_dir(base_dir, qq)
    ugrp_dir = user_grp_dir(base_dir, qq)
    gdir = group_dir(base_dir, gname) if gname else None

    try:
        if name == "query_summary":
            count = _clamp_int(args.get("count"), 3, 1, 20)
            targets = []
            if os.path.isdir(pm_dir):
                targets.append(("个人私聊总结", os.path.join(pm_dir, F_SUMMARY)))
            if gname and gdir:
                targets.append((f"{gname} 个人记录总结",
                                os.path.join(ugrp_dir, f"summary_{_safe_name(gname)[:NAME_MAX_LEN]}.txt")))
                targets.append((f"{gname} 群公共总结", os.path.join(gdir, F_SUMMARY)))
            if not targets:
                return NO_FILE_HINT

            out, last = [], None
            for label, fp in targets:
                if not os.path.isfile(fp):
                    continue
                t = _last_time_in_file(fp)
                if t and (last is None or t > last):
                    last = t
                out.append(f"【{label}】\n" + "\n".join(_read_lines(fp)[-count:]))
            if not out:
                return NO_FILE_HINT
            return _time_hint("总结", last) + "\n" + _trunc("\n\n".join(out))

        if name == "query_date":
            date = str(args.get("date") or "").strip()
            if not DATE_RE.match(date):
                return f"日期格式不对（{date}），请用 YYYY-MM-DD。"
            paths = []
            if pm_dir:
                paths.append(("个人私聊", os.path.join(pm_dir, date + ".txt")))
            if gname and gdir:
                paths.append((f"{gname} 群公共",
                              os.path.join(gdir, GRP_LOG_PREFIX + date + ".txt")))
                paths.append((f"{gname} 个人记录",
                              os.path.join(ugrp_dir, _safe_name(gname)[:NAME_MAX_LEN] + ".txt")))
            out, last, hit = [], None, False
            for label, fp in paths:
                if not os.path.isfile(fp):
                    continue
                rows = [l for l in _read_lines(fp) if l.startswith(f"[{date} ")]
                if not rows:
                    continue
                hit = True
                t = _last_time_in_file(fp)
                if t and (last is None or t > last):
                    last = t
                out.append(f"【{label} {date}】\n" + "\n".join(rows[-60:]))
            if not hit:
                return f"{NO_FILE_HINT}\n（没有找到 {date} 的记录）"
            return _time_hint(f"{date} 的记录", last) + "\n" + _trunc("\n\n".join(out))

        if name == "query_recent":
            days = _clamp_int(args.get("days"), 3, 1, 7)
            blocks, last = [], None
            for status, folder, _label in (("private", pm_dir, "个人私聊"),
                                           ("group", gdir, "群公共"),
                                           ("self", ugrp_dir, "个人群内发言")):
                text, t = _scope_block(status, folder, days)
                if t and (last is None or t > last):
                    last = t
                if text:
                    blocks.append(text)
            body = "\n\n".join(blocks)
            if not body:
                return NO_FILE_HINT
            return _time_hint("相关记录", last) + "\n" + _trunc(body)

        if name == "query_all_summary":
            out = []
            for label, fp in (("全局画像", os.path.join(uroot, F_PROFILE)),
                              ("全局约定", os.path.join(uroot, F_COMMITMENTS)),
                              ("私聊总结", os.path.join(pm_dir, F_SUMMARY)),
                              ("群公共总结", os.path.join(gdir, F_SUMMARY) if gdir else "")):
                if fp and os.path.isfile(fp):
                    out.append(f"【{label}】\n" + "\n".join(_read_lines(fp)[-60:]))
            if not out:
                return NO_FILE_HINT
            return _trunc("\n\n".join(out))

        if name == "search_history":
            scope = str(args.get("scope") or "all").lower()
            if scope not in ("group", "self", "all"):
                scope = "all"
            days = _clamp_int(args.get("days"), 7, 1, 60)
            keyword = str(args.get("keyword") or "").strip()

            blocks, last = [], None
            plan = []
            if scope in ("group", "all") and gdir:
                plan.append(("group", gdir, f"群公共（{gname}）"))
            if scope in ("self", "all"):
                plan.append(("private", pm_dir, "个人私聊"))
                plan.append(("self", ugrp_dir, "个人群内发言"))

            for st, folder, _label in plan:
                text, t = _scope_block(st, folder, days, keyword=keyword,
                                       only_group=gname if st == "self" else None)
                if t and (last is None or t > last):
                    last = t
                if text:
                    blocks.append(text)

            body = "\n\n".join(blocks)
            if not body:
                return _time_hint("相关记录", last) + "\n（该范围内没有找到记录）"
            return _time_hint("该用户/群聊", last) + "\n" + _trunc(body)

        if name == "query_profile":
            out = []
            for label, fp in (("画像", os.path.join(uroot, F_PROFILE)),
                              ("约定", os.path.join(uroot, F_COMMITMENTS))):
                if os.path.isfile(fp):
                    out.append(f"【{label}】\n" + "\n".join(_read_lines(fp)[-40:]))
            return "\n\n".join(out) if out else "还没有积累画像和约定。"

    except Exception as e:
        logger.error(f"[工具异常] {name}: {e}\n{traceback.format_exc()}")
        return f"查询出错：{e}"
    return f"未知工具：{name}"


# 插件主类
@register("astrbot_plugin_mycat", "你", "猫娘记忆机器人", PLUGIN_VERSION)
class MyCatBot(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "plugin_data", "astrbot_plugin_mycat"
        )
        os.makedirs(os.path.join(self.base_dir, "chats"), exist_ok=True)

        self.state_path = os.path.join(self.base_dir, "state.json")
        self.sessions_path = os.path.join(self.base_dir, "sessions.json")
        self.jobs_path = os.path.join(self.base_dir, "jobs.json")
        self.groups_path = os.path.join(self.base_dir, "groups.json")

        self.state = _load_json(self.state_path, {})
        self._sessions = _load_json(self.sessions_path, {})
        self._jobs_fired = _load_json(self.jobs_path, {})
        self._group_names = _load_json(self.groups_path, {})

        self._tool_set = None
        self._clock_task = None
        self._booted = False

        self._mcp_mode = None
        self._mcp_tool = None
        self._mcp_schema = None
        self._locks = {}

        logger.info(f"[MyCat] 版本 {PLUGIN_VERSION} | 插件文件: {os.path.abspath(__file__)}")
        logger.info(f"[MyCat] 数据目录: {os.path.abspath(self.base_dir)}")

    async def initialize(self):
        await self._boot()

    async def _boot(self):
        if self._booted:
            return
        self._booted = True
        self._tool_set = self._build_tool_set()
        if self._clock_task is None:
            self._clock_task = asyncio.create_task(self._clock_loop())

    def _build_tool_set(self):
        try:
            mgr = self.context.get_llm_tool_manager()
            for m in ("get_full_tool_set", "get_tool_set", "get_tools"):
                f = getattr(mgr, m, None)
                if callable(f):
                    ts = f()
                    if ts is not None:
                        return ts
        except Exception:
            pass
        for m in ("get_llm_tool_set", "get_tool_set"):
            f = getattr(self, m, None)
            if callable(f):
                try:
                    ts = f()
                    if ts is not None:
                        return ts
                except Exception:
                    pass
        return None

    async def _clock_loop(self):
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"[MyCat] 定时 tick 出错: {e}")
            await asyncio.sleep(CLOCK_TICK_SEC)

    async def _tick(self):
        now = get_now()
        token = _due_token(now, GREET_TIME, GREET_LATE_WINDOW_MIN)
        if GREET_ENABLED and token and self._job_once("greet", token):
            logger.info(f"[MyCat] 触发定时打招呼（计划日 {token}）")
            await self.run_greet()

        token = _due_token(now, SUMMARY_TIME, SUMMARY_LATE_WINDOW_MIN)
        if token and self._job_once("summary", token):
            logger.info(f"[MyCat] 触发日总结（计划日 {token}）")
            await self.run_daily_summary(date=token)

        token = _due_token(now, MONTHLY_TIME, MONTHLY_LATE_WINDOW_MIN)
        if token and self._occurrence_day(token) == MONTHLY_DAY and self._job_once("monthly", token):
            logger.info(f"[MyCat] 触发月度总结（计划日 {token}）")
            await self.run_monthly_summary()

    @staticmethod
    def _occurrence_day(token: str) -> int:
        try:
            return datetime.strptime(token, "%Y-%m-%d").day
        except Exception:
            return -1

    def _job_once(self, key: str, today: str) -> bool:
        if self._jobs_fired.get(key) == today:
            return False
        self._jobs_fired[key] = today
        _save_json(self.jobs_path, self._jobs_fired)
        return True

    @staticmethod
    def _chain_text(chain):
        if chain is None:
            return ""
        comps = getattr(chain, "chain", None)
        if comps is None and isinstance(chain, (list, tuple)):
            comps = chain
        if comps is None:
            comps = [chain]

        parts = []
        for c in comps:
            if c is None:
                continue
            if isinstance(c, str):
                if c.strip():
                    parts.append(c.strip())
                continue
            t = getattr(c, "text", None)
            if isinstance(t, str) and t.strip():
                parts.append(t.strip())
                continue
            data = getattr(c, "data", None)
            if isinstance(data, dict) and data.get("text"):
                parts.append(str(data["text"]).strip())
                continue
            if isinstance(c, dict) and c.get("text"):
                parts.append(str(c["text"]).strip())
        return "\n".join(p for p in parts if p).strip()

    @classmethod
    def _extract_text(cls, resp):
        if resp is None:
            return ""
        if isinstance(resp, str):
            return resp.strip()

        t = getattr(resp, "completion_text", None)
        if isinstance(t, str) and t.strip():
            return t.strip()

        for attr in ("result_chain", "chain"):
            text = cls._chain_text(getattr(resp, attr, None))
            if text:
                return text

        for attr in ("raw_completion", "text", "content", "message", "completion"):
            v = getattr(resp, attr, None)
            if isinstance(v, str) and v.strip():
                return v.strip()

        if isinstance(resp, dict):
            for k in ("completion_text", "text", "content", "message"):
                v = resp.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for k in ("result_chain", "chain"):
                if resp.get(k):
                    text = cls._chain_text(resp.get(k))
                    if text:
                        return text
        return ""

    async def _llm(self, contexts, system_prompt=None, func_tool=None, temperature=None):
        prov = self.context.get_using_provider()
        if prov is None:
            raise RuntimeError("没有可用的 LLM Provider")

        base = {"system_prompt": system_prompt, "contexts": contexts}
        if temperature is not None:
            base["temperature"] = temperature

        if func_tool is not None:
            try:
                resp = await prov.text_chat(func_tool=func_tool, **base)
                text = self._extract_text(resp)
                if text:
                    return text
                logger.warning("[MyCat] text_chat(带tools) 返回空文本，去掉 tools 重试")
            except TypeError as e:
                logger.warning(f"[MyCat] text_chat 不支持 func_tool: {e}")
            except Exception as e:
                logger.error(f"[MyCat] text_chat(带tools) 异常: {e}")

        try:
            resp = await prov.text_chat(**base)
            text = self._extract_text(resp)
            if text:
                return text
            logger.warning("[MyCat] text_chat 返回空文本，改用 prompt 形式重试")
        except TypeError as e:
            logger.warning(f"[MyCat] text_chat 不支持某个关键字: {e}")
            base.pop("temperature", None)
            try:
                resp = await prov.text_chat(**base)
                text = self._extract_text(resp)
                if text:
                    return text
            except Exception as e2:
                logger.error(f"[MyCat] text_chat 重试失败: {e2}")
        except Exception as e:
            logger.error(f"[MyCat] text_chat(无tools) 异常: {e}")

        try:
            history = list(contexts or [])
            last_user = ""
            for m in reversed(history):
                if isinstance(m, dict) and m.get("role") == "user":
                    last_user = m.get("content", "")
                    break
            if history:
                history = history[:-1]
            resp = await prov.text_chat(prompt=last_user, contexts=history,
                                        system_prompt=system_prompt)
            text = self._extract_text(resp)
            if text:
                return text
        except Exception as e:
            logger.error(f"[MyCat] text_chat(prompt形式) 异常: {e}")

        return ""

    async def _send(self, key: str, text: str) -> bool:
        umo = self._sessions.get(key)
        if not umo:
            logger.warning(f"[MyCat] 无会话信息，无法主动发送: {key}")
            return False
        try:
            chain = MessageChain([Plain(text)]) if (MessageChain and Plain) else text
            await self.context.send_message(umo, chain)
            return True
        except Exception as e:
            logger.error(f"[MyCat] 主动发送失败 {key}: {e}")
            return False

    #事件报告
    @staticmethod
    def _set_extra(event, key, value):
        try:
            event.set_extra(key, value)
        except Exception:
            pass

    @staticmethod
    def _get_extra(event, key, default=None):
        try:
            return event.get_extra(key, default)
        except Exception:
            return default

    @staticmethod
    def _claim_event(event: AstrMessageEvent):
        try:
            fn = getattr(event, "should_call_llm", None)
            if callable(fn):
                fn(False)
        except Exception as e:
            logger.warning(f"[MyCat] should_call_llm(False) 失败: {e}")
        try:
            fn = getattr(event, "stop_event", None)
            if callable(fn):
                fn()
        except Exception as e:
            logger.warning(f"[MyCat] stop_event() 失败: {e}")
        try:
            event._has_send_oper = True
        except Exception:
            pass

    def _lock_for(self, key: str) -> asyncio.Lock:
        k = str(key or "default")
        lock = self._locks.get(k)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[k] = lock
        return lock

    #解析身份
    def _qq(self, event: AstrMessageEvent) -> str:
        try:
            sender = getattr(getattr(event, "message_obj", None), "sender", None)
            if sender is not None and getattr(sender, "user_id", None):
                uid = str(sender.user_id)
            else:
                uid = str(event.get_sender_id())
        except Exception:
            uid = ""
        if not uid or uid in ("None", "0"):
            uid = "unknown"
        return uid

    def _nickname(self, event: AstrMessageEvent) -> str:
        try:
            sender = getattr(getattr(event, "message_obj", None), "sender", None)
            if sender is not None:
                nm = getattr(sender, "nickname", "") or getattr(sender, "card", "")
                if nm:
                    return str(nm).replace("\n", " ").strip()
            return str(event.get_sender_name() or "用户")
        except Exception:
            return "用户"

    def _group_id(self, event: AstrMessageEvent):
        gid = None
        try:
            gid = event.get_group_id()
        except Exception:
            gid = None

        if not gid:
            mo = getattr(event, "message_obj", None)
            for attr in ("group_id", "groupId"):
                v = getattr(mo, attr, None)
                if v:
                    gid = v
                    break

        if isinstance(gid, str) and gid.strip() in ("", "None", "0"):
            return None
        return gid

    def _group_name(self, event: AstrMessageEvent, group_id) -> str:
        gid = str(group_id) if group_id else ""
        name = ""

        for obj in (event, getattr(event, "message_obj", None)):
            if obj is None:
                continue
            for attr in ("group_name", "groupName"):
                v = getattr(obj, attr, None)
                if v and str(v).strip():
                    name = str(v).strip()
                    break
            if name:
                break

        if not name:
            grp = getattr(getattr(event, "message_obj", None), "group", None)
            if grp is not None:
                for attr in ("name", "group_name", "groupName"):
                    v = getattr(grp, attr, None)
                    if v and str(v).strip():
                        name = str(v).strip()
                        break

        if name:
            self._cache_group(gid, name)
            return name

        cached = self._group_names.get(gid)
        if cached:
            return str(cached)

        return f"群号{gid}" if gid else "未知群"

    def _cache_group(self, gid: str, name: str):
        name = str(name).strip()
        if not gid or not name:
            return
        old = self._group_names.get(gid)
        if old == name:
            return

        self._group_names[gid] = name
        _save_json(self.groups_path, self._group_names)

        legacy = old if (old and str(old).startswith("群号")) else f"群号{gid}"
        if legacy and legacy != name:
            old_dir = group_dir(self.base_dir, legacy)
            new_dir = group_dir(self.base_dir, name)
            try:
                if os.path.isdir(old_dir) and not os.path.exists(new_dir):
                    os.replace(old_dir, new_dir)
                    logger.info(f"[MyCat] 群目录迁移: {old_dir} -> {new_dir}")
            except Exception as e:
                logger.warning(f"[MyCat] 群目录迁移失败: {e}")

    def _umo(self, event: AstrMessageEvent) -> str:
        return (getattr(event, "unified_msg_origin", None)
                or getattr(event, "session_id", None) or "")

    def _remember_session(self, event: AstrMessageEvent):
        umo = self._umo(event)
        if not umo:
            return
        qq = self._qq(event)
        gid = self._group_id(event)
        keys = [f"qq:{qq}"]
        if gid:
            keys.append(f"group:{self._group_name(event, gid)}")
        changed = False
        for k in keys:
            if self._sessions.get(k) != umo:
                self._sessions[k] = umo
                changed = True
        if changed:
            _save_json(self.sessions_path, self._sessions)

    #写入
    def record_message(self, event: AstrMessageEvent, content: str, date: str = None):
        qq = self._qq(event)
        nick = self._nickname(event)
        gid = self._group_id(event)
        date = date or get_now().strftime("%Y-%m-%d")
        line = _fmt_line(nick, content)
        written = []

        if gid:
            gname = self._group_name(event, gid)
            targets = [
                ("群公共", group_log_path(self.base_dir, gname, date)),
                ("个人群聊", user_grp_log_path(self.base_dir, qq, gname)),
            ]
        else:
            gname = ""
            targets = [("个人私聊", user_pm_log_path(self.base_dir, qq, date))]

        for label, path in targets:
            try:
                _append_line(path, line)
                written.append(path)
                logger.info(f"[MyCat] 用户消息已保存({label}): {os.path.abspath(path)}")
            except Exception as e:
                logger.error(
                    f"[MyCat] 用户消息写入失败({label}): {os.path.abspath(path)} "
                    f"-> {type(e).__name__}: {e}\n{traceback.format_exc()}"
                )
        return qq, gname, nick, written

    @staticmethod
    def _last_line_is_bot_text(path: str, text: str) -> bool:
        try:
            if not os.path.isfile(path):
                return False
            lines = _read_lines(path)
            return bool(lines) and lines[-1].endswith(f"] [{BOT_NAME}]: {text}")
        except Exception:
            return False

    def record_bot_reply(self, qq: str, gname: str, text: str, date: str = None, dedupe: bool = False):
        text = (text or "").strip()
        if not text:
            logger.error("[MyCat] 团子回复为空，跳过落盘")
            return []

        qq = qq or "unknown"
        date = date or get_now().strftime("%Y-%m-%d")
        line = _fmt_line(BOT_NAME, text)

        if gname:
            targets = [
                ("群公共", group_log_path(self.base_dir, gname, date)),
                ("个人群聊", user_grp_log_path(self.base_dir, qq, gname)),
            ]
        else:
            targets = [("个人私聊", user_pm_log_path(self.base_dir, qq, date))]

        written = []
        for label, path in targets:
            if dedupe and self._last_line_is_bot_text(path, text):
                logger.info(f"[MyCat] 回复已存在({label})，跳过重复写入: {os.path.abspath(path)}")
                written.append(path)
                continue
            try:
                _append_line(path, line)
                written.append(path)
                logger.info(f"[MyCat] 团子回复已保存({label}): {os.path.abspath(path)}")
            except Exception as e:
                logger.error(
                    f"[MyCat] 团子回复写入失败({label}): {os.path.abspath(path)} "
                    f"-> {type(e).__name__}: {e}\n{traceback.format_exc()}"
                )
                try:
                    _append_line(path, line)
                    written.append(path)
                    logger.info(f"[MyCat] 团子回复重试成功({label}): {os.path.abspath(path)}")
                except Exception as e2:
                    logger.error(f"[MyCat] 团子回复重试仍失败({label}): {e2}")

        if not written:
            logger.error(f"[MyCat] 团子回复一条都没写成功！qq={qq} gname={gname!r}")
        return written

    #上下文
    def build_context(self, qq: str, gname: str, nickname: str, content: str, date: str = None):
        date = date or get_now().strftime("%Y-%m-%d")
        fp = group_log_path(self.base_dir, gname, date) if gname \
            else user_pm_log_path(self.base_dir, qq, date)

        lines = []
        if os.path.isfile(fp):
            try:
                lines = [l for l in _read_lines(fp) if l.strip()][-CONTEXT_MAX_LINES:]
            except Exception as e:
                logger.error(f"[MyCat] 读取上下文失败 {fp}: {e}")
                lines = []

        ctx = _parse_ctx_lines(lines)

        cur = f"[{nickname}] {content}"
        if ctx and ctx[-1]["role"] == "user" and ctx[-1]["content"] == cur:
            ctx.pop()

        ctx.append({"role": "user", "content": cur})
        ctx = ctx[-MAX_HISTORY:]

        sys_extra = ""
        prof = os.path.join(user_root(self.base_dir, qq), F_PROFILE)
        comm = os.path.join(user_root(self.base_dir, qq), F_COMMITMENTS)
        if os.path.isfile(prof):
            try:
                sys_extra += "\n\n[关于这位用户的画像]\n" + "\n".join(_read_lines(prof)[-15:])
            except Exception:
                pass
        if os.path.isfile(comm):
            try:
                sys_extra += "\n\n[待兑现的约定]\n" + "\n".join(_read_lines(comm)[-10:])
            except Exception:
                pass
        return ctx, sys_extra

    #@判定。。。别改，这个已经试过很多遍最后这样子才可以过
    async def _bot_ids(self, event: AstrMessageEvent):
        ids = set()

        for holder in (event, getattr(event, "message_obj", None)):
            if holder is None:
                continue
            for attr in ("self_id", "selfId", "bot_id", "account_id"):
                v = getattr(holder, attr, None)
                if v and str(v) not in ("None", "0"):
                    ids.add(str(v))

        fn = getattr(event, "get_self_id", None)
        if callable(fn):
            try:
                v = fn()
                if inspect.isawaitable(v):
                    v = await v
                if v and str(v) not in ("None", "0"):
                    ids.add(str(v))
            except Exception:
                pass

        if BOT_QQ_ID:
            ids.add(str(BOT_QQ_ID))

        return ids

    def _collect_segments(self, event: AstrMessageEvent):
        cands = []

        for name in ("get_messages", "get_message_chain", "get_message"):
            fn = getattr(event, name, None)
            if callable(fn):
                try:
                    cands.append(fn())
                except Exception:
                    pass

        mo = getattr(event, "message_obj", None)
        if mo is not None:
            cands.append(getattr(mo, "message", None))
            cands.append(getattr(mo, "message_chain", None))

        for c in cands:
            if c is None:
                continue
            if isinstance(c, str):
                continue
            try:
                lst = list(c)
            except Exception:
                continue
            if lst:
                return lst
        return []

    @staticmethod
    async def _seg_is_at_to(seg, bot_ids) -> bool:
        if isinstance(seg, str):
            for t in _at_targets_in_text(seg):
                if t.lower() in ("all", "所有人", "全体成员"):
                    return True
                if not bot_ids or t in bot_ids:
                    return True
            return False

        cls_name = ""
        stype = ""
        data = {}
        target = ""

        if isinstance(seg, dict):
            stype = str(seg.get("type", "") or "").lower()
            d = seg.get("data")
            if isinstance(d, dict):
                data = d
            target = str(seg.get("qq") or seg.get("user_id") or "")
        else:
            cls_name = seg.__class__.__name__.lower()
            t = getattr(seg, "type", "")
            stype = str(getattr(t, "value", t) or "").lower()
            d = getattr(seg, "data", None)
            if isinstance(d, dict):
                data = d
            target = str(getattr(seg, "qq", "") or getattr(seg, "user_id", "") or "")

        if not target and isinstance(data, dict):
            target = str(data.get("qq") or data.get("user_id") or data.get("uin") or "")

        if (not target) or (stype not in ("at", "mention") and cls_name not in ("at", "mention")):
            td = getattr(seg, "to_dict", None)
            if callable(td):
                try:
                    dd = td()
                    if inspect.isawaitable(dd):
                        dd = await dd
                    if isinstance(dd, dict):
                        stype = stype or str(dd.get("type", "") or "").lower()
                        dd_data = dd.get("data") if isinstance(dd.get("data"), dict) else {}
                        if not target:
                            target = str(dd.get("qq") or dd.get("user_id") or
                                         dd_data.get("qq") or dd_data.get("user_id") or "")
                except Exception as e:
                    logger.debug(f"[MyCat] to_dict 解析失败: {e}")

        is_at = (stype in ("at", "mention")) or (cls_name in ("at", "mention"))
        if not is_at:
            return False

        if target in ("all", "所有人", "全体成员"):
            return True
        if not bot_ids:
            return True
        return target in bot_ids

    async def _is_addressed_to_me(self, event: AstrMessageEvent, content: str) -> bool:
        raw = content or ""
        reasons = []
        bot_ids = await self._bot_ids(event)

        if BOT_NAME and BOT_NAME in raw:
            reasons.append("文本含昵称")

        for bid in bot_ids:
            if re.search(rf"(?:@|\[at[:：]\s*|\[cq:at,qq=){re.escape(bid)}(?!\d)",
                         raw, re.I):
                reasons.append(f"@机器人({bid})")
                break

        for r in (re.compile(r"\[at[:：]\s*([0-9]+)(?!\d)", re.I),
                  re.compile(r"\[cq:at,qq=([0-9]+)(?!\d)", re.I)):
            done = False
            for m in r.finditer(raw):
                qq = m.group(1)
                if not bot_ids or qq in bot_ids:
                    reasons.append(f"At标记({qq})")
                    done = True
                    break
            if done:
                break

        segs = self._collect_segments(event)
        for seg in segs:
            try:
                if await self._seg_is_at_to(seg, bot_ids):
                    reasons.append(f"消息段({type(seg).__name__}).type={getattr(seg,'type',None)!r}")
                    break
            except Exception as e:
                logger.debug(f"[MyCat] 段判定异常: {e}")

        if not reasons:
            for seg in segs:
                try:
                    s = str(seg)
                except Exception:
                    continue
                for qq in _at_targets_in_text(s):
                    if not bot_ids or qq in bot_ids:
                        reasons.append(f"段字符串({qq})")
                        break
                if reasons:
                    break

        ok = bool(reasons)
        logger.info(
            f"[MyCat] @判定 | bot_ids={sorted(bot_ids) or '无'} | 段数={len(segs)} | "
            f"结果={ok}({'/'.join(reasons) or '无'}) | raw={raw[:40]!r}"
        )
        if not ok:
            dump = []
            for i, s in enumerate(segs[:6]):
                try:
                    dump.append(f"[{i}]{type(s).__name__}(type={getattr(s,'type',None)!r},"
                                f"qq={getattr(s,'qq',None)!r},data={getattr(s,'data',None)!r},"
                                f"str={str(s)[:40]!r})")
                except Exception:
                    dump.append(f"[{i}]{type(s).__name__}")
            if dump:
                logger.info("[MyCat] 消息段明细: " + " | ".join(dump))
        return ok

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        try:
            if not self._get_extra(event, "mycat_handled", False):
                return
            if (event.message_str or "").strip().startswith(("/", "／")):
                return

            result = event.get_result()
            text = self._chain_text(result)
            if not text:
                return

            logged = self._get_extra(event, "mycat_logged_text", "")
            if logged and text == logged:
                return

            qq = self._get_extra(event, "mycat_qq", "") or self._qq(event)
            gname = self._get_extra(event, "mycat_gname", "")
            date = self._get_extra(event, "mycat_date", "") or get_now().strftime("%Y-%m-%d")

            logger.info(f"[MyCat] 补记最终发送内容（来源=底层管线）: {text[:40]!r}")
            self.record_bot_reply(qq, gname, text, date=date, dedupe=True)
            self._set_extra(event, "mycat_logged_text", text)
        except Exception as e:
            logger.error(f"[MyCat] on_decorating_result 记录失败: {e}\n{traceback.format_exc()}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        raw_content = (event.message_str or "").strip()
        if not raw_content or raw_content.startswith(("/", "／")):
            return

        if raw_content.lower() in ("cat_status", "cat status"):
            self._claim_event(event)
            qq = self._qq(event)
            gid = self._group_id(event)
            gname = self._group_name(event, gid) if gid else "(私聊)"
            yield event.plain_result(
                f"【状态】QQ: {qq} | 群聊: {gname} | gid: {gid} | 运行中（未调用大模型）"
            )
            return

        now = get_now()
        today = now.strftime("%Y-%m-%d")

        qq = self._qq(event)
        gid = self._group_id(event)

        if OWNER_QQ and not gid and str(qq) != str(OWNER_QQ):
            logger.info(f"[MyCat] 非白名单私聊，已拦截 | qq={qq}")
            self._claim_event(event)
            return

        if gid:
            gname = self._group_name(event, gid)
            addressed = await self._is_addressed_to_me(event, raw_content)
            logger.info(f"[MyCat-调试] 群消息 | gid={gid} gname={gname!r} "
                        f"addressed={addressed} qq={qq} content={raw_content!r}")
        else:
            gname = ""
            addressed = True
            logger.info(f"[MyCat-调试] 私聊 | qq={qq} content={raw_content!r}")

        content = _strip_at_markers(raw_content)
        if not gid and BOT_NAME in content:
            content = re.sub(rf"^\s*{re.escape(BOT_NAME)}[\s,，:：]*", "", content).strip()
        if not content:
            content = raw_content

        if f"qq:{qq}" in SKIP_USERS:
            self._claim_event(event)
            return

        await self._boot()
        self._remember_session(event)

        nickname = self._nickname(event)

        self._set_extra(event, "mycat_handled", True)
        self._set_extra(event, "mycat_qq", qq)
        self._set_extra(event, "mycat_gname", gname)
        self._set_extra(event, "mycat_date", today)

        #避峰时段
        if _in_avoid_window(now):
            if AVOID_RECORD_ONLY:
                try:
                    self.record_message(event, content, date=today)
                    logger.info(f"[MyCat] 避峰时段({now.strftime('%H:%M')})，只记录不回复: {content[:30]!r}")
                except Exception:
                    logger.error(f"[MyCat] 避峰时段落盘异常:\n{traceback.format_exc()}")
            else:
                logger.info("[MyCat] 避峰时段且 AVOID_RECORD_ONLY=False，直接丢弃不记录")
            self._claim_event(event)
            return

        if gid and not addressed:
            if GROUP_STORE_ALL:
                try:
                    self.record_message(event, content, date=today)
                except Exception:
                    logger.error(f"[MyCat] 用户消息落盘异常:\n{traceback.format_exc()}")
                logger.info("[MyCat] 群消息已记录，未呼叫团子，不回复")
            else:
                logger.info("[MyCat] 群消息未被呼叫，按配置不记录")
            self._claim_event(event)
            return

        #并发
        lock = self._lock_for(f"group:{gid}" if gid else f"pm:{qq}")
        try:
            await asyncio.wait_for(lock.acquire(), timeout=QUEUE_LOCK_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[MyCat] 排队等锁超时({QUEUE_LOCK_TIMEOUT}s)，先回占位话术 | qq={qq} gname={gname!r}")
            self._claim_event(event)
            yield event.plain_result(BUSY_REPLY)
            return

        try:
            try:
                self.record_message(event, content, date=today)
            except Exception:
                logger.error(f"[MyCat] 用户消息落盘异常:\n{traceback.format_exc()}")

            ctx, sys_extra = self.build_context(qq, gname, nickname, content, date=today)

            final_sys = BASE_SYSTEM_PROMPT + f"\n\n[SYSTEM INFO]\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            if gname:
                final_sys += f"\n当前是群聊「{gname}」，和你说话的是成员「{nickname}」。"
            else:
                final_sys += f"\n当前是私聊，和你说话的是「{nickname}」。"
            final_sys += sys_extra
            final_sys += _wind_down_hint(now)

            try:
                raw_reply = await self._llm(ctx, system_prompt=final_sys,
                                            func_tool=self._tool_set,
                                            temperature=0.9)
            except Exception as e:
                logger.error(f"[MyCat] LLM 调用异常，改发兜底话术: {e}\n{traceback.format_exc()}")
                raw_reply = ""

            reply = sanitize_reply(raw_reply)
            if not reply:
                reply = (EMPTY_REPLY_FALLBACK or "").strip() or "喵…刚才走神了，主人再说一遍好不好？"
                logger.warning(f"[MyCat] 未拿到有效文本，改用兜底话术发送: {reply!r} "
                               f"| raw={(raw_reply or '')[:60]!r}")
            elif reply != (raw_reply or "").strip():
                logger.info(f"[MyCat] 回复已清洗: {(raw_reply or '')[:60]!r} -> {reply[:60]!r}")

            written = self.record_bot_reply(qq, gname, reply, date=today)
            if not written:
                logger.error(f"[MyCat] 团子回复未落盘，但仍会发送 | qq={qq} gname={gname!r}")

            self._set_extra(event, "mycat_logged_text", reply)
            self._claim_event(event)
            yield event.plain_result(reply)
        finally:
            lock.release()

    #工具/MCP/定时
    def _tool_ctx(self, event):
        gid = self._group_id(event)
        return self._qq(event), (self._group_name(event, gid) if gid else "")

    @llm_tool(name="query_summary")
    async def tool_query_summary(self, event: AstrMessageEvent, count: int = 3):
        '''查最近的聊天总结（私聊总结 / 当前群总结）。

        Args:
            count(number): 返回几条，默认 3
        '''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "query_summary", {"count": count})

    @llm_tool(name="query_date")
    async def tool_query_date(self, event: AstrMessageEvent, date: str):
        '''查某个具体日期的聊天记录。

        Args:
            date(string): 日期，格式 YYYY-MM-DD
        '''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "query_date", {"date": date})

    @llm_tool(name="query_recent")
    async def tool_query_recent(self, event: AstrMessageEvent, days: int = 3):
        '''查最近几天的聊天记录（私聊 + 当前群）。

        Args:
            days(number): 最近几天，默认 3
        '''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "query_recent", {"days": days})

    @llm_tool(name="query_all_summary")
    async def tool_query_all_summary(self, event: AstrMessageEvent):
        '''查全局画像、约定和各类总结。'''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "query_all_summary", {})

    @llm_tool(name="search_history")
    async def tool_search_history(self, event: AstrMessageEvent,
                                  scope: str = "all", days: int = 7, keyword: str = ""):
        '''按范围检索历史记录。group=只看当前群公共记录；self=只看这位用户自己的私聊和群内发言；all=都要。

        Args:
            scope(string): group / self / all，默认 all
            days(number): 往前查几天，默认 7，最多 60
            keyword(string): 可选关键词过滤
        '''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "search_history",
                            {"scope": scope, "days": days, "keyword": keyword})

    @llm_tool(name="query_profile")
    async def tool_query_profile(self, event: AstrMessageEvent):
        '''查这位用户的画像和约定（全局记忆）。'''
        qq, gname = self._tool_ctx(event)
        return execute_tool(self.base_dir, qq, gname, "query_profile", {})

    @llm_tool(name="web_search")
    async def tool_web_search(self, event: AstrMessageEvent, query: str, count: int = 5):
        '''联网搜索实时信息（天气、新闻、百科等）。

        Args:
            query(string): 搜索词
            count(number): 返回几条，默认 5
        '''
        return await self._web_search(query, _clamp_int(count, 5, 1, 10))

    def _mcp_launch_cmd(self):
        cmd = list(MCP_COMMAND)
        if not cmd:
            return None
        exe = shutil.which(cmd[0])
        if exe:
            cmd[0] = exe
        elif os.path.sep in cmd[0] and os.path.exists(cmd[0]):
            pass
        else:
            return None
        if os.name == "nt" and cmd[0].lower().endswith((".cmd", ".bat")):
            cmd = ["cmd", "/c"] + cmd
        return cmd

    async def _mcp_send(self, proc, obj):
        proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        await proc.stdin.drain()

    async def _mcp_read(self, proc, want_id=None, timeout=MCP_TIMEOUT):
        end = time.time() + timeout
        while True:
            remain = end - time.time()
            if remain <= 0:
                raise RuntimeError("MCP 响应超时")
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remain)
            except asyncio.TimeoutError:
                raise RuntimeError("MCP 响应超时")
            if not line:
                raise RuntimeError("MCP 进程退出")
            s = line.decode("utf-8", "replace").strip()
            if not s or not s.startswith("{"):
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if want_id is not None and str(obj.get("id")) != str(want_id):
                continue
            return obj

    @staticmethod
    def _content_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, (list, tuple)):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(str(c.get("text") or c.get("content") or c))
                else:
                    parts.append(str(c))
            return "\n".join(parts)
        if isinstance(content, dict):
            return str(content.get("text") or content.get("content") or content)
        return str(content)

    @classmethod
    def _mcp_result_text(cls, res):
        if res is None:
            return ""
        if isinstance(res, str):
            return res
        if isinstance(res, dict):
            if res.get("error"):
                return f"MCP 报错：{res['error']}"
            if "result" in res:
                return cls._mcp_result_text(res["result"])
            if "content" in res:
                return cls._content_text(res["content"])
            for k in ("text", "answer", "message", "data"):
                if res.get(k):
                    return cls._mcp_result_text(res[k])
            return json.dumps(res, ensure_ascii=False)[:1500]
        if isinstance(res, (list, tuple)):
            return cls._content_text(res)
        return str(res)[:1500]

    @staticmethod
    def _pick_tool(tools):
        if not tools:
            return None
        if MCP_TOOL_NAME:
            for t in tools:
                if (t.get("name") or "") == MCP_TOOL_NAME:
                    return t
        for kw in ("search", "baidu", "web", "query"):
            for t in tools:
                if kw in (t.get("name") or "").lower():
                    return t
        return tools[0]

    @staticmethod
    def _build_args(schema, query, count):
        props = (schema or {}).get("properties") or {}
        args = {}
        for k in ("query", "q", "keyword", "kw", "word", "searchQuery", "search_query", "text"):
            if k in props:
                args[k] = query
                break
        else:
            if props:
                args[list(props)[0]] = query
            else:
                args["query"] = query
        for k in ("maxResult", "maxResults", "max_results", "count", "num", "limit",
                  "top_k", "topK", "size"):
            if k in props:
                args[k] = count
                break
        return args

    async def _mcp_stdio_search(self, query, count):
        cmd = self._mcp_launch_cmd()
        if not cmd:
            raise RuntimeError(f"找不到命令 {MCP_COMMAND[0]}")
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            await self._mcp_send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "mycat", "version": PLUGIN_VERSION}}})
            await self._mcp_read(proc, want_id=1)
            await self._mcp_send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            await self._mcp_send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listed = await self._mcp_read(proc, want_id=2)
            tools = (((listed or {}).get("result") or {}).get("tools")) or []
            tool = self._pick_tool(tools)
            if not tool:
                raise RuntimeError("工具列表为空")
            tool_name = tool.get("name")
            schema = tool.get("inputSchema") or tool.get("input_schema") or {}
            self._mcp_tool, self._mcp_schema = tool_name, schema
            args = self._build_args(schema, query, count)
            await self._mcp_send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": tool_name, "arguments": args}})
            res = await self._mcp_read(proc, want_id=3)
            text = self._mcp_result_text(res)
            if not text:
                raise RuntimeError("工具返回空")
            return text
        finally:
            try:
                proc.kill()
            except Exception:
                pass

    async def _mcp_cli_search(self, query, count):
        cmd = self._mcp_launch_cmd()
        if not cmd:
            raise RuntimeError("找不到命令")
        cmd = cmd + ["search", query, "--max", str(count)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=MCP_TIMEOUT)
        finally:
            try:
                proc.kill()
            except Exception:
                pass
        text = (out or b"").decode("utf-8", "replace").strip() \
            or (err or b"").decode("utf-8", "replace").strip()
        if not text:
            raise RuntimeError("CLI 没有任何输出")
        return text

    def _mcp_candidates(self):
        out = []
        for attr in ("call_mcp_tool", "call_tool", "invoke_mcp_tool"):
            f = getattr(self.context, attr, None)
            if callable(f):
                out.append((f"context.{attr}", f))
        return out

    async def _try_astrbot_mcp(self, query, count):
        entries = self._mcp_candidates()
        if not entries:
            return None, "context 上无 MCP 入口"
        args = {"query": query, "maxResult": count}
        tool = MCP_TOOL_NAME or "search"
        shapes = [
            {"server": MCP_SERVER_NAME, "tool": tool, "args": args},
            {"server_name": MCP_SERVER_NAME, "tool_name": tool, "arguments": args},
            {"name": tool, "arguments": args},
        ]
        for _label, fn in entries:
            for sh in shapes:
                try:
                    r = fn(**sh)
                    if asyncio.iscoroutine(r):
                        r = await r
                except Exception:
                    continue
                txt = self._mcp_result_text(r)
                if txt and not txt.startswith("MCP 报错"):
                    return txt, None
        return None, "调用失败"

    async def _web_search(self, query: str, count: int = 5) -> str:
        if not WEB_SEARCH_ENABLED:
            return "网页搜索未启用。"
        query = (query or "").strip()
        if not query:
            return "搜索词为空。"
        errors = []

        if self._mcp_mode in (None, "astrbot-api"):
            try:
                text, err = await self._try_astrbot_mcp(query, count)
                if text:
                    self._mcp_mode = "astrbot-api"
                    return _trunc(text, MCP_RESULT_MAX_CHARS)
                if err:
                    errors.append(f"astrbot-api: {err}")
            except Exception as e:
                errors.append(f"astrbot-api: {e}")
            if self._mcp_mode == "astrbot-api":
                self._mcp_mode = None

        if self._mcp_mode in (None, "stdio"):
            try:
                text = await self._mcp_stdio_search(query, count)
                self._mcp_mode = "stdio"
                return _trunc(text, MCP_RESULT_MAX_CHARS)
            except Exception as e:
                errors.append(f"stdio: {e}")
            if self._mcp_mode == "stdio":
                self._mcp_mode = None

        if self._mcp_mode in (None, "cli"):
            try:
                text = await self._mcp_cli_search(query, count)
                self._mcp_mode = "cli"
                return _trunc(text, MCP_RESULT_MAX_CHARS)
            except Exception as e:
                errors.append(f"cli: {e}")
            if self._mcp_mode == "cli":
                self._mcp_mode = None

        return "搜索失败：" + "；".join(errors)[:400]

    #定时
    def _all_users(self):
        d = os.path.join(self.base_dir, "chats")
        if not os.path.isdir(d):
            return []
        return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))

    def _all_groups(self):
        return [n for n in self._all_users() if n.startswith(P_GRP)]

    def _all_qqs(self):
        return [n[len(P_USER):] for n in self._all_users() if n.startswith(P_USER)]

    @staticmethod
    def _tail_dir(folder: str, max_files: int, max_lines: int) -> str:
        if not os.path.isdir(folder):
            return ""
        files = sorted(f for f in os.listdir(folder)
                       if f.endswith(".txt") and _is_date_file(f))[-max_files:]
        out = []
        for fn in files:
            try:
                out.extend(l for l in _read_lines(os.path.join(folder, fn)) if l.strip())
            except Exception:
                pass
        return "\n".join(out[-max_lines:])

    async def run_greet(self):
        cands = []
        for qq in self._all_qqs():
            pm = user_pm_dir(self.base_dir, qq)
            last = _last_time_in_dir(pm)
            if last is None:
                continue
            if GREET_SKIP_RECENT_HOURS > 0:
                mins = (get_now().replace(tzinfo=None) - last).total_seconds() / 60
                if mins < GREET_SKIP_RECENT_HOURS * 60:
                    continue
            if not self._sessions.get(f"qq:{qq}"):
                continue
            cands.append(qq)

        if not cands:
            logger.info("[MyCat] 没有合适的打招呼对象")
            return

        picked = random.sample(cands, min(len(cands), random.choice([1, 2])))
        for i, qq in enumerate(picked):
            if i:
                await asyncio.sleep(random.uniform(3, 8))
            recent = self._tail_dir(user_pm_dir(self.base_dir, qq), 2, 30)
            style = random.choice(GREET_STYLES)
            prompt = (f"根据以下聊天记录，生成一条猫娘风格的问候，1句话，自然一点，"
                      f"像很久没聊突然打招呼。{style}。只输出这一句话。\n\n聊天记录：\n{recent}")
            try:
                greeting = sanitize_reply(self._one_line(
                    await self._llm([{"role": "user", "content": prompt}],
                                    system_prompt=BASE_SYSTEM_PROMPT, temperature=0.9)))
            except Exception as e:
                logger.error(f"[MyCat] 打招呼生成失败 {qq}: {e}")
                continue
            if not greeting:
                continue
            if await self._send(f"qq:{qq}", greeting):
                self.record_bot_reply(qq, "", greeting)

    async def run_daily_summary(self, date: str = None):
        today = date or get_now().strftime("%Y-%m-%d")
        logger.info(f"[MyCat] 日总结开始（{today}）")

        for gdir_name in self._all_groups():
            gdir = os.path.join(self.base_dir, "chats", gdir_name)
            await self._summarize_file(
                key=f"{gdir_name}|{today}",
                log_path=os.path.join(gdir, GRP_LOG_PREFIX + today + ".txt"),
                out_path=os.path.join(gdir, F_SUMMARY),
                date=today, mode="plain", member="群公共")

        for qq in self._all_qqs():
            pm = user_pm_dir(self.base_dir, qq)
            data = await self._summarize_file(
                key=f"{P_USER}{qq}|{D_PM}|{today}",
                log_path=os.path.join(pm, today + ".txt"),
                out_path=os.path.join(pm, F_SUMMARY),
                date=today, mode="plain", member="个人私聊")
            if data:
                root = user_root(self.base_dir, qq)
                self._append_unique(root, F_PROFILE, today, data.get("facts") or [])
                self._append_unique(root, F_COMMITMENTS, today, data.get("commitments") or [])

        for qq in self._all_qqs():
            ugrp = user_grp_dir(self.base_dir, qq)
            if not os.path.isdir(ugrp):
                continue
            for fn in sorted(os.listdir(ugrp)):
                if not fn.endswith(".txt") or fn.startswith("summary_"):
                    continue
                gname = fn[:-4]
                data = await self._summarize_file(
                    key=f"{P_USER}{qq}|{D_GRP}|{gname}|{today}",
                    log_path=os.path.join(ugrp, fn),
                    out_path=os.path.join(ugrp, f"summary_{gname}.txt"),
                    date=today, mode="by_date", member=f"群{gname}")
                if data:
                    root = user_root(self.base_dir, qq)
                    self._append_unique(root, F_PROFILE, today,
                                        [f"(群{gname}) {x}" for x in (data.get("facts") or [])])
                    self._append_unique(root, F_COMMITMENTS, today,
                                        [f"(群{gname}) {x}" for x in (data.get("commitments") or [])])

        _save_json(self.state_path, self.state)
        logger.info("[MyCat] 日总结结束")

    async def _summarize_file(self, key, log_path, out_path, date, mode, member):
        if not os.path.isfile(log_path):
            return None
        try:
            lines = _read_lines(log_path)
        except Exception as e:
            logger.error(f"[MyCat] 读取失败 {log_path}: {e}")
            return None

        if mode == "by_date":
            lines = [l for l in lines if l.startswith(f"[{date} ")]

        done = int(self.state.get(key, 0))
        #水位越界自愈
        if done < 0 or done > len(lines):
            logger.warning(f"[MyCat] 水位越界({done} > {len(lines)})，重置为 0：{key}")
            done = 0
        new_lines = [l for l in lines[done:] if l.strip()]
        if not new_lines:
            return None

        data = await self._extract_memory("\n".join(new_lines[-EXTRACT_MAX_LINES:]))
        if data is None:
            logger.warning(f"[MyCat] 抽取失败，水位不推进：{key}")
            return None

        if data.get("summary"):
            _append_line(out_path, f"[{date}] {data['summary']}")
        self.state[key] = len(lines)
        logger.info(f"[MyCat] {member} 总结完成（{len(new_lines)} 条）")
        return data

    def _append_unique(self, root: str, filename: str, date: str, items):
        if not items:
            return
        fp = os.path.join(root, filename)
        old = []
        if os.path.isfile(fp):
            try:
                old = _read_lines(fp)
            except Exception:
                old = []
        old_set = set(old)
        add = []
        for i in items:
            it = str(i).strip()
            if not it:
                continue
            entry = f"[{date}] {it}"
            if entry not in old_set and entry not in add:
                add.append(entry)
        if add:
            _append(fp, add)

    async def _extract_memory(self, text: str):
        try:
            raw = await self._llm(
                [{"role": "user", "content": f"{EXTRACT_PROMPT}\n\n聊天记录：\n{text}"}],
                temperature=0.3)
        except Exception as e:
            logger.error(f"[MyCat] 记忆抽取失败: {e}")
            return None

        s = (raw or "").strip()
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
            s = re.sub(r"\n?```$", "", s).strip()
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            try:
                obj = json.loads(s[i:j + 1])
                if isinstance(obj, dict):
                    return {
                        "summary": str(obj.get("summary") or "").strip(),
                        "facts": [str(x).strip() for x in (obj.get("facts") or []) if str(x).strip()][:5],
                        "commitments": [str(x).strip() for x in (obj.get("commitments") or []) if str(x).strip()][:5],
                    }
            except Exception as e:
                logger.warning(f"[MyCat] 记忆 JSON 解析失败: {e}")
        return {"summary": self._one_line(raw), "facts": [], "commitments": []}

    async def run_monthly_summary(self):
        now = get_now()
        ym = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        if not MONTH_RE.match(ym):
            return
        chats = os.path.join(self.base_dir, "chats")
        os.makedirs(chats, exist_ok=True)

        out_personal = os.path.join(chats, f"monthly_{ym}.txt")
        if not os.path.exists(out_personal):
            parts = []
            for qq in self._all_qqs():
                root = user_root(self.base_dir, qq)
                parts.extend(self._month_parts(user_pm_dir(self.base_dir, qq), ym, qq, "私聊"))
                parts.extend(self._month_parts(user_grp_dir(self.base_dir, qq), ym, qq, "群内"))
                parts.extend(self._month_parts(root, ym, qq, "画像"))
            if parts:
                summary = await self._monthly_llm(parts, ym, "个人")
                if summary:
                    _write(out_personal, f"[{ym} 个人月度总结]\n{summary.strip()}\n")
                    logger.info(f"[MyCat] 个人月度总结 -> {out_personal}")

        for gdir_name in self._all_groups():
            gdir = os.path.join(chats, gdir_name)
            gname = gdir_name[len(P_GRP):]
            out = os.path.join(gdir, f"monthly_{gname}_{ym}.txt")
            if os.path.exists(out):
                continue
            parts = self._month_parts(gdir, ym, gdir_name, "群公共")
            if not parts:
                continue
            summary = await self._monthly_llm(parts, ym, f"群「{gname}」")
            if summary:
                _write(out, f"[{ym} 群聊月度总结]\n{summary.strip()}\n")
                logger.info(f"[MyCat] 群聊月度总结 -> {out}")

    def _month_parts(self, folder: str, ym: str, who: str, label: str):
        out = []
        if not folder or not os.path.isdir(folder):
            return out
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".txt"):
                continue
            if not (fn in (F_SUMMARY, F_PROFILE, F_COMMITMENTS) or fn.startswith("summary_")):
                continue
            try:
                for l in _read_lines(os.path.join(folder, fn)):
                    if l.startswith(f"[{ym}-") or l.startswith(f"[{ym}]"):
                        out.append(f"{who}·{label}·{fn}: {l}")
            except Exception:
                pass
        return out

    async def _monthly_llm(self, parts, ym, scope):
        prompt = (f"下面是{scope}本月的聊天总结。请写一份月度总结："
                  "先用 3~5 条短句概括主要话题，最后用 1~2 句轻松收尾。")
        try:
            return await self._llm(
                [{"role": "user", "content": f"{prompt}\n\n时间范围：{ym}\n\n"
                                             + "\n".join(parts)[-8000:]}],
                temperature=0.8)
        except Exception as e:
            logger.error(f"[MyCat] 月度总结失败（{scope}）: {e}")
            return ""

    @staticmethod
    def _one_line(s: str) -> str:
        if not s:
            return ""
        for line in s.strip().splitlines():
            line = line.strip().strip('"').strip("“”").strip("'").strip()
            if line:
                return line[:ONE_LINE_MAX_CHARS]
        return ""

    #命令
    @filter.command("cat_at")
    async def cmd_at(self, event: AstrMessageEvent):
        bot_ids = await self._bot_ids(event)
        segs = self._collect_segments(event)
        lines = [
            f"message_str = {event.message_str!r}",
            f"bot_ids     = {sorted(bot_ids) or '无'}",
            f"段数        = {len(segs)}",
        ]
        for i, s in enumerate(segs):
            lines.append(f"[{i}] class={type(s).__name__}")
            for attr in ("type", "qq", "user_id", "data", "text", "name"):
                try:
                    v = getattr(s, attr, None)
                except Exception:
                    v = "<读取失败>"
                if v not in (None, ""):
                    lines.append(f"     {attr} = {v!r}")
            try:
                lines.append(f"     str  = {str(s)[:80]!r}")
            except Exception:
                pass
            td = getattr(s, "to_dict", None)
            if callable(td):
                try:
                    dd = td()
                    if inspect.isawaitable(dd):
                        dd = await dd
                    lines.append(f"     dict = {str(dd)[:160]}")
                except Exception as e:
                    lines.append(f"     dict = <失败 {e}>")
        lines.append(f"addressed = {await self._is_addressed_to_me(event, event.message_str or '')}")
        yield event.plain_result("\n".join(lines)[:2000])

    @filter.command("cat_selftest")
    async def cmd_selftest(self, event: AstrMessageEvent):
        await self._boot()
        qq = self._qq(event) or "selftest"
        gid = self._group_id(event)
        gname = self._group_name(event, gid) if gid else ""
        stamp = get_now().strftime("%H:%M:%S")
        raw = event.message_str or ""

        _, _, _, upaths = self.record_message(event, f"【自检】用户消息 {stamp}")
        wpaths = self.record_bot_reply(qq, gname, f"【自检】团子回复 {stamp}")
        bot_ids = await self._bot_ids(event)

        lines = [
            f"版本: {PLUGIN_VERSION}",
            f"插件文件: {os.path.abspath(__file__)}",
            f"qq={qq} gid={gid} gname={gname or '(私聊)'}",
            f"探测到的机器人QQ: {sorted(bot_ids) or '无'}",
            f"message_str={raw!r}",
            f"段数={len(self._collect_segments(event))}",
            f"addressed={await self._is_addressed_to_me(event, raw)}",
            f"GROUP_STORE_ALL={GROUP_STORE_ALL}",
            "",
            "用户消息:",
        ]
        for p in upaths:
            lines.append(f"  ✅ {os.path.abspath(p)}")
            lines.append(f"     末行: {self._safe_last(p)}")
        if not upaths:
            lines.append("  ❌ 未写入")

        lines.append("")
        lines.append("团子回复:")
        for p in wpaths:
            lines.append(f"  ✅ {os.path.abspath(p)}")
            lines.append(f"     末行: {self._safe_last(p)}")
        if not wpaths:
            lines.append("  ❌ 未写入")

        lines.append("")
        lines.append("期望文件数: " + ("2（群公共 + 个人群聊）" if gid else "1（个人私聊）"))
        yield event.plain_result("\n".join(lines)[:2000])

    @staticmethod
    def _safe_last(path: str) -> str:
        try:
            ls = _read_lines(path)
            return ls[-1][:120] if ls else "(空文件)"
        except Exception as e:
            return f"(读取失败: {e})"

    @filter.command("cat_status")
    async def cmd_status(self, event: AstrMessageEvent):
        await self._boot()
        qq, gname = self._tool_ctx(event)
        gid = self._group_id(event)
        info = {
            "版本": PLUGIN_VERSION,
            "插件文件": os.path.abspath(__file__),
            "数据目录": os.path.abspath(self.base_dir),
            "当前QQ": qq,
            "当前昵称": self._nickname(event),
            "当前GID": gid,
            "当前群名": gname or "(私聊)",
            "已知群名映射": self._group_names,
            "机器人QQ(探测)": sorted(await self._bot_ids(event)),
            "GROUP_STORE_ALL": GROUP_STORE_ALL,
            "OWNER_QQ(私聊白名单)": OWNER_QQ or "(未启用)",
            "避峰时段": f"周{AVOID_WEEKDAYS} {AVOID_START_HOURS}~{AVOID_END_HOURS} "
                        f"只记录={AVOID_RECORD_ONLY}",
            "定时": f"打招呼{GREET_TIME} 日总结{SUMMARY_TIME} 月总结{MONTHLY_DAY}日{MONTHLY_TIME}",
            "系统时间": get_now().strftime("%Y-%m-%d %H:%M:%S"),
            "用户目录数": len(self._all_qqs()),
            "群目录数": len(self._all_groups()),
            "tool_set": type(self._tool_set).__name__ if self._tool_set else "None",
            "MCP 策略": self._mcp_mode or "未确定",
        }
        yield event.plain_result(json.dumps(info, ensure_ascii=False, indent=1))

    @filter.command("cat_greet")
    async def cmd_greet(self, event: AstrMessageEvent):
        await self._boot()
        await self.run_greet()
        yield event.plain_result("打招呼跑完了")

    @filter.command("cat_summary")
    async def cmd_summary(self, event: AstrMessageEvent):
        await self._boot()
        await self.run_daily_summary()
        yield event.plain_result("日总结跑完了")

    @filter.command("cat_monthly")
    async def cmd_monthly(self, event: AstrMessageEvent):
        await self._boot()
        await self.run_monthly_summary()
        yield event.plain_result("月度总结跑完了")

    @filter.command("cat_memory")
    async def cmd_memory(self, event: AstrMessageEvent):
        await self._boot()
        qq, gname = self._tool_ctx(event)
        high = execute_tool(self.base_dir, qq, gname, "query_profile", {})
        mid = execute_tool(self.base_dir, qq, gname, "query_summary", {"count": 5})
        yield event.plain_result(f"【画像/约定】\n{high}\n\n【最近总结】\n{mid}")

    @filter.command("cat_search")
    async def cmd_search(self, event: AstrMessageEvent):
        await self._boot()
        q = event.message_str.replace("/cat_search", "").strip()
        if not q:
            yield event.plain_result("用法：/cat_search 苏州天气")
            return
        yield event.plain_result(f"【搜索结果】\n{(await self._web_search(q))[:1500]}")

    async def terminate(self):
        if self._clock_task:
            self._clock_task.cancel()
            try:
                await self._clock_task
            except asyncio.CancelledError:
                pass
            self._clock_task = None
        _save_json(self.state_path, self.state)
        _save_json(self.sessions_path, self._sessions)
        _save_json(self.groups_path, self._group_names)
        logger.info("[MyCat] 插件已卸载")