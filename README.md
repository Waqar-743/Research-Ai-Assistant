# Multi-Agent Research Assistant

A sophisticated FastAPI backend that leverages multiple AI agents to conduct comprehensive research, answer complex questions, and synthesize information from multiple sources.



##  Features

- **Multi-Agent Orchestration**: 5 specialized AI agents working in concert
- **Real-time Updates**: WebSocket support for live progress tracking
- **Multiple Data Sources**: Google, NewsAPI, ArXiv, PubMed, Wikipedia
- **Quality Assurance**: Built-in fact-checking and source verification
- **Report Generation**: Markdown, HTML, and PDF formats
- **Citation Management**: APA, MLA, Chicago styles
- **Configurable Research Mode**: Auto (hands-free) or Supervised (human-in-the-loop)

## 🤖 Agent Architecture

| Agent | Role | LLM Model |
|-------|------|-----------|
| **User Proxy** | Query clarification, human oversight | DeepSeek Chat |
| **Researcher** | Search and information gathering | DeepSeek Chat |
| **Analyst** | Information synthesis and pattern detection | Claude Sonnet |
| **Fact-Checker** | Validation and verification | GPT-4o |
| **Report Generator** | Report writing and formatting | Claude Sonnet |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 7.0+ (or Docker)
- API Keys:
  - OpenRouter API Key
  - Google Custom Search API Key
  - NewsAPI Key (optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Research-Assistant
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

5. **Start MongoDB** (using Docker)
   ```bash
   docker compose up mongodb -d
   ```

6. **Run the application**
   ```bash
   uvicorn app.main:app --reload
   ```

### Using Docker

```bash
# Development mode
docker compose up -d

# With MongoDB admin UI
docker compose --profile debug up -d

# Production mode
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 📚 API Documentation

Once running, access the API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/research/start` | POST | Start a new research session |
| `/api/v1/research/{session_id}` | GET | Get research status |
| `/api/v1/research/{session_id}/results` | GET | Get research results |
| `/api/v1/history/` | GET | List all research sessions |
| `/ws/{session_id}` | WebSocket | Real-time progress updates |

### Starting a Research Session

```bash
curl -X POST "http://localhost:8000/api/v1/research/start" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the latest developments in quantum computing?",
    "focus_areas": ["hardware", "algorithms", "applications"],
    "research_mode": "auto",
    "max_sources": 100,
    "report_format": "markdown",
    "citation_style": "APA"
  }'
```

### WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/{session_id}');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Update:', data);
  // data.type: 'agent_status_update' | 'phase_update' | 'research_complete' | 'research_error'
  // data.agent: 'researcher' | 'analyst' | 'fact_checker' | 'report_generator'
  // data.status: 'idle' | 'in_progress' | 'completed' | 'failed'
  // data.progress: 0-100
};
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment (development/production) | development |
| `DEBUG` | Enable debug mode | true |
| `MONGODB_URL` | MongoDB connection string | mongodb://localhost:27017 |
| `OPENROUTER_API_KEY` | OpenRouter API key | (required) |
| `GOOGLE_API_KEY` | Google Custom Search API key | (required) |
| `GOOGLE_CSE_ID` | Google Custom Search Engine ID | (required) |
| `NEWSAPI_KEY` | NewsAPI key | (optional) |

### Research Modes

- **Auto Mode** (default): Research runs autonomously without human intervention
- **Supervised Mode**: Pauses at key checkpoints for human approval and feedback

## 📁 Project Structure

```
Research-Assistant/
├── app/
│   ├── agents/              # AI Agent implementations
│   │   ├── base_agent.py
│   │   ├── researcher.py
│   │   ├── analyst.py
│   │   ├── fact_checker.py
│   │   ├── report_generator.py
│   │   ├── user_proxy.py
│   │   └── orchestrator.py
│   ├── api/                 # API endpoints
│   │   ├── v1/
│   │   │   ├── research.py
│   │   │   ├── history.py
│   │   │   ├── status.py
│   │   │   └── health.py
│   │   └── websocket.py
│   ├── database/            # Database layer
│   │   ├── connection.py
│   │   ├── schemas.py
│   │   └── repositories.py
│   ├── tools/               # Agent tools
│   │   ├── search_tools.py
│   │   ├── validation_tools.py
│   │   ├── formatting_tools.py
│   │   └── llm_tools.py
│   ├── services/            # Business logic
│   ├── middleware/          # HTTP middleware
│   ├── models/              # Pydantic models
│   ├── utils/               # Utilities
│   ├── config.py            # Configuration
│   └── main.py              # Application entry
├── docker/                  # Docker configuration
├── tests/                   # Test suite
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_agents.py -v
```

## 🚢 Deployment

### Azure Deployment

1. Create an Azure Container App or App Service
2. Set up Azure Cosmos DB for MongoDB API
3. Configure environment variables in Azure
4. Deploy using GitHub Actions or Azure CLI

```bash
# Azure CLI deployment
az containerapp up \
  --name research-assistant \
  --resource-group my-rg \
  --location eastus \
  --source .
```

## 📄 License

MIT License

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📞 Support

For issues and questions, please open a GitHub issue.
