# service.py — Service Orchestrator

`src/service.py` is the top-level coordinator for the notifier. It owns no protocol logic of its own — instead it wires together the WebSocket client and the Discord notifier, manages their lifecycles, and routes alerts between them.

---

## Class: `AlertNotificationService`

### Owned objects

| Attribute | Type | Purpose |
|---|---|---|
| `centauri_client` | `CentauriWebSocketClient` | SDCP WebSocket connection to the printer |
| `discord_notifier` | `DiscordNotifier` | aiohttp session + Discord webhook sender |
| `websocket_task` | `asyncio.Task` | Runs the WS reconnect loop |
| `poll_task` | `asyncio.Task` | Periodically drains the alert buffer |
| `heartbeat_task` | `asyncio.Task` | Sends text "ping" every 30 s |

---

## Startup sequence (`start`)

```
1. validate_config()              — check all required env vars are set
2. _test_connections()            — optional: quick connect/close to verify reachability
3. DiscordNotifier.__aenter__()   — open aiohttp ClientSession
4. attach WS callbacks            — on_connect / on_disconnect / on_error
5. create_task(start_with_reconnect)   — WS loop starts in background
6. create_task(_poll_loop)             — alert drain starts in background
7. create_task(_heartbeat_loop)        — ping loop starts in background
8. _setup_signal_handlers()       — SIGTERM / SIGINT → graceful shutdown
9. asyncio.gather(all three tasks) — block here until stopped
```

---

## Concurrent tasks

Three `asyncio.Task` objects run independently after startup:

### `_poll_loop`
- Runs `_poll_for_alerts()` immediately, then sleeps for `POLL_INTERVAL_MINUTES * 60` seconds.
- `_poll_for_alerts()` calls `centauri_client.get_new_alerts()` to drain the buffer, filters by severity, then calls `discord_notifier.send_alerts_batch()`.
- Skips silently if the WebSocket is not yet connected.

### `_heartbeat_loop`
- Every 30 seconds, calls `centauri_client.send_heartbeat()` which sends the text string `"ping"` over the WebSocket.
- The printer responds with `"pong"` — this is the SDCP application-level heartbeat, not a WebSocket protocol ping frame.

### `websocket_task` (delegated to `CentauriWebSocketClient`)
- Connects, requests initial status (`Cmd=0`), receives messages indefinitely.
- Auto-reconnects after 10 seconds on any error or disconnect.
- Fires the callbacks registered in step 4 above.

---

## WebSocket callbacks

| Callback | When fired | What it does |
|---|---|---|
| `on_connect` | WS connection established | Fires `_notify_printer_connected()` as a new task |
| `on_disconnect` | WS closed (clean or error) | Logs the event |
| `on_error` | Unhandled WS exception | Logs the error |

### `_notify_printer_connected`
Sends a green "Printer Connected" embed directly to Discord (bypasses the alert buffer). This fires once per connection, including reconnections.

---

## Alert flow

```
Printer firmware
    │  (SDCP WebSocket messages)
    ▼
CentauriWebSocketClient._handle_status / _handle_notice
    │  (Alert objects appended to _alert_buffer)
    ▼
AlertNotificationService._poll_for_alerts   (runs every POLL_INTERVAL_MINUTES)
    │  get_new_alerts() drains the buffer
    │  _filter_alerts() applies severity rules
    ▼
DiscordNotifier.send_alerts_batch
    │  (one embed per alert, batched into one webhook POST)
    ▼
Discord channel
```

Alerts that come from the WebSocket client:
- **Initial status** — buffered on the very first `sdcp/status` message after connect
- **Status change** — buffered whenever `CurrentStatus` differs from the previous message
- **Progress milestones** — buffered when layer progress crosses 25 %, 50 %, or 75 %
- **Notices** — buffered from `sdcp/notice` messages pushed by the firmware

---

## Shutdown (`stop`)

Called on `SIGTERM`, `SIGINT`, or an unhandled exception from `gather`:

1. `is_running = False` — poll and heartbeat loops exit on next iteration
2. `poll_task.cancel()` / `heartbeat_task.cancel()` / `websocket_task.cancel()`
3. `centauri_client.disconnect()` — closes the WS connection cleanly
4. `discord_notifier.__aexit__()` — closes the aiohttp session

---

## Entry points

```python
# Called by main.py
async def main():
    service = AlertNotificationService()
    await service.start()
```

`main.py` calls `asyncio.run(main())`. `start()` blocks until the service stops.
