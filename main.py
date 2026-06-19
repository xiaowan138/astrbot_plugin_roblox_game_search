import asyncio
import math
import re
import time
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
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

DEFAULT_BACKGROUND = (
    "radial-gradient(circle at top left, rgba(99, 102, 241, 0.35), transparent 28%), "
    "radial-gradient(circle at top right, rgba(16, 185, 129, 0.28), transparent 24%), "
    "linear-gradient(135deg, #111827 0%, #0f172a 52%, #111827 100%)"
)

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
  </style>
</head>
<body>
  <div class="panel">
    <div class="hero">
      <div class="cover">
        <img src="{{ game.image_url }}" alt="game-icon" />
      </div>
      <div>
        <h1 class="title">{{ game.name }}</h1>
        <div class="badges">
          <span class="badge">开发者：{{ game.creator_name }}</span>
          <span class="badge">类型：{{ game.genre }}</span>
          <span class="badge">年龄组：{{ game.age_text }}</span>
          <span class="badge">好评率：{{ game.rating_text }}</span>
          <span class="badge">在线：{{ game.playing_text }}</span>
          <span class="badge">公开服：{{ game.server_count_text }}</span>
        </div>
        <p class="desc">{{ game.description }}</p>
      </div>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="stat-label">开发者</div>
        <div class="stat-value">{{ game.creator_name }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">游戏类型</div>
        <div class="stat-value">{{ game.genre }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">年龄组</div>
        <div class="stat-value">{{ game.age_text }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">好评度</div>
        <div class="stat-value">{{ game.rating_text }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">当前在线人数</div>
        <div class="stat-value">{{ game.playing_text }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">公开服务器统计</div>
        <div class="stat-value">{{ game.server_count_text }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">公开服在线总人数</div>
        <div class="stat-value">{{ game.server_players_text }}</div>
      </div>
    </div>

    <div class="section">
      <h2 class="section-title">公开服务器状态</h2>
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
            <td>{{ server.status }}</td>
            <td>{{ server.playing }}/{{ server.max_players }}</td>
            <td>{{ server.ping_text }}</td>
            <td>{{ server.fps_text }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="footer-note">
      {{ game.server_note }}<br />
      Roblox 链接：https://www.roblox.com/games/{{ game.root_place_id }}
    </div>
  </div>
</body>
</html>
"""


class RobloxRateLimitError(RuntimeError):
    pass


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
    up_votes: int
    down_votes: int
    image_url: str
    servers: list[RobloxServer]
    scanned_all_servers: bool
    page_limit_hit: bool

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
    "0.1.7",
)
class RobloxGameSearchPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        timeout = float(self.config.get("request_timeout", 20))
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "AstrBot-Roblox-Search/0.1.7"},
            follow_redirects=True,
        )
        self._request_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self._recent_event_keys: dict[str, float] = {}

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

        if not args["query"]:
            yield event.plain_result(self._usage_text(search_mode))
            return

        if search_mode == "name" and args["query"].isdigit():
            yield event.plain_result("这个指令用于按游戏名搜索。纯数字 ID 请使用 /roblox游戏ID搜索。")
            return

        if search_mode == "id" and not args["query"].isdigit():
            yield event.plain_result("这个指令只接受纯数字 ID。游戏名请使用 /roblox游戏搜索。")
            return

        render_mode = args["mode"] or str(self.config.get("default_render_mode", "html")).lower()
        background = args["background"] or str(self.config.get("html_background", DEFAULT_BACKGROUND))

        try:
            if search_mode == "name":
                game = await self._resolve_game_by_name(args["query"])
            else:
                game = await self._resolve_game_by_id(int(args["query"]))

            if not game:
                yield event.plain_result(self._not_found_text(args["query"]))
                return

            display_limit = max(1, int(self.config.get("server_display_limit", 10)))
            if args["servers"]:
                display_limit = max(1, int(args["servers"]))
            display_servers = sorted(
                game.servers,
                key=lambda server: (server.ping is None, server.ping if server.ping is not None else math.inf),
            )[:display_limit]

            if render_mode == "text":
                yield event.chain_result(
                    [
                        Comp.Image.fromURL(game.image_url),
                        Comp.Plain(self._render_text(game, display_servers)),
                    ]
                )
                return

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
                        "server_count_text": game.server_count_text,
                        "server_players_text": game.server_players_text,
                        "root_place_id": game.root_place_id,
                        "server_note": self._server_note(game, display_servers),
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

        now = time.monotonic()
        ttl_seconds = 5.0
        cutoff = now - ttl_seconds
        if len(self._recent_event_keys) > 120:
            self._recent_event_keys = {
                key: ts for key, ts in self._recent_event_keys.items() if ts >= cutoff
            }

        message_obj = getattr(event, "message_obj", None)
        message_id = getattr(message_obj, "message_id", "") or getattr(message_obj, "id", "")
        sender_id = (
            getattr(message_obj, "sender_id", "")
            or getattr(message_obj, "sender", "")
            or getattr(message_obj, "user_id", "")
        )
        origin = getattr(event, "unified_msg_origin", "") or getattr(event, "session_id", "")
        dedupe_key = f"{search_mode}:{origin}:{sender_id}:{message_id}:{raw_message}"
        last_seen = self._recent_event_keys.get(dedupe_key)
        if last_seen and last_seen >= cutoff:
            return True
        self._recent_event_keys[dedupe_key] = now
        return False

    def _not_found_text(self, query: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", query or ""):
            return (
                "没有找到对应的 Roblox 游戏。插件已经尝试中文别名、关键词翻译和英文候选搜索，"
                "可以换一个更完整的游戏名再试。"
            )
        return "没有找到对应的 Roblox 游戏，请检查输入后再试。"

    def _parse_command_args(self, message: str, command_names: list[str]) -> dict[str, str | None]:
        text = re.sub(r"^/+", "", (message or "").strip())
        commands_pattern = "|".join(re.escape(command_name) for command_name in command_names)
        text = re.sub(rf"^(?:{commands_pattern})", "", text, count=1).strip()

        mode = None
        background = None
        server_match = None

        for pattern, value in (
            (r"(?:^|\s)--?(?:文本|text)(?:\s|$)", "text"),
            (r"(?:^|\s)--?(?:图片|html|image|img)(?:\s|$)", "html"),
        ):
            if re.search(pattern, text, re.IGNORECASE):
                mode = value
                text = re.sub(pattern, " ", text, flags=re.IGNORECASE).strip()

        bg_match = re.search(r"--?(?:背景|bg)=(.+?)(?=\s--|$)", text, re.IGNORECASE)
        if bg_match:
            background = bg_match.group(1).strip()
            text = text.replace(bg_match.group(0), " ").strip()

        server_match = re.search(r"--?(?:服务器数|servers?)=(\d+)", text, re.IGNORECASE)
        if server_match:
            text = text.replace(server_match.group(0), " ").strip()

        return {
            "query": normalize_text(text, ""),
            "mode": mode,
            "background": background,
            "servers": server_match.group(1) if server_match else None,
        }

    def _usage_text(self, search_mode: str) -> str:
        if search_mode == "name":
            return (
                "用法：/roblox游戏搜索 游戏名\n"
                "别名：/游戏搜索 游戏名\n"
                "可选参数：--文本 | --图片 | --背景=自定义CSS背景\n"
                "示例：/roblox游戏搜索 doors\n"
                "示例：/游戏搜索 --文本 Blox Fruits"
            )
        return (
            "用法：/roblox游戏ID搜索 数字ID\n"
            "别名：/游戏ID搜索 数字ID\n"
            "可选参数：--文本 | --图片 | --背景=自定义CSS背景\n"
            "示例：/roblox游戏ID搜索 6516141723\n"
            "示例：/游戏ID搜索 --文本 2440500124"
        )

    async def _resolve_game_by_name(self, query: str) -> RobloxGame | None:
        search_hit = await self._search_game(query.strip())
        if not search_hit:
            return None

        universe_id = int(search_hit["universe_id"])
        detail = await self._fetch_game_detail(universe_id)
        if not detail:
            return None

        votes = await self._fetch_votes(universe_id)
        image_url = await self._fetch_image(universe_id)
        return await self._build_game(detail, votes, image_url, search_hit["description"], search_hit)

    async def _resolve_game_by_id(self, numeric_id: int) -> RobloxGame | None:
        detail = await self._fetch_game_detail(numeric_id)
        if detail:
            universe_id = int(detail.get("id", numeric_id))
            votes = await self._fetch_votes(universe_id)
            image_url = await self._fetch_image(universe_id)
            age_info = await self._fetch_age_info(universe_id, normalize_text(detail.get("name"), ""))
            return await self._build_game(detail, votes, image_url, "", age_info)

        universe_id = await self._place_to_universe(numeric_id)
        if not universe_id:
            return None

        detail = await self._fetch_game_detail(universe_id)
        if not detail:
            return None

        votes = await self._fetch_votes(universe_id)
        image_url = await self._fetch_image(universe_id)
        age_info = await self._fetch_age_info(universe_id, normalize_text(detail.get("name"), ""))
        return await self._build_game(detail, votes, image_url, "", age_info)

    async def _search_game(self, query: str) -> dict[str, Any] | None:
        search_queries = await self._build_search_queries(query)
        candidates: list[dict[str, Any]] = []
        seen_candidates: dict[str, dict[str, Any]] = {}

        for query_index, search_query in enumerate(search_queries):
            for candidate in await self._search_game_candidates(search_query):
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
                    existing.setdefault("_matched_queries", []).append(search_query)
                    continue

                candidate = dict(candidate)
                candidate["_best_query_index"] = query_index
                candidate["_matched_queries"] = [search_query]
                candidates.append(candidate)
                seen_candidates[candidate_key] = candidate

        return self._pick_best_search_hit(search_queries, candidates)

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

    def _pick_best_search_hit(
        self,
        queries: str | list[str],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not candidates:
            return None

        target_queries = [queries] if isinstance(queries, str) else queries
        target_queries = [normalize_text(query, "") for query in target_queries if normalize_text(query, "")]

        def single_match_score(query: str, candidate: dict[str, Any]) -> float:
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
            return SequenceMatcher(None, query_norm, name_norm).ratio() * 1500

        def match_score(candidate: dict[str, Any]) -> float:
            return max((single_match_score(query, candidate) for query in target_queries), default=0.0)

        def score(candidate: dict[str, Any]) -> float:
            base = match_score(candidate)
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

        best = max(candidates, key=score)
        best_match = match_score(best)
        min_match_score = float(self.config.get("name_match_min_score", 2200))
        if best_match < min_match_score:
            return None
        return best

    async def _build_search_queries(self, query: str) -> list[str]:
        query_clean = normalize_text(query, "")
        cleaned_query = self._cleanup_user_search_query(query_clean)
        search_queries: list[str] = []

        def add(value: str | None):
            value = normalize_text(value, "")
            if not value:
                return
            if compact_match_text(value) in {compact_match_text(item) for item in search_queries}:
                return
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
            ("Tycoon 2", "Tycoon 2"),
        )
        for old, new in replacements:
            if old in query:
                variants.append(query.replace(old, new))
        return variants

    async def _fetch_age_info(self, universe_id: int, name: str) -> dict[str, Any]:
        if not name:
            return {}
        for search_hit in await self._search_game_candidates(name):
            if int(search_hit.get("universe_id", 0)) == universe_id:
                return search_hit
        return {}

    async def _fetch_game_detail(self, universe_id: int) -> dict[str, Any] | None:
        payload = await self._get_json(GAME_DETAIL_URL, params={"universeIds": str(universe_id)})
        data = payload.get("data", [])
        return data[0] if data else None

    async def _fetch_votes(self, universe_id: int) -> dict[str, Any]:
        payload = await self._get_json(GAME_VOTES_URL, params={"universeIds": str(universe_id)})
        data = payload.get("data", [])
        return data[0] if data else {"upVotes": 0, "downVotes": 0}

    async def _fetch_image(self, universe_id: int) -> str:
        params = {
            "universeIds": str(universe_id),
            "returnPolicy": "PlaceHolder",
            "size": "512x512",
            "format": "Png",
            "isCircular": "false",
        }
        payload = await self._get_json(GAME_ICON_URL, params=params)
        data = payload.get("data", [])
        if data:
            return data[0].get("imageUrl") or ""
        return ""

    async def _place_to_universe(self, place_id: int) -> int | None:
        try:
            payload = await self._get_json(PLACE_TO_UNIVERSE_URL.format(place_id=place_id))
        except httpx.HTTPStatusError:
            return None
        universe_id = payload.get("universeId")
        return int(universe_id) if universe_id else None

    async def _fetch_servers(self, root_place_id: int) -> tuple[list[RobloxServer], bool, bool]:
        page_size = min(100, max(10, int(self.config.get("server_page_size", 30))))
        page_limit = max(1, int(self.config.get("server_scan_page_limit", 5)))
        cursor = None
        all_servers: list[RobloxServer] = []
        scanned_all = True
        page_limit_hit = False

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

            for item in payload.get("data", []):
                playing = int(item.get("playing", 0))
                max_players = int(item.get("maxPlayers", 0))
                ping = item.get("ping")
                fps = item.get("fps")
                all_servers.append(
                    RobloxServer(
                        id=str(item.get("id", "")),
                        playing=playing,
                        max_players=max_players,
                        ping=int(ping) if ping is not None else None,
                        fps=float(fps) if fps is not None else None,
                        status=summarize_status(playing, max_players),
                    )
                )

            cursor = payload.get("nextPageCursor")
            if not cursor:
                break
        else:
            scanned_all = False
            page_limit_hit = True

        if cursor:
            scanned_all = False
        return all_servers, scanned_all, page_limit_hit

    async def _build_game(
        self,
        detail: dict[str, Any],
        votes: dict[str, Any],
        image_url: str,
        fallback_description: str,
        age_info: dict[str, Any] | None,
    ) -> RobloxGame:
        root_place_id = int(detail.get("rootPlaceId", 0))
        servers, scanned_all, page_limit_hit = await self._fetch_servers(root_place_id)

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
            playing=int(detail.get("playing", 0)),
            up_votes=int(votes.get("upVotes", 0)),
            down_votes=int(votes.get("downVotes", 0)),
            image_url=image_url,
            servers=servers,
            scanned_all_servers=scanned_all,
            page_limit_hit=page_limit_hit,
        )

    def _render_text(self, game: RobloxGame, display_servers: list[RobloxServer]) -> str:
        lines = [
            f"游戏名：{game.name}",
            f"游戏简介：{game.description}",
            f"开发者：{game.creator_name}",
            f"年龄组：{game.age_text}",
            f"类型 / 好评度：{game.genre} / {game.rating_text}",
            f"在线人数：{game.playing_text}",
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
        return "\n".join(lines)

    def _server_note(self, game: RobloxGame, display_servers: list[RobloxServer]) -> str:
        shown = len(display_servers)
        total = len(game.servers)
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
