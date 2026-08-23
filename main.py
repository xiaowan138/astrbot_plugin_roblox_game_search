import asyncio
import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


OMNI_SEARCH_URL = "https://apis.roblox.com/search-api/omni-search"
GAME_DETAIL_URL = "https://games.roblox.com/v1/games"
GAME_VOTES_URL = "https://games.roblox.com/v1/games/votes"
GAME_ICON_URL = "https://thumbnails.roblox.com/v1/games/icons"
PLACE_TO_UNIVERSE_URL = "https://apis.roblox.com/universes/v1/places/{place_id}/universe"
PUBLIC_SERVERS_URL = "https://games.roblox.com/v1/games/{place_id}/servers/Public"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

GAME_URL_ID_PATTERN = re.compile(r"roblox\.com/games/(\d+)", re.IGNORECASE)

# Roblox 公开服务器接口只接受这几个分页大小
VALID_SERVER_PAGE_SIZES = (10, 25, 50, 100)

# 缓存哨兵：用于区分“未缓存”和“缓存了 None / 空结果”
_NOT_CACHED = object()

DEFAULT_BACKGROUND = (
    "radial-gradient(circle at top left, rgba(99, 102, 241, 0.35), transparent 28%), "
    "radial-gradient(circle at top right, rgba(16, 185, 129, 0.28), transparent 24%), "
    "linear-gradient(135deg, #111827 0%, #0f172a 52%, #111827 100%)"
)

# 预设背景:--背景=dark|light|blue|red|green|purple|default 等直接映射,免写一长串 CSS
PRESET_BACKGROUNDS = {
    "default": DEFAULT_BACKGROUND,
    "dark": DEFAULT_BACKGROUND,
    "深色": DEFAULT_BACKGROUND,
    "默认": DEFAULT_BACKGROUND,
    "none": DEFAULT_BACKGROUND,
    "light": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
    "浅色": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
    "blue": "linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%)",
    "蓝色": "linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%)",
    "red": "linear-gradient(135deg, #1f0a0a 0%, #991b1b 100%)",
    "红色": "linear-gradient(135deg, #1f0a0a 0%, #991b1b 100%)",
    "green": "linear-gradient(135deg, #052e16 0%, #15803d 100%)",
    "绿色": "linear-gradient(135deg, #052e16 0%, #15803d 100%)",
    "purple": "linear-gradient(135deg, #1e1b4b 0%, #6d28d9 100%)",
    "紫色": "linear-gradient(135deg, #1e1b4b 0%, #6d28d9 100%)",
}

# 自定义 CSS 背景允许的字符集:禁止 < > ; { } \ 等可逃逸出 <style> 的结构字符
_BACKGROUND_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " #,().%_-:/'\"\t\r\n*+=!@[]?"
)

