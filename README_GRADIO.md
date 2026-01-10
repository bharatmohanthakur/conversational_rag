# Gradio Streaming Application

A beautiful Gradio interface for testing and using the RAG server's streaming endpoint.

## Features

- ⚡ **Real-time streaming**: Word-by-word response delivery
- 📊 **Status updates**: Shows intermediate progress (like Gemini/Claude)
- 💬 **Chat interface**: Natural conversation flow with history
- 📈 **Metadata display**: Complete response metadata in JSON format
- 🔄 **Server status**: Real-time connection status check
- 🎨 **Modern UI**: Clean, user-friendly interface

## Installation

Make sure you have Gradio installed:

```bash
pip install gradio requests
```

Or if using the existing virtual environment:

```bash
source /home/admincsp/multimodal-rag/azadea/.venv/bin/activate
pip install gradio
```

## Usage

### 1. Start the RAG Server

First, ensure the RAG server is running:

```bash
cd /home/admincsp/conversational_rag
source /home/admincsp/multimodal-rag/azadea/.venv/bin/activate
python rag_server.py
```

The server should be running on `http://localhost:8060`

### 2. Start the Gradio Application

In a new terminal:

```bash
cd /home/admincsp/conversational_rag
source /home/admincsp/multimodal-rag/azadea/.venv/bin/activate
python gradio_streaming_app.py
```

The Gradio app will start on `http://localhost:7860`

### 3. Access the Interface

Open your browser and navigate to:
- **Local**: `http://localhost:7860`
- **Network**: `http://<your-server-ip>:7860`

## Interface Components

1. **Server Status**: Shows connection status to RAG server
2. **User ID**: Set your user ID for conversation tracking
3. **Chat Interface**: Main conversation area with streaming responses
4. **Status Display**: Shows current processing status (e.g., "🔍 Searching knowledge base...")
5. **Message Input**: Type your questions here
6. **Metadata Display**: Expandable section showing complete response metadata

## Example Queries

- "hi" - Test greeting responses
- "What is the maternity leave policy?" - Test RAG queries
- "What are the working hours?" - Test clarification flow
- "Tell me about vacation policy" - Test general queries

## Configuration

You can modify the API endpoint in `gradio_streaming_app.py`:

```python
API_BASE_URL = "http://localhost:8060"  # Change if server is on different host/port
```

## Troubleshooting

### Server Not Connected

If you see "❌ Not Connected":
1. Check if RAG server is running: `curl http://localhost:8060/health`
2. Verify the port matches (default: 8060)
3. Check firewall settings if accessing remotely

### Streaming Not Working

1. Ensure you're using the `/query/stream` endpoint
2. Check browser console for errors
3. Verify network connectivity

### Slow Responses

- RAG queries can take 20-30 seconds for complex questions
- Status messages will show progress
- Check server logs for bottlenecks

## Technical Details

- **Streaming Protocol**: Server-Sent Events (SSE)
- **Response Format**: JSON with `type` field (`status`, `token`, `done`, `error`)
- **Update Frequency**: Real-time as tokens arrive
- **Timeout**: 120 seconds per request

## Screenshots

The interface includes:
- Real-time status updates during processing
- Word-by-word streaming display
- Conversation history
- Expandable metadata section
- Example queries for quick testing
