import asyncio
import math
import re
import uuid
from dataclasses import dataclass
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

DEFAULT_BACKGROUND = (
    "radial-gradient(circle at top left, rgba(99, 102, 241, 0.35), transparent 28%), "
    "radial-gradient(circle at top right, rgba(16, 185, 129, 0.28), transparent 24%), "
    "linear-gradient(135deg, #111827 0%, #0f172a 52%, #111827 100%)"
)

HTML_TEMPLATE = r"""
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
      letter-spacing: 0;
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
    "通过 /roblox游戏搜索 指令查询 Roblox 游戏详情与服务器信息。",
    "0.1.0",
)
class RobloxGameSearchPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        timeout = float(self.config.get("request_timeout", 20))
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "AstrBot-Roblox-Search/0.1"},
            follow_redirects=True,
        )

    async def terminate(self):
        await self.client.aclose()

    @filter.command("roblox游戏搜索")
    async def roblox_game_search(self, event: AstrMessageEvent):
        query_text = event.message_str or ""
        args = self._parse_command_args(query_text)

        if not args["query"]:
            yield event.plain_result(self._usage_text())
            return

        render_mode = args["mode"] or str(self.config.get("default_render_mode", "html")).lower()
        background = args["background"] or str(
            self.config.get("html_background", DEFAULT_BACKGROUND)
        )

        try:
            game = await self._resolve_game(args["query"])
            if not game:
                yield event.plain_result("没有找到对应的 Roblox 游戏。请换一个 ID 或游戏名试试。")
                return

            display_limit = max(1, int(self.config.get("server_display_limit", 15)))
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
        except Exception as exc:  # noqa: BLE001
            logger.exception("Roblox 游戏搜索插件执行失败: %s", exc)
            yield event.plain_result(f"查询失败：{exc}")

    def _parse_command_args(self, message: str) -> dict[str, str | None]:
        text = re.sub(r"^/+", "", (message or "").strip())
        text = re.sub(r"^roblox游戏搜索", "", text, count=1).strip()

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

    def _usage_text(self) -> str:
        return (
            "用法：/roblox游戏搜索 ID/游戏名\n"
            "可选参数：--文本 | --图片 | --背景=自定义CSS背景\n"
            "示例：/roblox游戏搜索 doors\n"
            "示例：/roblox游戏搜索 --文本 6516141723\n"
            "示例：/roblox游戏搜索 --背景=linear-gradient(135deg,#0f172a,#1d4ed8) Blox Fruits"
        )

    async def _resolve_game(self, query: str) -> RobloxGame | None:
        query = query.strip()
        if not query:
            return None

        if query.isdigit():
            by_id = await self._resolve_game_by_id(int(query))
            if by_id:
                return by_id

        search_hit = await self._search_game(query)
        if not search_hit:
            return None

        universe_id = int(search_hit["universe_id"])
        detail_task = self._fetch_game_detail(universe_id)
        votes_task = self._fetch_votes(universe_id)
        image_task = self._fetch_image(universe_id)
        detail, votes, image_url = await asyncio.gather(detail_task, votes_task, image_task)
        if not detail:
            return None
        return await self._build_game(
            detail,
            votes,
            image_url,
            search_hit["description"],
            search_hit,
        )

    async def _resolve_game_by_id(self, numeric_id: int) -> RobloxGame | None:
        detail = await self._fetch_game_detail(numeric_id)
        if detail:
            votes_task = self._fetch_votes(numeric_id)
            image_task = self._fetch_image(numeric_id)
            age_task = self._fetch_age_info(
                int(detail.get("id", numeric_id)),
                normalize_text(detail.get("name"), ""),
            )
            votes, image_url, age_info = await asyncio.gather(votes_task, image_task, age_task)
            return await self._build_game(detail, votes, image_url, "", age_info)

        universe_id = await self._place_to_universe(numeric_id)
        if not universe_id:
            return None

        detail_task = self._fetch_game_detail(universe_id)
        votes_task = self._fetch_votes(universe_id)
        image_task = self._fetch_image(universe_id)
        detail, votes, image_url = await asyncio.gather(detail_task, votes_task, image_task)
        if not detail:
            return None
        age_info = await self._fetch_age_info(
            universe_id,
            normalize_text(detail.get("name"), ""),
        )
        return await self._build_game(detail, votes, image_url, "", age_info)

    async def _search_game(self, query: str) -> dict[str, Any] | None:
        params = {
            "searchQuery": query,
            "pageToken": "",
            "sessionId": str(uuid.uuid4()),
            "pageType": "all",
        }
        payload = await self._get_json(OMNI_SEARCH_URL, params=params)
        for block in payload.get("searchResults", []):
            if block.get("contentGroupType") != "Game":
                continue
            for content in block.get("contents", []):
                universe_id = content.get("universeId") or content.get("contentId")
                root_place_id = content.get("rootPlaceId")
                if universe_id and root_place_id:
                    return {
                        "universe_id": int(universe_id),
                        "root_place_id": int(root_place_id),
                        "description": normalize_text(content.get("description"), "暂无简介。"),
                        "age_recommendation": normalize_text(
                            content.get("ageRecommendationDisplayName"),
                            "",
                        ),
                        "content_maturity": normalize_text(content.get("contentMaturity"), ""),
                        "minimum_age": int(content.get("minimumAge", 0) or 0),
                    }
        return None

    async def _fetch_age_info(self, universe_id: int, name: str) -> dict[str, Any]:
        if not name:
            return {}
        search_hit = await self._search_game(name)
        if search_hit and int(search_hit.get("universe_id", 0)) == universe_id:
            return search_hit

        params = {
            "searchQuery": name,
            "pageToken": "",
            "sessionId": str(uuid.uuid4()),
            "pageType": "all",
        }
        payload = await self._get_json(OMNI_SEARCH_URL, params=params)
        for block in payload.get("searchResults", []):
            if block.get("contentGroupType") != "Game":
                continue
            for content in block.get("contents", []):
                if int(content.get("universeId", 0) or 0) != universe_id:
                    continue
                return {
                    "age_recommendation": normalize_text(
                        content.get("ageRecommendationDisplayName"),
                        "",
                    ),
                    "content_maturity": normalize_text(content.get("contentMaturity"), ""),
                    "minimum_age": int(content.get("minimumAge", 0) or 0),
                }
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
        page_size = min(100, max(10, int(self.config.get("server_page_size", 100))))
        page_limit = max(1, int(self.config.get("server_scan_page_limit", 30)))
        cursor = None
        all_servers: list[RobloxServer] = []
        scanned_all = True
        page_limit_hit = False

        for _ in range(page_limit):
            params = {"sortOrder": "Asc", "limit": str(page_size)}
            if cursor:
                params["cursor"] = cursor
            payload = await self._get_json(PUBLIC_SERVERS_URL.format(place_id=root_place_id), params=params)
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
            return f"已展示 {shown} 个公开服务器，已完成全量统计，共 {total} 个服务器。"
        if game.page_limit_hit:
            return (
                f"已展示 {shown} 个公开服务器，当前仅统计到 {total} 个服务器。"
                "由于公开服务器过多，已触发扫描上限，显示的是初版的截断结果。"
            )
        return f"已展示 {shown} 个公开服务器，当前已统计至少 {total} 个服务器。"

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("errors"):
            raise RuntimeError(data["errors"][0].get("message", "Roblox API 返回错误"))
        return data if isinstance(data, dict) else {}