# 消息内展示的服务器数量上限,防止配置过大生成超大图片
MAX_DISPLAY_SERVERS = 50

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 32px;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: {{ background }};
      color: #f8fafc;
    }
    .panel {
      width: 1120px;
      border-radius: 28px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.14);
      background: rgba(15, 23, 42, 0.78);
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(12px);
    }
    .hero {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 28px;
      padding: 28px;
      background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0));
    }
    .cover {
      width: 320px;
      height: 320px;
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.14);
      background: rgba(15, 23, 42, 0.9);
    }
    .cover img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .title {
      font-size: 42px;
      font-weight: 800;
      line-height: 1.1;
      margin: 0 0 14px 0;
    }
    .desc {
      font-size: 18px;
      line-height: 1.7;
      color: rgba(248, 250, 252, 0.88);
      margin: 0;
      white-space: pre-wrap;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 0 0 18px 0;
    }
    .badge {
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.1);
      font-size: 14px;
      color: rgba(248, 250, 252, 0.92);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      padding: 0 28px 24px;
    }
    .stat {
      padding: 18px 18px 16px;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .stat-label {
      font-size: 13px;
      color: rgba(248, 250, 252, 0.66);
      margin-bottom: 10px;
    }
    .stat-value {
      font-size: 24px;
      font-weight: 700;
      line-height: 1.25;
    }
    .section {
      padding: 0 28px 24px;
    }
    .section-title {
      font-size: 21px;
      font-weight: 700;
      margin: 0 0 14px 0;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    th, td {
      padding: 14px 16px;
      text-align: left;
      font-size: 15px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    th {
      color: rgba(248, 250, 252, 0.68);
      font-weight: 600;
      background: rgba(255, 255, 255, 0.03);
    }
    tr:last-child td {
      border-bottom: none;
    }
    .footer-note {
      padding: 0 28px 28px;
      font-size: 13px;
      color: rgba(248, 250, 252, 0.62);
      line-height: 1.6;
    }
    .server-unavailable {
      padding: 18px;
      border-radius: 18px;
      color: rgba(248, 250, 252, 0.72);
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
  </style>
</head>
<body>
  <div class="panel">
    <div class="hero">
      <div class="cover">
        <img src="{{ game.image_url | e }}" alt="game-icon" />
      </div>
      <div>
        <h1 class="title">{{ game.name | e }}</h1>
        <div class="badges">
          <span class="badge">开发者：{{ game.creator_name | e }}</span>
          <span class="badge">类型：{{ game.genre | e }}</span>
          <span class="badge">年龄组：{{ game.age_text | e }}</span>
          <span class="badge">好评率：{{ game.rating_text | e }}</span>
          <span class="badge">价格：{{ game.price_text | e }}</span>
          <span class="badge">在线：{{ game.playing_text | e }}</span>
          <span class="badge">公开服：{{ game.server_count_text | e }}</span>
        </div>
        <p class="desc">{{ game.description | e }}</p>
      </div>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="stat-label">开发者</div>
        <div class="stat-value">{{ game.creator_name | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">游戏类型</div>
        <div class="stat-value">{{ game.genre | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">年龄组</div>
        <div class="stat-value">{{ game.age_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">好评度</div>
        <div class="stat-value">{{ game.rating_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">当前在线人数</div>
        <div class="stat-value">{{ game.playing_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">总访问量</div>
        <div class="stat-value">{{ game.visits_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">收藏数</div>
        <div class="stat-value">{{ game.favorited_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">公开服务器统计</div>
        <div class="stat-value">{{ game.server_count_text | e }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">公开服在线总人数</div>
        <div class="stat-value">{{ game.server_players_text | e }}</div>
      </div>
    </div>

    <div class="section">
      <h2 class="section-title">公开服务器状态</h2>
      {% if game.server_data_available %}
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>状态</th>
            <th>人数</th>
            <th>延迟</th>
            <th>FPS</th>
          </tr>
        </thead>
        <tbody>
          {% for server in game.display_servers %}
          <tr>
            <td>{{ loop.index }}</td>
            <td>{{ server.status | e }}</td>
            <td>{{ server.playing | e }}/{{ server.max_players | e }}</td>
            <td>{{ server.ping_text | e }}</td>
            <td>{{ server.fps_text | e }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="server-unavailable">{{ game.server_note | e }}</div>
      {% endif %}
    </div>

    <div class="footer-note">
      {% if game.server_data_available %}{{ game.server_note | e }}<br />{% endif %}
      Roblox 链接：https://www.roblox.com/games/{{ game.root_place_id | e }}<br />
      快速加入：https://www.roblox.com/games/start?placeId={{ game.root_place_id | e }}
    </div>
  </div>
</body>
</html>
"""


class RobloxRateLimitError(RuntimeError):
    pass


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """进程内简单的 TTL 缓存：到期惰性清理，带容量上限，避免无限增长。"""

    def __init__(self, default_ttl: float, max_entries: int = 256):
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._data: dict[Any, _CacheEntry] = {}

    def get(self, key: Any, default: Any = None) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return default
        if entry.expires_at <= time.monotonic():
            del self._data[key]
            return default
        return entry.value

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        ttl_seconds = self._default_ttl if ttl is None else ttl
        if ttl_seconds <= 0:
            return  # TTL 为 0 表示禁用缓存
        if len(self._data) >= self._max_entries and key not in self._data:
            self._evict()
        self._data[key] = _CacheEntry(value, time.monotonic() + ttl_seconds)

    def _evict(self) -> None:
        now = time.monotonic()
        for key in [k for k, entry in self._data.items() if entry.expires_at <= now]:
            del self._data[key]
        if len(self._data) >= self._max_entries:
            oldest_key = min(self._data, key=lambda k: self._data[k].expires_at)
            del self._data[oldest_key]


@dataclass
class RobloxServer:
    id: str
    playing: int
    max_players: int
    ping: int | None
    fps: float | None
    status: str

    @property
    def ping_text(self) -> str:
        return f"{self.ping} ms" if self.ping is not None else "未知"

    @property
    def fps_text(self) -> str:
        return f"{self.fps:.1f}" if self.fps is not None else "未知"


@dataclass
class RobloxGame:
    universe_id: int
    root_place_id: int
    name: str
    description: str
    creator_name: str
    genre: str
    age_recommendation: str
    content_maturity: str
    minimum_age: int
    playing: int
    visits: int
    favorited: int
    price: int
    up_votes: int
    down_votes: int
    image_url: str
    servers: list[RobloxServer]
    scanned_all_servers: bool
    page_limit_hit: bool
    server_data_available: bool
    servers_skipped: bool = False

    @property
    def rating(self) -> float:
        total = self.up_votes + self.down_votes
        return (self.up_votes / total * 100.0) if total else 0.0

    @property
    def rating_text(self) -> str:
        return f"{self.rating:.1f}% ({format_number(self.up_votes)}/{format_number(self.down_votes)})"

    @property
    def playing_text(self) -> str:
        return format_number(self.playing)

    @property
    def visits_text(self) -> str:
        return format_number(self.visits)

    @property
    def favorited_text(self) -> str:
        return format_number(self.favorited)

    @property
    def price_text(self) -> str:
        return "免费" if self.price <= 0 else f"{self.price} Robux"

    @property
    def join_url(self) -> str:
        if self.root_place_id > 0:
            return f"https://www.roblox.com/games/start?placeId={self.root_place_id}"
        return ""

    @property
    def age_text(self) -> str:
        if self.age_recommendation:
            return self.age_recommendation
        if self.minimum_age > 0:
            return f"{self.minimum_age}+"
        if self.content_maturity:
            return self.content_maturity.replace("_", " ").title()
        return "未提供"

    @property
    def total_server_players(self) -> int:
        return sum(server.playing for server in self.servers)

    @property
    def server_count_text(self) -> str:
        count = format_number(len(self.servers))
        return count if self.scanned_all_servers else f"{count}+"

    @property
    def server_players_text(self) -> str:
        players = format_number(self.total_server_players)
        return players if self.scanned_all_servers else f"{players}+"


def format_number(value: int) -> str:
    return f"{value:,}"


def normalize_text(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = value.strip()
    return cleaned if cleaned else fallback


def normalize_match_text(value: str | None) -> str:
    text = normalize_text(value, "").casefold()
    text = re.sub(r"[\[\(【（].*?[\]\)】）]", " ", text)
    normalized = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(normalized.split())


def compact_match_text(value: str | None) -> str:
    return normalize_match_text(value).replace(" ", "")


def summarize_status(playing: int, max_players: int) -> str:
    if max_players <= 0:
        return "未知"
    ratio = playing / max_players
    if ratio >= 1:
        return "已满"
    if ratio >= 0.8:
        return "很满"
    if ratio >= 0.45:
        return "活跃"
    if ratio > 0:
        return "空闲"
    return "空服"


@register(
    "astrbot_plugin_roblox_game_search",
    "xiaowan",
    "通过 Roblox 游戏搜索与 Roblox 游戏ID搜索 指令查询 Roblox 游戏详情。",
    "0.3.0",
)
class RobloxGameSearchPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        timeout = float(self.config.get("request_timeout", 20))
        client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(timeout),
            "headers": {"User-Agent": "AstrBot-Roblox-Search/0.3.0"},
            "follow_redirects": True,
        }
        proxy = normalize_text(str(self.config.get("proxy", "")), "")
        if proxy:
            client_kwargs["proxy"] = proxy
        self.client = httpx.AsyncClient(**client_kwargs)
        self._request_lock = asyncio.Lock()
        self._last_request_ts = 0.0

        cache_enabled = bool(self.config.get("enable_cache", True))
        static_ttl = max(0, int(self.config.get("cache_static_ttl_seconds", 3600)))
        votes_ttl = max(0, int(self.config.get("cache_votes_ttl_seconds", 600)))
        servers_ttl = max(0, int(self.config.get("cache_servers_ttl_seconds", 180)))
        if not cache_enabled:
            static_ttl = 0
            votes_ttl = 0
            servers_ttl = 0
        self._cache_search = TTLCache(static_ttl)
        self._cache_detail = TTLCache(static_ttl)
        self._cache_votes = TTLCache(votes_ttl)
        self._cache_image = TTLCache(static_ttl)
        self._cache_age = TTLCache(static_ttl)
        self._cache_servers = TTLCache(servers_ttl)
        self._cache_place_universe = TTLCache(static_ttl)

        # 收藏夹:JSON 文件持久化,按发送者区分;路径可在测试中覆盖
        self._fav_lock = asyncio.Lock()
        self._favorites_file: str | None = None

    async def terminate(self):
        await self.client.aclose()

    @filter.command("roblox游戏搜索")
    async def roblox_game_search(self, event: AstrMessageEvent):
        async for result in self._handle_search(event, search_mode="name"):
            yield result

    @filter.command("游戏搜索")
    async def game_search(self, event: AstrMessageEvent):
        async for result in self._handle_search(event, search_mode="name"):
            yield result

    @filter.command("roblox游戏ID搜索")
    async def roblox_game_id_search(self, event: AstrMessageEvent):
        async for result in self._handle_search(event, search_mode="id"):
            yield result

    @filter.command("游戏ID搜索")
    async def game_id_search(self, event: AstrMessageEvent):
        async for result in self._handle_search(event, search_mode="id"):
            yield result

    @filter.command("roblox收藏")
    async def roblox_favorite_add(self, event: AstrMessageEvent):
        async for result in self._handle_favorite(event, action="add"):
            yield result

    @filter.command("roblox游戏收藏")
    async def roblox_favorite_add_alias(self, event: AstrMessageEvent):
        async for result in self._handle_favorite(event, action="add"):
            yield result

    @filter.command("roblox取消收藏")
    async def roblox_favorite_remove(self, event: AstrMessageEvent):
        async for result in self._handle_favorite(event, action="remove"):
            yield result

    @filter.command("roblox我的收藏")
    async def roblox_favorite_list(self, event: AstrMessageEvent):
        async for result in self._handle_favorite(event, action="list"):
            yield result

    async def _handle_search(self, event: AstrMessageEvent, search_mode: str):
        if self._is_duplicate_event(event, search_mode):
            return

        query_text = event.message_str or ""
        command_names = (
            ["roblox游戏搜索", "游戏搜索"]
            if search_mode == "name"
            else ["roblox游戏ID搜索", "游戏ID搜索"]
        )
        args = self._parse_command_args(query_text, command_names)
        query = args["query"]

        if args["help"] or not query:
            yield event.plain_result(self._usage_text(search_mode))
            return

        if args["mode_conflict"]:
            yield event.plain_result("输出模式冲突：--文本 和 --图片 只能选择其中一个，请去掉一个后重试。")
            return

        # 支持直接粘贴 Roblox 游戏链接：自动提取数字 ID 并按 ID 搜索
        url_id = self._extract_game_url_id(query)
        if url_id is not None:
            query = url_id
            search_mode = "id"

        if search_mode == "name" and query.isdigit():
            yield event.plain_result("这个指令用于按游戏名搜索。纯数字 ID 请使用 /roblox游戏ID搜索。")
            return

        if search_mode == "id" and not query.isdigit():
            yield event.plain_result("这个指令只接受纯数字 ID。游戏名请使用 /roblox游戏搜索。")
            return

        render_mode = args["mode"] or str(self.config.get("default_render_mode", "html")).lower()
        background = self._resolve_background(args["background"])
        fetch_servers = not args["compact"]
        use_cache = not args["refresh"]

        try:
            if search_mode == "name":
                game, suggestions = await self._resolve_game_by_name(
                    query, fetch_servers=fetch_servers, use_cache=use_cache
                )
            else:
                game = await self._resolve_game_by_id(
                    int(query), fetch_servers=fetch_servers, use_cache=use_cache
                )
                suggestions = []

            if not game:
                yield event.plain_result(self._not_found_text(query, suggestions))
                return

            display_servers = self._display_servers(game, args["servers"], args["sort"])

            if render_mode == "text":
                yield event.chain_result(
                    [
                        Comp.Image.fromURL(game.image_url),
                        Comp.Plain(self._render_text(game, display_servers)),
                    ]
                )
                return

            try:
                image_url = await self.html_render(
                    HTML_TEMPLATE,
                    {
                        "background": background,
                        "game": {
                            "name": game.name,
                            "image_url": game.image_url,
                            "description": game.description,
                            "creator_name": game.creator_name,
                            "genre": game.genre,
                            "age_text": game.age_text,
                            "rating_text": game.rating_text,
                            "playing_text": game.playing_text,
                            "visits_text": game.visits_text,
                            "favorited_text": game.favorited_text,
                            "price_text": game.price_text,
                            "server_count_text": game.server_count_text,
                            "server_players_text": game.server_players_text,
                            "root_place_id": game.root_place_id,
                            "server_note": self._server_note(game, display_servers),
                            "server_data_available": game.server_data_available,
                            "display_servers": [
                                {
                                    "status": server.status,
                                    "playing": server.playing,
                                    "max_players": server.max_players,
                                    "ping_text": server.ping_text,
                                    "fps_text": server.fps_text,
                                }
                                for server in display_servers
                            ],
                        },
                    },
                    options={"type": "png", "full_page": True, "animations": "disabled"},
                )
                yield event.image_result(image_url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HTML 渲染失败，已自动降级为文本模式: %s", exc)
                yield event.chain_result(
                    [
                        Comp.Image.fromURL(game.image_url),
                        Comp.Plain(self._render_text(game, display_servers)),
                    ]
                )
        except RobloxRateLimitError:
            yield event.plain_result("Roblox 接口限流了，插件已放慢请求节奏。请稍等几十秒后再试。")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Roblox 游戏搜索插件执行失败: %s", exc)
            yield event.plain_result(f"查询失败：{exc}")

    def _is_duplicate_event(self, event: AstrMessageEvent, search_mode: str) -> bool:
        raw_message = event.message_str or ""
        event_extra_key = f"roblox_game_search_handled:{search_mode}:{raw_message}"
        if event.get_extra(event_extra_key):
            return True
        event.set_extra(event_extra_key, True)
        return False

    def _extract_game_url_id(self, text: str) -> str | None:
        match = GAME_URL_ID_PATTERN.search(text or "")
        return match.group(1) if match else None

    def _not_found_text(self, query: str, suggestions: list[dict[str, Any]] | None = None) -> str:
        if re.search(r"[\u4e00-\u9fff]", query or ""):
            text = (
                "没有找到对应的 Roblox 游戏。插件已经尝试中文别名、关键词翻译和英文候选搜索，"
                "可以换一个更完整的游戏名再试。"
            )
        else:
            text = "没有找到对应的 Roblox 游戏，请检查输入后再试。"
        if suggestions:
            lines = ["", "相近候选（发送 /roblox游戏ID搜索 <ID> 查看）："]
            for index, candidate in enumerate(suggestions[:3], start=1):
                name = normalize_text(candidate.get("name"), "未知游戏")
                lines.append(f"{index}. {name}（ID: {candidate.get('root_place_id')}）")
            text += "\n".join(lines)
        return text

    def _parse_command_args(self, message: str, command_names: list[str]) -> dict[str, Any]:
        text = self._strip_command_prefix(message, command_names)

        mode = None
        background = None
        server_match = None
        compact = False
        sort_mode = "ping"
        help_requested = False
        refresh = False
        mode_conflict = False

        text_pattern = r"(?:^|\s)--?(?:文本|text)(?:\s|$)"
        html_pattern = r"(?:^|\s)--?(?:图片|html|image|img)(?:\s|$)"
        if re.search(text_pattern, text, re.IGNORECASE) and re.search(html_pattern, text, re.IGNORECASE):
            mode_conflict = True
        for pattern, value in ((text_pattern, "text"), (html_pattern, "html")):
            if re.search(pattern, text, re.IGNORECASE):
                mode = value
                text = re.sub(pattern, " ", text, flags=re.IGNORECASE).strip()

        compact_pattern = r"(?:^|\s)--?(?:简洁|compact|noservers?)(?:\s|$)"
        if re.search(compact_pattern, text, re.IGNORECASE):
            compact = True
            text = re.sub(compact_pattern, " ", text, flags=re.IGNORECASE).strip()

        help_pattern = r"(?:^|\s)(?:--?帮助|--?help|-h)(?:\s|$)"
        if re.search(help_pattern, text, re.IGNORECASE):
            help_requested = True
            text = re.sub(help_pattern, " ", text, flags=re.IGNORECASE).strip()

        refresh_pattern = r"(?:^|\s)--?(?:刷新|refresh)(?:\s|$)"
        if re.search(refresh_pattern, text, re.IGNORECASE):
            refresh = True
            text = re.sub(refresh_pattern, " ", text, flags=re.IGNORECASE).strip()

        # 只匹配已知的排序方式，避免误吞游戏名；支持 --排序=人数 与 --排序 人数 两种写法
        sort_match = re.search(
            r"--?(?:排序|sort)[= ](人数|players|空位|free|延迟|ping)",
            text,
            re.IGNORECASE,
        )
        if sort_match:
            sort_key = sort_match.group(1).lower()
            if sort_key in {"players", "人数"}:
                sort_mode = "players"
            elif sort_key in {"free", "空位"}:
                sort_mode = "free"
            else:
                sort_mode = "ping"
            text = text.replace(sort_match.group(0), " ").strip()
        else:
            # 未知的 --排序=xxx 或孤立的 --排序 也剥掉，避免污染游戏名
            text = re.sub(r"--?(?:排序|sort)=\S+", " ", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"(?:^|\s)--?(?:排序|sort)(?=\s|$)", " ", text, flags=re.IGNORECASE).strip()

        background, text = self._extract_background_option(text)

        server_match = re.search(r"--?(?:服务器数|servers?)=(\d+)", text, re.IGNORECASE)
        if server_match:
            text = text.replace(server_match.group(0), " ").strip()

        return {
            "query": normalize_text(text, ""),
            "mode": mode,
            "background": background,
            "servers": server_match.group(1) if server_match else None,
            "compact": compact,
            "sort": sort_mode,
            "help": help_requested,
            "refresh": refresh,
            "mode_conflict": mode_conflict,
        }

    @staticmethod
    def _strip_command_prefix(message: str, command_names: list[str]) -> str:
        text = re.sub(r"^/+", "", (message or "").strip())
        commands_pattern = "|".join(re.escape(command_name) for command_name in command_names)
        return re.sub(rf"^(?:{commands_pattern})", "", text, count=1).strip()

    @staticmethod
    def _sanitize_background(value: str | None) -> str | None:
        """校验自定义 CSS 背景，拒绝可逃逸出 <style> 的结构字符；非法时返回 None 走默认背景。"""
        if not value:
            return None
        if not set(value).issubset(_BACKGROUND_ALLOWED_CHARS):
            return None
        stripped = value.strip()
        return stripped or None

    def _resolve_background(self, raw: str | None) -> str:
        """解析 --背景 参数：预设名直接映射，自定义值做结构校验，非法/缺失回退到配置默认。"""
        if raw:
            preset = PRESET_BACKGROUNDS.get(raw.strip().casefold())
            if preset:
                return preset
            sanitized = self._sanitize_background(raw)
            if sanitized:
                return sanitized
        configured = str(self.config.get("html_background", DEFAULT_BACKGROUND))
        return self._sanitize_background(configured) or DEFAULT_BACKGROUND

    def _extract_background_option(self, text: str) -> tuple[str | None, str]:
        """Extract a CSS background option without consuming the game name."""
        option_match = re.search(r"(?:^|\s)--?(?:背景|bg)=", text, re.IGNORECASE)
        if not option_match:
            return None, text

        value_start = option_match.end()
        remainder = text[value_start:].lstrip()
        option_end = value_start + (len(text[value_start:]) - len(remainder))
        if not remainder:
            return None, text

        if remainder[0] in {"\"", "'"}:
            quote = remainder[0]
            closing_quote = remainder.find(quote, 1)
            if closing_quote == -1:
                return None, text
            background = remainder[1:closing_quote].strip()
            option_end += closing_quote + 1
        else:
            function_match = re.match(r"[A-Za-z-]+\(", remainder)
            if function_match:
                depth = 0
                quote: str | None = None
                escaped = False
                option_length = 0
                for index, char in enumerate(remainder):
                    if quote:
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == quote:
                            quote = None
                        continue
                    if char in {"\"", "'"}:
                        quote = char
                    elif char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0:
                            option_length = index + 1
                            break
                if not option_length:
                    return None, text
                background = remainder[:option_length].strip()
                option_end += option_length
            else:
                value_match = re.match(r"\S+", remainder)
                if not value_match:
                    return None, text
                background = value_match.group(0).strip()
                option_end += len(value_match.group(0))

        query = f"{text[:option_match.start()]} {text[option_end:]}".strip()
        return background or None, query

    def _usage_text(self, search_mode: str) -> str:
        common = (
            "可选参数：--文本 | --图片 | --简洁（跳过服务器扫描）| --排序=延迟|人数|空位 "
            "| --服务器数=N | --刷新（强制刷新缓存）| --帮助\n"
            "背景：--背景=CSS（或 dark/light/blue/red/green/purple 预设名）\n"
        )
        if search_mode == "name":
            return (
                "用法：/roblox游戏搜索 游戏名\n"
                "别名：/游戏搜索 游戏名\n"
                "支持粘贴 Roblox 游戏链接：/roblox游戏搜索 https://www.roblox.com/games/2440500124/Blox-Fruits\n"
                + common
                + "示例：/roblox游戏搜索 doors\n"
                "示例：/游戏搜索 --文本 Blox Fruits\n"
                "示例：/游戏搜索 --简洁 doors\n"
                "示例：/游戏搜索 --排序=人数 --服务器数=5 doors\n"
                "示例：/游戏搜索 --刷新 doors\n"
                "示例：/游戏搜索 --背景=blue Doors\n"
                "示例：/游戏搜索 --背景=linear-gradient(135deg,#0f172a,#1d4ed8) Doors\n"
                "复杂背景请使用引号：--背景=\"radial-gradient(...), linear-gradient(...)\" Doors\n"
                "收藏：/roblox收藏 <ID> 收藏游戏 | /roblox我的收藏 查看 | /roblox取消收藏 <ID> 移除"
            )
        return (
            "用法：/roblox游戏ID搜索 数字ID\n"
            "别名：/游戏ID搜索 数字ID\n"
            "支持粘贴 Roblox 游戏链接：/游戏ID搜索 https://www.roblox.com/games/2440500124/Blox-Fruits\n"
            + common
            + "示例：/roblox游戏ID搜索 6516141723\n"
            "示例：/游戏ID搜索 --文本 2440500124\n"
            "示例：/游戏ID搜索 --服务器数=5 2440500124\n"
            "收藏：/roblox收藏 <ID> 收藏游戏 | /roblox我的收藏 查看 | /roblox取消收藏 <ID> 移除"
        )

    async def _handle_favorite(self, event: AstrMessageEvent, action: str):
        if action == "list":
            yield event.plain_result(self._favorite_list_text(event))
            return

        command_names = ["roblox收藏", "roblox游戏收藏"] if action == "add" else ["roblox取消收藏"]
        query = self._strip_command_prefix(event.message_str or "", command_names)
        if not query:
            yield event.plain_result(self._favorite_usage_text())
            return

        url_id = self._extract_game_url_id(query)
        if url_id is not None:
            query = url_id

        if action == "remove":
            removed = await self._favorite_remove(event, query)
            if removed is True:
                yield event.plain_result("已取消收藏。")
            elif removed is False:
                yield event.plain_result("该游戏不在收藏列表中。")
            else:
                yield event.plain_result(self._favorite_usage_text())
            return

        # 收藏需要先解析出游戏（简洁模式，不扫描服务器）
        try:
            if query.isdigit():
                game = await self._resolve_game_by_id(int(query), fetch_servers=False)
            else:
                game, _ = await self._resolve_game_by_name(query, fetch_servers=False)
        except RobloxRateLimitError:
            yield event.plain_result("Roblox 接口限流了，请稍等几十秒后再试。")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("收藏操作失败: %s", exc)
            yield event.plain_result(f"操作失败：{exc}")
            return

        if not game:
            yield event.plain_result("没有找到对应的 Roblox 游戏，无法收藏。")
            return

        added = await self._favorite_add(event, game)
        yield event.plain_result(
            f"已收藏：{game.name}（ID: {game.root_place_id}）"
            if added
            else f"{game.name} 已在收藏列表中。"
        )

    def _favorite_usage_text(self) -> str:
        return (
            "用法：\n"
            "/roblox收藏 <游戏ID|游戏链接|游戏名> 收藏一个游戏\n"
            "/roblox取消收藏 <游戏ID|游戏名> 取消收藏\n"
            "/roblox我的收藏 查看收藏列表\n"
            "示例：/roblox收藏 6516141723\n"
            "/roblox收藏 doors"
        )

    @staticmethod
    def _sender_key(event: AstrMessageEvent) -> str:
        try:
            sender_id = event.get_sender_id()
            if sender_id is not None:
                return str(sender_id)
        except Exception:  # noqa: BLE001
            pass
        return "default"

    def _favorites_path(self) -> Path:
        if self._favorites_file:
            return Path(self._favorites_file)
        return Path(__file__).resolve().parent / "favorites.json"

    def _load_favorites(self) -> dict[str, Any]:
        path = self._favorites_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {}

    def _save_favorites(self, data: dict[str, Any]) -> None:
        path = self._favorites_path()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("保存收藏数据失败: %s", exc)

    async def _favorite_add(self, event: AstrMessageEvent, game: RobloxGame) -> bool:
        key = self._sender_key(event)
        async with self._fav_lock:
            data = self._load_favorites()
            entries = data.setdefault(key, [])
            for entry in entries:
                if str(entry.get("root_place_id")) == str(game.root_place_id):
                    return False
            entries.append({
                "universe_id": game.universe_id,
                "root_place_id": game.root_place_id,
                "name": game.name,
                "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            self._save_favorites(data)
            return True

    async def _favorite_remove(self, event: AstrMessageEvent, query: str) -> bool | None:
        """按 ID 或名称移除收藏。返回 True=已移除 / False=不存在 / None=参数无效。"""
        key = self._sender_key(event)
        query = query.strip()
        if not query:
            return None
        query_lower = query.casefold()
        async with self._fav_lock:
            data = self._load_favorites()
            entries = data.get(key, [])
            remaining: list[dict[str, Any]] = []
            removed_any = False
            for entry in entries:
                match_id = str(entry.get("root_place_id")) == query or str(entry.get("universe_id")) == query
                match_name = bool(query_lower) and query_lower in str(entry.get("name", "")).casefold()
                if (match_id or match_name) and not removed_any:
                    removed_any = True
                    continue
                remaining.append(entry)
            if not removed_any:
                return False
            data[key] = remaining
            self._save_favorites(data)
            return True

    def _favorite_list_text(self, event: AstrMessageEvent) -> str:
        key = self._sender_key(event)
        entries = self._load_favorites().get(key, [])
        if not entries:
            return "还没有收藏任何游戏。使用 /roblox收藏 <游戏ID> 添加。"
        lines = [f"共收藏 {len(entries)} 个游戏："]
        for index, entry in enumerate(entries, start=1):
            name = normalize_text(entry.get("name"), "未知游戏")
            root_place_id = entry.get("root_place_id")
            lines.append(f"{index}. {name}（ID: {root_place_id}）")
            if root_place_id:
                lines.append(f"   链接：https://www.roblox.com/games/{root_place_id}")
        lines.append("使用 /roblox取消收藏 <ID> 移除，或 /roblox收藏 <ID> 添加更多。")
        return "\n".join(lines)

    async def _resolve_game_by_name(
        self,
        query: str,
        fetch_servers: bool = True,
        use_cache: bool = True,
    ) -> tuple[RobloxGame | None, list[dict[str, Any]]]:
        search_hit, suggestions = await self._search_game(query.strip(), use_cache=use_cache)
        if not search_hit:
            return None, suggestions

        universe_id = int(search_hit["universe_id"])
        detail = await self._fetch_game_detail(universe_id, use_cache=use_cache)
        if not detail:
            return None, suggestions

        votes = await self._fetch_votes(universe_id, use_cache=use_cache)
        image_url = await self._fetch_image(universe_id, use_cache=use_cache)
        game = await self._build_game(
            detail,
            votes,
            image_url,
            search_hit["description"],
            search_hit,
            fetch_servers=fetch_servers,
            use_cache=use_cache,
        )
        return game, suggestions

    async def _resolve_game_by_id(
        self,
        numeric_id: int,
        fetch_servers: bool = True,
        use_cache: bool = True,
    ) -> RobloxGame | None:
        # 数字 ID 可能是 universeId 也可能是 placeId（两者数字命名空间相同、可能撞号），
        # 两个方向都解析，取更热门/更可信的那个。
        direct_detail = await self._fetch_game_detail(numeric_id, use_cache=use_cache)

        place_universe_id = await self._place_to_universe(numeric_id, use_cache=use_cache)
        place_detail = None
        if place_universe_id and place_universe_id != numeric_id:
            place_detail = await self._fetch_game_detail(place_universe_id, use_cache=use_cache)

        chosen_detail = self._pick_better_id_detail(direct_detail, place_detail)
        if chosen_detail is None:
            return None

        universe_id = int(chosen_detail.get("id", 0))
        if universe_id <= 0:
            universe_id = place_universe_id or numeric_id

        votes = await self._fetch_votes(universe_id, use_cache=use_cache)
        image_url = await self._fetch_image(universe_id, use_cache=use_cache)
        age_info = await self._fetch_age_info(
            universe_id,
            normalize_text(chosen_detail.get("name"), ""),
            use_cache=use_cache,
        )
        return await self._build_game(
            chosen_detail,
            votes,
            image_url,
            "",
            age_info,
            fetch_servers=fetch_servers,
            use_cache=use_cache,
        )

    @staticmethod
    def _pick_better_id_detail(
        direct: dict[str, Any] | None,
        indirect: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """ID 同时命中 universe 和 place 时，按热度（在线人数 > 访问量）选择更可信的。"""
        if direct is None:
            return indirect
        if indirect is None:
            return direct
        direct_pop = (int(direct.get("playing", 0) or 0), int(direct.get("visits", 0) or 0))
        indirect_pop = (int(indirect.get("playing", 0) or 0), int(indirect.get("visits", 0) or 0))
        if direct_pop >= indirect_pop:
            return direct
        return indirect

    async def _search_game(self, query: str, use_cache: bool = True) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        search_queries = await self._build_search_queries(query)
        if not search_queries:
            return None, []

        cache_key = "|".join(compact_match_text(search_query) for search_query in search_queries)
        if use_cache:
            cached = self._cache_search.get(cache_key, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached

        candidates: list[dict[str, Any]] = []
        seen_candidates: dict[str, dict[str, Any]] = {}

        for query_index, search_query in enumerate(search_queries):
            try:
                raw_candidates = await self._search_game_candidates(search_query)
            except RobloxRateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("搜索候选失败（query=%r）: %s", search_query, exc)
                raw_candidates = []
            for candidate in raw_candidates:
                candidate_key = str(candidate.get("universe_id") or candidate.get("root_place_id"))
                if not candidate_key:
                    continue

                existing = seen_candidates.get(candidate_key)
                if existing:
                    existing["result_index"] = min(
                        int(existing.get("result_index", 0)),
                        int(candidate.get("result_index", 0)),
                    )
                    existing["_best_query_index"] = min(
                        int(existing.get("_best_query_index", query_index)),
                        query_index,
                    )
                    continue

                candidate = dict(candidate)
                candidate["_best_query_index"] = query_index
                candidates.append(candidate)
                seen_candidates[candidate_key] = candidate

        best = self._pick_best_search_hit(search_queries, candidates)
        suggestions = self._pick_suggestions(search_queries, candidates, best)
        result = (best, suggestions)
        self._cache_search.set(cache_key, result)
        return result

    async def _search_game_candidates(self, query: str) -> list[dict[str, Any]]:
        params = {
            "searchQuery": query,
            "pageToken": "",
            "sessionId": str(uuid.uuid4()),
            "pageType": "all",
        }
        payload = await self._get_json(OMNI_SEARCH_URL, params=params)
        candidates: list[dict[str, Any]] = []
        index = 0
        for block in payload.get("searchResults", []):
            if block.get("contentGroupType") != "Game":
                continue
            for content in block.get("contents", []):
                universe_id = content.get("universeId") or content.get("contentId")
                root_place_id = content.get("rootPlaceId")
                if universe_id and root_place_id:
                    candidates.append({
                        "universe_id": int(universe_id),
                        "root_place_id": int(root_place_id),
                        "name": normalize_text(content.get("name"), ""),
                        "description": normalize_text(content.get("description"), "暂无简介。"),
                        "creator_name": normalize_text(content.get("creatorName"), ""),
                        "player_count": int(content.get("playerCount", 0) or 0),
                        "total_up_votes": int(content.get("totalUpVotes", 0) or 0),
                        "total_down_votes": int(content.get("totalDownVotes", 0) or 0),
                        "emphasis": bool(content.get("emphasis", False)),
                        "is_sponsored": bool(content.get("isSponsored", False)),
                        "result_index": index,
                        "age_recommendation": normalize_text(
                            content.get("ageRecommendationDisplayName"),
                            "",
                        ),
                        "content_maturity": normalize_text(content.get("contentMaturity"), ""),
                        "minimum_age": int(content.get("minimumAge", 0) or 0),
                    })
                    index += 1
        return candidates

    def _single_match_score(self, query: str, candidate: dict[str, Any]) -> float:
        query_norm = normalize_match_text(query)
        query_key = compact_match_text(query)
        query_acronym = query_key
        name = candidate.get("name", "")
        name_norm = normalize_match_text(name)
        name_key = compact_match_text(name)
        name_words = name_norm.split()
        name_acronym = "".join(word[0] for word in name_words if word)

        if query_norm and name_norm == query_norm:
            return 10000
        if query_key and name_key == query_key:
            return 9500
        if query_acronym and len(query_acronym) >= 2 and name_acronym == query_acronym:
            return 9000
        if query_norm and name_norm.startswith(query_norm):
            return 5200
        if query_key and name_key.startswith(query_key):
            return 4800
        if query_acronym and len(query_acronym) >= 2 and name_acronym.startswith(query_acronym):
            return 4600
        if query_norm and f" {query_norm} " in f" {name_norm} ":
            return 3400
        if query_key and query_key in name_key:
            return 2600
        # 模糊匹配权重按相似度比例放大，默认阈值 2200 对应相似度约 0.74：
        # 拼写相近的游戏能通过，明显无关的仍会被拒。
        # 但短词（少于 5 个字符）相似度置信度低，例如 door/Doom 相似度 0.75
        # 会误判命中，这里直接拒绝模糊分支，只保留精确/前缀/包含等强匹配。
        if len(query_norm) < 5:
            return 0
        return SequenceMatcher(None, query_norm, name_norm).ratio() * 3000

    def _match_score(self, queries: list[str], candidate: dict[str, Any]) -> float:
        return max(
            (self._single_match_score(query, candidate) for query in queries),
            default=0.0,
        )

    def _candidate_score(self, queries: list[str], candidate: dict[str, Any]) -> float:
        base = self._match_score(queries, candidate)
        if candidate.get("emphasis"):
            base += 450
        if candidate.get("is_sponsored"):
            base -= 1600

        players = max(0, int(candidate.get("player_count", 0) or 0))
        up_votes = max(0, int(candidate.get("total_up_votes", 0) or 0))
        base += min(math.log10(players + 1) * 130, 650)
        base += min(math.log10(up_votes + 1) * 70, 420)
        base -= int(candidate.get("result_index", 0)) * 2
        base -= int(candidate.get("_best_query_index", 0)) * 20
        return base

    def _pick_best_search_hit(
        self,
        queries: str | list[str],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None

        target_queries = [queries] if isinstance(queries, str) else queries
        target_queries = [normalize_text(query, "") for query in target_queries if normalize_text(query, "")]

        best = max(candidates, key=lambda candidate: self._candidate_score(target_queries, candidate))
        best_match = self._match_score(target_queries, best)
        min_match_score = float(self.config.get("name_match_min_score", 2200))
        if best_match < min_match_score:
            return None
        return best

    def _pick_suggestions(
        self,
        queries: str | list[str],
        candidates: list[dict[str, Any]],
        best: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        target_queries = [queries] if isinstance(queries, str) else queries
        target_queries = [normalize_text(query, "") for query in target_queries if normalize_text(query, "")]
        best_key = str(best.get("universe_id") or best.get("root_place_id")) if best else None

        ranked = sorted(
            candidates,
            key=lambda candidate: self._candidate_score(target_queries, candidate),
            reverse=True,
        )
        min_match_score = float(self.config.get("name_match_min_score", 2200))
        suggestion_bar = min_match_score * 0.5
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in ranked:
            key = str(candidate.get("universe_id") or candidate.get("root_place_id"))
            if not key or key == best_key or key in seen:
                continue
            if self._match_score(target_queries, candidate) < suggestion_bar:
                continue
            seen.add(key)
            suggestions.append(candidate)
            if len(suggestions) >= 3:
                break
        return suggestions

    async def _build_search_queries(self, query: str) -> list[str]:
        query_clean = normalize_text(query, "")
        cleaned_query = self._cleanup_user_search_query(query_clean)
        search_queries: list[str] = []
        seen_keys: set[str] = set()

        def add(value: str | None):
            value = normalize_text(value, "")
            if not value:
                return
            key = compact_match_text(value)
            if key in seen_keys:
                return
            seen_keys.add(key)
            search_queries.append(value)

        if self._contains_chinese(query_clean):
            for value in self._make_keyword_translation_queries(cleaned_query):
                add(value)
            for value in self._resolve_alias_queries(query_clean):
                add(value)
            for value in self._resolve_alias_queries(cleaned_query):
                add(value)

            translated_query = await self._translate_query_to_english(cleaned_query)
            for value in self._english_query_variants(translated_query):
                add(value)

            add(cleaned_query)
            add(query_clean)
        else:
            add(query_clean)
            add(cleaned_query)
            for value in self._resolve_alias_queries(query_clean):
                add(value)
            for value in self._resolve_alias_queries(cleaned_query):
                add(value)

        max_queries = max(1, int(self.config.get("max_search_queries", 6)))
        return search_queries[:max_queries]

    def _resolve_alias_queries(self, query: str) -> list[str]:
        query_clean = normalize_text(query, "")
        query_key = compact_match_text(query_clean)
        raw_aliases = {
            "史诗迷你游戏": "Epic Minigames",
            "史诗小游戏": "Epic Minigames",
            "史诗迷你小游戏": "Epic Minigames",
            "布鲁克海文": "Brookhaven",
            "布鲁克海文rp": "Brookhaven",
            "布鲁克黑文": "Brookhaven",
            "brookhaven": "Brookhaven",
            "doors": "DOORS",
            "门": "DOORS",
            "门2": "DOORS",
            "压力": "Pressure",
            "自然灾害": "Natural Disaster Survival",
            "自然灾害模拟器": "Natural Disaster Survival",
            "自然灾害生存": "Natural Disaster Survival",
            "忍者传奇": "Ninja Legends",
            "力量传奇": "Legends Of Speed",
            "速度传奇": "Legends Of Speed",
            "收养我": "Adopt Me",
            "领养我": "Adopt Me",
            "宠物模拟器": "Pet Simulator",
            "宠物模拟器99": "Pet Simulator 99",
            "蜂群模拟器": "Bee Swarm Simulator",
            "兵工厂": "Arsenal",
            "越狱": "Jailbreak",
            "杀手": "Murder Mystery 2",
            "谋杀神秘2": "Murder Mystery 2",
            "彩虹朋友": "Rainbow Friends",
            "鱿鱼游戏": "Squid Game",
            "床战": "BedWars",
            "战争大亨": "War Tycoon",
            "动漫冒险": "Anime Adventures",
            "动漫防御": "Anime Defenders",
            "水果": "Blox Fruits",
            "方块水果": "Blox Fruits",
            "恶魔果实": "Blox Fruits",
            "bloxfruit": "Blox Fruits",
            "bloxfruits": "Blox Fruits",
            "地狱塔": "Tower of Hell",
            "塔狱": "Tower of Hell",
            "餐厅大亨": "Restaurant Tycoon 2",
            "主题公园大亨": "Theme Park Tycoon 2",
            "伐木大亨2": "Lumber Tycoon 2",
            "木材大亨2": "Lumber Tycoon 2",
            "载具传奇": "Vehicle Legends",
            "矿工天堂": "Miner's Haven",
            "铁路": "Stepford County Railway",
            "火车模拟器": "Stepford County Railway",
            "scr": "Stepford County Railway",
        }
        aliases = {
            compact_match_text(alias): target
            for alias, target in raw_aliases.items()
            if compact_match_text(alias)
        }
        user_aliases = self.config.get("game_aliases", {})
        if isinstance(user_aliases, dict):
            for alias, target in user_aliases.items():
                alias_key = compact_match_text(str(alias))
                target_text = normalize_text(str(target), "")
                if alias_key and target_text:
                    aliases[alias_key] = target_text

        resolved: list[str] = []
        if query_key in aliases:
            resolved.append(aliases[query_key])
        return resolved

    def _cleanup_user_search_query(self, query: str) -> str:
        text = normalize_text(query, "")
        text = re.sub(r"(?i)\broblox\b", " ", text)
        text = text.replace("罗布乐思", " ").replace("罗布勒斯", " ")
        text = re.sub(r"[的：:，,。!！?？]+", " ", text)
        return normalize_text(" ".join(text.split()), query)

    def _contains_chinese(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

    def _make_keyword_translation_queries(self, query: str) -> list[str]:
        text = re.sub(r"\s+", "", normalize_text(query, ""))
        if not text:
            return []

        phrases = {
            "史诗迷你游戏": "Epic Minigames",
            "史诗小游戏": "Epic Minigames",
            "迷你游戏": "Minigames",
            "小游戏": "Minigames",
            "布鲁克海文": "Brookhaven",
            "布鲁克黑文": "Brookhaven",
            "自然灾害": "Natural Disaster",
            "灾害生存": "Disaster Survival",
            "宠物模拟器": "Pet Simulator",
            "主题公园": "Theme Park",
            "餐厅大亨": "Restaurant Tycoon",
            "伐木大亨": "Lumber Tycoon",
            "木材大亨": "Lumber Tycoon",
            "地狱塔": "Tower of Hell",
            "彩虹朋友": "Rainbow Friends",
            "蜂群": "Bee Swarm",
            "鱿鱼游戏": "Squid Game",
            "战争大亨": "War Tycoon",
            "动漫冒险": "Anime Adventures",
            "动漫防御": "Anime Defenders",
            "火车模拟器": "Train Simulator",
            "模拟器": "Simulator",
            "大亨": "Tycoon",
            "传奇": "Legends",
            "生存": "Survival",
            "冒险": "Adventure",
            "防御": "Defense",
            "战争": "War",
            "速度": "Speed",
            "力量": "Power",
            "水果": "Fruits",
            "方块": "Blox",
            "塔": "Tower",
            "门": "Doors",
            "铁路": "Railway",
            "火车": "Train",
            "车辆": "Vehicle",
            "载具": "Vehicle",
            "餐厅": "Restaurant",
            "主题": "Theme",
            "公园": "Park",
            "宠物": "Pet",
            "蜂": "Bee",
            "群": "Swarm",
            "忍者": "Ninja",
            "谋杀": "Murder",
            "神秘": "Mystery",
            "自然": "Natural",
            "灾害": "Disaster",
            "史诗": "Epic",
            "迷你": "Mini",
            "游戏": "Games",
        }
        phrase_keys = sorted(phrases, key=len, reverse=True)
        tokens: list[str] = []
        unknown_chinese = 0
        index = 0

        while index < len(text):
            matched_key = next((key for key in phrase_keys if text.startswith(key, index)), None)
            if matched_key:
                tokens.append(phrases[matched_key])
                index += len(matched_key)
                continue

            char = text[index]
            if char.isascii() and char.isalnum():
                end = index + 1
                while end < len(text) and text[end].isascii() and text[end].isalnum():
                    end += 1
                tokens.append(text[index:end])
                index = end
                continue

            if self._contains_chinese(char):
                unknown_chinese += 1
            index += 1

        if not tokens or unknown_chinese > max(2, len(tokens)):
            return []

        translated = " ".join(tokens)
        return self._english_query_variants(translated)

    async def _translate_query_to_english(self, query: str) -> str:
        if not self.config.get("enable_online_translation", True):
            return ""
        if not self._contains_chinese(query):
            return ""

        params = {
            "client": "gtx",
            "sl": "zh-CN",
            "tl": "en",
            "dt": "t",
            "q": query,
        }
        try:
            await self._wait_for_request_slot()
            response = await self.client.get(TRANSLATE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or not data or not isinstance(data[0], list):
                return ""
            translated = "".join(
                str(part[0])
                for part in data[0]
                if isinstance(part, list) and part and part[0]
            )
            return self._normalize_translated_query(translated)
        except Exception:
            return ""

    def _normalize_translated_query(self, query: str) -> str:
        text = normalize_text(query, "")
        text = re.sub(r"(?i)\broblox\b", " ", text)
        text = re.sub(r"(?i)\bgame\s+of\b", " ", text)
        text = re.sub(r"(?i)\bthe\b", " ", text)
        return normalize_text(" ".join(text.split()), "")

    def _english_query_variants(self, query: str) -> list[str]:
        query = normalize_text(query, "")
        if not query:
            return []

        variants = [query]
        replacements = (
            ("Mini Games", "Minigames"),
            ("Mini Game", "Minigames"),
            ("mini games", "Minigames"),
            ("mini game", "Minigames"),
        )
        for old, new in replacements:
            if old in query:
                variants.append(query.replace(old, new))
        return variants

    async def _fetch_age_info(self, universe_id: int, name: str, use_cache: bool = True) -> dict[str, Any]:
        if not name:
            return {}
        if use_cache:
            cached = self._cache_age.get(universe_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached or {}
        result: dict[str, Any] = {}
        try:
            for search_hit in await self._search_game_candidates(name):
                if int(search_hit.get("universe_id", 0)) == universe_id:
                    result = search_hit
                    break
        except RobloxRateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取年龄组信息失败（universe_id=%s）: %s", universe_id, exc)
        self._cache_age.set(universe_id, result)
        return result

    async def _fetch_game_detail(self, universe_id: int, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self._cache_detail.get(universe_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached
        try:
            payload = await self._get_json(GAME_DETAIL_URL, params={"universeIds": str(universe_id)})
        except RobloxRateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取游戏详情失败（universe_id=%s）: %s", universe_id, exc)
            payload = {}
        data = payload.get("data", [])
        detail = data[0] if data else None
        self._cache_detail.set(universe_id, detail)
        return detail

    async def _fetch_votes(self, universe_id: int, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            cached = self._cache_votes.get(universe_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached
        try:
            payload = await self._get_json(GAME_VOTES_URL, params={"universeIds": str(universe_id)})
        except RobloxRateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取投票数据失败（universe_id=%s）: %s", universe_id, exc)
            payload = {}
        data = payload.get("data", [])
        votes = data[0] if data else {"upVotes": 0, "downVotes": 0}
        self._cache_votes.set(universe_id, votes)
        return votes

    async def _fetch_image(self, universe_id: int, use_cache: bool = True) -> str:
        if use_cache:
            cached = self._cache_image.get(universe_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached
        params = {
            "universeIds": str(universe_id),
            "returnPolicy": "PlaceHolder",
            "size": "512x512",
            "format": "Png",
            "isCircular": "false",
        }
        try:
            payload = await self._get_json(GAME_ICON_URL, params=params)
        except RobloxRateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("获取游戏图标失败（universe_id=%s）: %s", universe_id, exc)
            payload = {}
        data = payload.get("data", [])
        image_url = (data[0].get("imageUrl") or "") if data else ""
        self._cache_image.set(universe_id, image_url)
        return image_url

    async def _place_to_universe(self, place_id: int, use_cache: bool = True) -> int | None:
        if use_cache:
            cached = self._cache_place_universe.get(place_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached
        try:
            payload = await self._get_json(PLACE_TO_UNIVERSE_URL.format(place_id=place_id))
        except RobloxRateLimitError:
            raise
        except (httpx.HTTPStatusError, RuntimeError, ValueError) as exc:
            # 接口 404 / 返回 errors JSON / 其他解析失败都视为“该 ID 不是有效 place”
            logger.warning("解析 place 到 universe 失败（place_id=%s）: %s", place_id, exc)
            self._cache_place_universe.set(place_id, None)
            return None
        universe_id = payload.get("universeId")
        result = int(universe_id) if universe_id else None
        self._cache_place_universe.set(place_id, result)
        return result

    async def _fetch_servers(
        self,
        root_place_id: int,
        use_cache: bool = True,
    ) -> tuple[list[RobloxServer], bool, bool, bool]:
        if root_place_id <= 0:
            return [], False, False, False

        if use_cache:
            cached = self._cache_servers.get(root_place_id, _NOT_CACHED)
            if cached is not _NOT_CACHED:
                return cached

        page_size = self._valid_server_page_size()
        page_limit = max(1, int(self.config.get("server_scan_page_limit", 5)))
        cursor = None
        all_servers: list[RobloxServer] = []
        scanned_all = True
        page_limit_hit = False
        server_data_available = True

        for _ in range(page_limit):
            params = {"sortOrder": "Asc", "limit": str(page_size)}
            if cursor:
                params["cursor"] = cursor
            try:
                payload = await self._get_json(PUBLIC_SERVERS_URL.format(place_id=root_place_id), params=params)
            except RobloxRateLimitError:
                scanned_all = False
                page_limit_hit = True
                break
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                logger.warning("获取 Roblox 公开服务器失败（place_id=%s）: %s", root_place_id, exc)
                scanned_all = False
                server_data_available = bool(all_servers)
                break

            for item in payload.get("data", []):
                try:
                    playing_raw = item.get("playing")
                    max_players_raw = item.get("maxPlayers")
                    if playing_raw is None or max_players_raw is None:
                        # Roblox 偶发返回 null 的异常条目，跳过避免污染统计
                        continue
                    playing = int(playing_raw)
                    max_players = int(max_players_raw)
                    ping = item.get("ping")
                    fps = item.get("fps")
                    server = RobloxServer(
                        id=str(item.get("id", "")),
                        playing=playing,
                        max_players=max_players,
                        ping=int(ping) if ping is not None else None,
                        fps=float(fps) if fps is not None else None,
                        status=summarize_status(playing, max_players),
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning("跳过无法解析的公开服务器数据（place_id=%s）: %r", root_place_id, item)
                    continue
                all_servers.append(server)

            cursor = payload.get("nextPageCursor")
            if not cursor:
                break
        else:
            scanned_all = False
            page_limit_hit = True

        if cursor:
            scanned_all = False

        result = (all_servers, scanned_all, page_limit_hit, server_data_available)
        self._cache_servers.set(root_place_id, result)
        return result

    async def _build_game(
        self,
        detail: dict[str, Any],
        votes: dict[str, Any],
        image_url: str,
        fallback_description: str,
        age_info: dict[str, Any] | None,
        fetch_servers: bool = True,
        use_cache: bool = True,
    ) -> RobloxGame:
        root_place_id = int(detail.get("rootPlaceId", 0))
        if fetch_servers:
            servers, scanned_all, page_limit_hit, server_data_available = await self._fetch_servers(
                root_place_id, use_cache=use_cache
            )
        else:
            servers, scanned_all, page_limit_hit, server_data_available = [], False, False, False

        genre_l1 = normalize_text(detail.get("genre_l1"), "")
        genre_l2 = normalize_text(detail.get("genre_l2"), "")
        genre = detail.get("genre") or "未知"
        if genre_l1 and genre_l2:
            genre = f"{genre_l1} / {genre_l2}"
        elif genre_l1:
            genre = f"{genre_l1} / {genre}"

        description = normalize_text(detail.get("description"), fallback_description)
        image_url = image_url or "https://tr.rbxcdn.com/default/512/512/Image/Png"

        return RobloxGame(
            universe_id=int(detail.get("id", 0)),
            root_place_id=root_place_id,
            name=normalize_text(detail.get("name"), "未知游戏"),
            description=description,
            creator_name=normalize_text(detail.get("creator", {}).get("name"), "未知开发者"),
            genre=genre,
            age_recommendation=normalize_text((age_info or {}).get("age_recommendation"), ""),
            content_maturity=normalize_text((age_info or {}).get("content_maturity"), ""),
            minimum_age=int((age_info or {}).get("minimum_age", 0) or 0),
            playing=int(detail.get("playing", 0) or 0),
            visits=int(detail.get("visits", 0) or 0),
            favorited=int(detail.get("favoritedCount", 0) or 0),
            price=int(detail.get("price", 0) or 0),
            up_votes=int(votes.get("upVotes", 0)),
            down_votes=int(votes.get("downVotes", 0)),
            image_url=image_url,
            servers=servers,
            scanned_all_servers=scanned_all,
            page_limit_hit=page_limit_hit,
            server_data_available=server_data_available,
            servers_skipped=not fetch_servers,
        )

    def _valid_server_page_size(self) -> int:
        value = max(1, int(self.config.get("server_page_size", 50)))
        # 收敛到 Roblox 接口合法值（10/25/50/100），配置了其他值也不会 400
        return min(VALID_SERVER_PAGE_SIZES, key=lambda option: (abs(option - value), option))

    def _display_servers(
        self,
        game: RobloxGame,
        servers_arg: str | None,
        sort_mode: str,
    ) -> list[RobloxServer]:
        limit = min(MAX_DISPLAY_SERVERS, max(1, int(self.config.get("server_display_limit", 10))))
        if servers_arg:
            limit = min(MAX_DISPLAY_SERVERS, max(1, int(servers_arg)))

        servers = list(game.servers)
        if sort_mode == "players":
            servers.sort(key=lambda server: server.playing, reverse=True)
        elif sort_mode == "free":
            servers.sort(
                key=lambda server: (
                    (server.max_players - server.playing) if server.max_players > 0 else -1
                ),
                reverse=True,
            )
        else:  # 默认按延迟从低到高，延迟未知的排最后
            servers.sort(
                key=lambda server: (
                    server.ping is None,
                    server.ping if server.ping is not None else math.inf,
                )
            )
        return servers[:limit]

    def _render_text(self, game: RobloxGame, display_servers: list[RobloxServer]) -> str:
        lines = [
            f"游戏名：{game.name}",
            f"游戏简介：{game.description}",
            f"开发者：{game.creator_name}",
            f"年龄组：{game.age_text}",
            f"类型 / 好评度：{game.genre} / {game.rating_text}",
            f"价格：{game.price_text}",
            f"在线人数：{game.playing_text}",
            f"总访问量：{game.visits_text}",
            f"收藏数：{game.favorited_text}",
            f"公开服务器数：{game.server_count_text}",
            f"公开服在线总人数：{game.server_players_text}",
            "服务器状态：",
        ]
        for index, server in enumerate(display_servers, start=1):
            lines.append(
                f"{index}. {server.status} | {server.playing}/{server.max_players} 人 | 延迟 {server.ping_text} | FPS {server.fps_text}"
            )
        lines.append(self._server_note(game, display_servers))
        lines.append(f"Roblox 链接：https://www.roblox.com/games/{game.root_place_id}")
        if game.join_url:
            lines.append(f"快速加入：{game.join_url}")
        return "\n".join(lines)

    def _server_note(self, game: RobloxGame, display_servers: list[RobloxServer]) -> str:
        if game.servers_skipped:
            return "已按 --简洁 模式跳过公开服务器扫描，未统计服务器数据。"
        shown = len(display_servers)
        total = len(game.servers)
        if not game.server_data_available:
            return "公开服务器数据暂不可用，已正常返回游戏基本信息。"
        if game.scanned_all_servers:
            return f"已展示 {shown} 个公开服务器，已完成当前扫描，共统计到 {total} 个服务器。"
        if game.page_limit_hit:
            return (
                f"已展示 {shown} 个公开服务器，当前仅统计到 {total} 个服务器。"
                "为了避免请求过快触发 Roblox 限流，服务器扫描已提前停止。"
            )
        return f"已展示 {shown} 个公开服务器，当前已统计至少 {total} 个服务器。"

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        retries = max(0, int(self.config.get("retry_429_count", 2)))
        backoff_ms = max(500, int(self.config.get("retry_429_backoff_ms", 3000)))
        attempt = 0

        while True:
            await self._wait_for_request_slot()
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and data.get("errors"):
                    raise RuntimeError(data["errors"][0].get("message", "Roblox API 返回错误"))
                return data if isinstance(data, dict) else {}
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    if attempt >= retries:
                        raise RobloxRateLimitError("Roblox API 请求过快，已触发 429。") from exc
                    await asyncio.sleep((backoff_ms / 1000.0) * (attempt + 1))
                    attempt += 1
                    continue
                raise

    async def _wait_for_request_slot(self):
        min_interval_ms = max(0, int(self.config.get("min_request_interval_ms", 500)))
        async with self._request_lock:
            now = time.monotonic()
            wait_seconds = (min_interval_ms / 1000.0) - (now - self._last_request_ts)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_ts = time.monotonic()
