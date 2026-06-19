# astrbot_plugin_roblox_game_search

一个 AstrBot 插件，通过两个指令查询 Roblox 游戏信息。

## 指令

```text
/roblox游戏搜索 游戏名
/roblox游戏ID搜索 数字ID
```

可选参数：

```text
--文本
--图片
--背景=CSS背景
--服务器数=10
```

## 功能

- `/roblox游戏搜索` 只按游戏名搜索。
- `/roblox游戏ID搜索` 只按纯数字 ID 搜索，兼容 `universeId` 和 `placeId`。
- 支持文本和 HTML 生图两种输出。
- 文本模式会直接发送图片组件，不再发图片链接。
- 展示字段包含：
  - 游戏名
  - 游戏图片
  - 游戏简介
  - 开发者
  - 年龄组
  - 类型和好评度
  - 在线人数
  - 公开服务器统计
  - 服务器状态 / 人数 / 延迟 / FPS

## 限流设置

这一版增加了请求节奏控制，避免一下子请求过多：

- 所有 Roblox API 请求按最小间隔串行发送
- 遇到 `429 Too Many Requests` 会自动退避重试
- 服务器分页默认缩小
- 服务器扫描页数默认降低
- 如果服务器接口还是被限流，会返回部分统计结果，而不是整条查询失败

对应配置见 `_conf_schema.json`：

- `min_request_interval_ms`
- `retry_429_count`
- `retry_429_backoff_ms`
- `server_page_size`
- `server_scan_page_limit`

## 安装

将本目录放进 AstrBot 的 `data/plugins` 目录，然后在 WebUI 中安装依赖并启用插件。
