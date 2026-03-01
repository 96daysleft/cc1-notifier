# Centauri Alert Notifier (CC1-Notifier) - Python

A Python-based service that connects to the Centauri Carbon system via WebSocket and sends real-time alert notifications to Discord via webhooks. Built with modern async Python using WebSocket patterns inspired by the [OctoEverywhere WebSocket client](https://github.com/OctoEverywhere/octowebsocket-client).

## Features

- 🔌 **WebSocket Connection**: Real-time connection to Centauri Carbon on port 3000
- 🎯 **Discord Integration**: Beautiful, formatted alert notifications sent to Discord channels
- 💓 **Heartbeat Monitoring**: Automatic heartbeat to keep WebSocket connection alive
- 🔄 **Auto-Reconnect**: Automatic reconnection with exponential backoff on connection loss
- 🐳 **Docker Ready**: Fully containerized for easy deployment
- ⚙️ **Configurable**: Flexible polling intervals and alert filtering
- 📊 **Rich Notifications**: Color-coded alerts with severity indicators and detailed information
- 🐍 **Modern Python**: Built with Python 3.11+ using async/await patterns
- 📝 **Structured Logging**: Beautiful colored logs with structured data
- 🛡️ **Error Handling**: Robust error handling and graceful shutdown

## Prerequisites

- Python 3.11+ 
- Docker (optional, for containerized deployment)
- Discord webhook URL
- Access to Centauri Carbon WebSocket server

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd cc1-notifier
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Centauri WebSocket Configuration (connects to port 3000)
CENTAURI_IP=ws://your-centauri-server

# Discord Configuration
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url_here

# Polling Configuration
POLL_INTERVAL_MINUTES=5
MAX_ALERTS_PER_POLL=10

# Logging Configuration
LOG_LEVEL=INFO

# Connection Settings
SKIP_CONNECTION_TEST=true

# Notification Settings
NOTIFY_ON_START=true
NOTIFY_ON_SHUTDOWN=true
```

### 3. Run the Service

#### Development Mode (Auto-setup)
```bash
./run.sh
```

#### Manual Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the service
python main.py
```

#### Docker Mode
```bash
# Using Docker Compose (recommended)
docker-compose up -d

# Or using Docker directly
docker build -t cc1-notifier .
docker run --env-file .env cc1-notifier
```

## Configuration

| Environment Variable | Description | Default | Required |
|---------------------|-------------|---------|----------|
| `CENTAURI_API_URL` | Centauri WebSocket server URL | `ws://localhost` | ✅ |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | - | ✅ |
| `POLL_INTERVAL_MINUTES` | Alert buffer check interval in minutes | `5` | ❌ |
| `MAX_ALERTS_PER_POLL` | Maximum alerts to process per check | `10` | ❌ |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` | ❌ |
| `SKIP_CONNECTION_TEST` | Skip initial WebSocket connection test | `true` | ❌ |
| `NOTIFY_ON_START` | Send an alert when a print job starts | `true` | ❌ |
| `NOTIFY_ON_SHUTDOWN` | Send an alert when the printer goes idle/shuts down | `true` | ❌ |

## Discord Webhook Setup

1. Go to your Discord server settings
2. Navigate to **Integrations** → **Webhooks**
3. Click **Create Webhook**
4. Customize the webhook name and channel
5. Copy the webhook URL and add it to your `.env` file

## WebSocket Protocol

The service connects to Centauri Carbon via WebSocket on **port 3000** and supports the following message types:

### Outgoing Messages
- `subscribe`: Subscribe to alert channel
- `get_alerts`: Request current alerts
- `heartbeat`: Keep connection alive

### Incoming Messages
- `alert`: Single new alert
- `alerts`: Multiple alerts or response to get_alerts
- `heartbeat`: Heartbeat response

### Example WebSocket Messages

**Subscribe to alerts:**
```json
{
  "type": "subscribe",
  "channel": "alerts"
}
```

**Request all alerts:**
```json
{
  "type": "get_alerts",
  "request_id": "1234567890"
}
```

**Heartbeat:**
```json
{
  "type": "heartbeat",
  "timestamp": "2026-02-22T13:50:00.000Z"
}
```

## Alert Format

Alerts received from Centauri Carbon should follow this structure:

```python
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

class Alert(BaseModel):
    id: str
    title: str
    description: str
    severity: Literal['low', 'medium', 'high', 'critical']
    timestamp: str
    source: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
```

## Docker Deployment

### Using Docker Compose (Recommended)

```yaml
version: '3.8'
services:
  cc1-notifier:
    build: .
    environment:
      - CENTAURI_IP=ws://centauri-carbon-server
      - DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook
      - POLL_INTERVAL_MINUTES=5
    restart: unless-stopped
```

### Environment File

Create a `.env` file for Docker:

```bash
# .env
CENTAURI_IP=ws://your-centauri-server
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url
POLL_INTERVAL_MINUTES=5
MAX_ALERTS_PER_POLL=10
LOG_LEVEL=INFO
SKIP_CONNECTION_TEST=true
NOTIFY_ON_START=true
NOTIFY_ON_SHUTDOWN=true
```

## Development

### Project Structure

```
cc1-notifier/
├── src/
│   ├── __init__.py           # Package initialization
│   ├── models.py             # Pydantic data models
│   ├── config.py             # Configuration and logging
│   ├── websocket_client.py   # WebSocket client for Centauri
│   ├── discord_notifier.py   # Discord webhook integration
│   └── service.py            # Main service orchestrator
├── main.py                   # Entry point
├── requirements.txt          # Python dependencies
├── run.sh                    # Development script
├── Dockerfile               # Docker container config
├── docker-compose.yml       # Docker Compose config
└── README.md                # This file
```

### Dependencies

The project uses modern Python libraries:

- **websockets**: WebSocket client library
- **aiohttp**: Async HTTP client for Discord webhooks
- **pydantic**: Data validation and serialization
- **structlog**: Structured logging
- **python-dotenv**: Environment variable management
- **colorama**: Colored terminal output

### Scripts

- `python main.py` - Run the service directly
- `./run.sh` - Development script with auto-setup
- `docker-compose up -d` - Start with Docker Compose
- `docker-compose logs -f` - View Docker logs
- `docker-compose down` - Stop Docker Compose

## Monitoring and Logs

The service provides comprehensive structured logging with timestamps and colored output:

```bash
2026-02-22T21:47:10.761Z [INFO] Service: 🚀 Starting Centauri Alert Notification Service...
2026-02-22T21:47:11.285Z [INFO] CentauriWS: Connecting to Centauri WebSocket url=ws://192.168.45.245:3000 
2026-02-22T21:47:12.531Z [INFO] CentauriWS: ✅ Connected to Centauri WebSocket
2026-02-22T21:47:13.142Z [INFO] Discord: ✅ Test message - Discord webhook connection successful!
2026-02-22T21:47:14.023Z [INFO] Service: 🔄 Alert polling started interval_minutes=5
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check if Centauri Carbon server is running on port 3000
   - Verify the WebSocket URL format (`ws://hostname` or `wss://hostname`)
   - Check firewall and network connectivity

2. **Discord Webhook Errors**
   - Verify webhook URL is correct and active
   - Check Discord server permissions
   - Ensure webhook channel still exists

3. **No Alerts Received**
   - Check WebSocket connection status in logs
   - Verify alert subscription was successful
   - Monitor heartbeat responses

4. **Python Import Errors**
   - Ensure Python 3.11+ is installed
   - Activate virtual environment: `source venv/bin/activate`
   - Install dependencies: `pip install -r requirements.txt`

### Debug Mode

Enable debug logging by setting `LOG_LEVEL=DEBUG` in your environment:

```env
LOG_LEVEL=DEBUG
```

This will provide detailed WebSocket message logs and connection status information.

## Comparison with Node.js Version

This Python implementation offers several advantages:

- **Better Error Handling**: More robust exception handling with structured logging
- **Modern Async**: Uses Python's native async/await patterns
- **Type Safety**: Full Pydantic validation for all data structures
- **Easier Development**: Simpler dependency management and development setup
- **Better Logging**: Structured logs with colors and better formatting
- **Resource Efficiency**: Lower memory footprint compared to Node.js

## License

ISC License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section
- Review the logs for error messages
- Create an issue in the repository

---

*Built with ❤️ using Python and inspired by [OctoEverywhere's WebSocket patterns](https://github.com/OctoEverywhere/octowebsocket-client)*

*Protocol reverse-engineering assisted by the Open Centauri project.*
