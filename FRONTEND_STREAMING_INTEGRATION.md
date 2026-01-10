# Frontend Integration Guide: Streaming Endpoint

This guide provides everything frontend engineers need to integrate with the RAG server's streaming endpoint (`/query/stream`).

## Table of Contents

1. [Overview](#overview)
2. [Endpoint Details](#endpoint-details)
3. [Server-Sent Events (SSE) Protocol](#server-sent-events-sse-protocol)
4. [Event Types](#event-types)
5. [JavaScript/TypeScript Examples](#javascripttypescript-examples)
6. [React Integration Example](#react-integration-example)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)
9. [UI/UX Recommendations](#uiux-recommendations)
10. [Testing](#testing)

---

## Overview

The `/query/stream` endpoint provides **real-time streaming responses** using Server-Sent Events (SSE). This enables:

- ⚡ **Progressive response delivery** - Word-by-word streaming (like ChatGPT/Gemini/Claude)
- 📊 **Intermediate status updates** - Show progress during processing
- 💬 **Natural conversation flow** - Better user experience
- 📈 **Complete metadata** - Full response details when streaming completes

### Key Features

- **Streaming Protocol**: Server-Sent Events (SSE)
- **Response Format**: JSON messages with `type` field
- **Update Frequency**: Real-time as tokens arrive
- **Timeout**: 120 seconds per request

---

## Endpoint Details

### Base URL

```
http://localhost:8060
```

For production, replace with your server URL.

### Endpoint

```
POST /query/stream
```

### Request Format

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "query": "What is the maternity leave policy?",
  "user_id": "user_123"
}
```

**Request Schema:**
```typescript
interface QueryRequest {
  query: string;        // Required: User's question
  user_id?: string;     // Optional: Defaults to "default_user"
}
```

### Response Format

The endpoint returns **Server-Sent Events (SSE)** with JSON payloads.

**Content-Type:** `text/event-stream`

**Response Format:**
```
data: {"type": "status", "message": "🤔 Understanding your question..."}

data: {"type": "token", "text": "Great"}

data: {"type": "token", "text": " question!"}

data: {"type": "done", "metadata": {...}}
```

---

## Server-Sent Events (SSE) Protocol

### What is SSE?

Server-Sent Events is a web standard that allows a server to push data to a client over HTTP. It's simpler than WebSockets and perfect for one-way streaming.

### SSE Message Format

Each message follows this format:
```
data: <JSON_STRING>

```

- `data:` prefix is required
- JSON string contains the actual payload
- Empty line (`\n\n`) separates messages

### Browser Support

SSE is supported in all modern browsers:
- ✅ Chrome/Edge (all versions)
- ✅ Firefox (all versions)
- ✅ Safari (all versions)
- ✅ Mobile browsers

---

## Event Types

The streaming endpoint sends 4 types of events:

### 1. Status Events

**Type:** `status`

**Purpose:** Show intermediate progress updates during processing

**Format:**
```json
{
  "type": "status",
  "message": "🤔 Understanding your question..."
}
```

**Possible Status Messages:**
- `"🤔 Understanding your question..."` - Initial processing
- `"👤 Analyzing your context..."` - User profile/context analysis
- `"🔍 Searching knowledge base..."` - RAG retrieval phase
- `"✨ Crafting response..."` - Response generation phase

**When to Use:**
- Display in a status indicator
- Show progress to users during long queries
- Update UI to indicate processing stage

### 2. Token Events

**Type:** `token`

**Purpose:** Stream individual words/tokens of the response

**Format:**
```json
{
  "type": "token",
  "text": "Great"
}
```

**Notes:**
- Tokens arrive word-by-word
- First token may not have leading space
- Subsequent tokens include leading space: `" text"`
- Accumulate tokens to build complete response

**When to Use:**
- Append to response display in real-time
- Create typing effect
- Show progressive response building

### 3. Done Event

**Type:** `done`

**Purpose:** Signal completion with full metadata

**Format:**
```json
{
  "type": "done",
  "metadata": {
    "request_id": "a15f2619",
    "agent": "LangGraph Decomposition",
    "complexity": "SIMPLE",
    "sub_queries": [],
    "sources": [
      {
        "source": "HRD - Maternity Leave Policy.md",
        "score": 0.95,
        "text": "..."
      }
    ],
    "elapsed_sec": 28.894,
    "quality": {
      "confidence": "high",
      "confidence_score": 0.85,
      "source_quality": "good",
      "has_sufficient_context": true,
      "should_show_warning": false,
      "warning_message": null
    },
    "enhancements": ["improved_tone", "added_context"]
  }
}
```

**Metadata Fields:**
- `request_id`: Unique request identifier
- `agent`: Processing agent used
- `complexity`: Query complexity level
- `sub_queries`: List of sub-queries (if decomposed)
- `sources`: Array of source documents
- `elapsed_sec`: Total processing time
- `quality`: Answer quality metrics
- `enhancements`: List of enhancements applied

**When to Use:**
- Display source references
- Show confidence indicators
- Log performance metrics
- Update conversation history

### 4. Progress Events

**Type:** `progress`

**Purpose:** Show detailed progress with percentage during RAG processing

**Format:**
```json
{
  "type": "progress",
  "percentage": 30,
  "message": "Querying vector database..."
}
```

**Possible Progress Messages:**
- `10%` - "Initializing search..."
- `30%` - "Querying vector database..."
- `70%` - "Processing results..."
- `85%` - "Analyzing sources..."
- `95%` - "Preparing response..."
- `100%` - "Streaming response..."

**When to Use:**
- Display progress bar
- Show percentage completion
- Update loading indicators with specific stages

### 5. Source Found Events

**Type:** `source_found`

**Purpose:** Stream individual sources as they're discovered (like Gemini's Search Grounding)

**Format:**
```json
{
  "type": "source_found",
  "index": 1,
  "source": "Maternity Leave Policy",
  "score": 0.95
}
```

**Fields:**
- `index`: Source number (1-5 for top sources)
- `source`: Source document name
- `score`: Relevance score (0.0-1.0)

**When to Use:**
- Show sources in real-time as they're found
- Display source list progressively
- Build source references dynamically

### 6. Code Block Start Event

**Type:** `code_block_start`

**Purpose:** Signal the start of a code block in the response

**Format:**
```json
{
  "type": "code_block_start",
  "language": "python"
}
```

**When to Use:**
- Prepare code block rendering
- Set up syntax highlighting
- Create code block container

### 7. Code Event

**Type:** `code`

**Purpose:** Stream code content (faster than token-by-token)

**Format:**
```json
{
  "type": "code",
  "text": "def hello():\n    print('Hello')"
}
```

**When to Use:**
- Append code content to code block
- Render code with syntax highlighting
- Stream code faster than regular text

### 8. Code Block End Event

**Type:** `code_block_end`

**Purpose:** Signal the end of a code block

**Format:**
```json
{
  "type": "code_block_end"
}
```

**When to Use:**
- Close code block rendering
- Finalize syntax highlighting
- Return to normal text streaming

### 9. Error Event

**Type:** `error`

**Purpose:** Signal errors during processing

**Format:**
```json
{
  "type": "error",
  "error": "Connection timeout"
}
```

**When to Use:**
- Display error messages to users
- Log errors for debugging
- Trigger retry mechanisms

---

## JavaScript/TypeScript Examples

### Basic JavaScript Example

```javascript
async function streamQuery(query, userId = 'default_user') {
  const response = await fetch('http://localhost:8060/query/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query: query,
      user_id: userId
    })
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  let accumulatedText = '';
  let currentStatus = '';

  while (true) {
    const { done, value } = await reader.read();
    
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || ''; // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const jsonStr = line.slice(6); // Remove 'data: ' prefix
        try {
          const data = JSON.parse(jsonStr);
          
          switch (data.type) {
            case 'status':
              currentStatus = data.message;
              updateStatusDisplay(currentStatus);
              break;
              
            case 'progress':
              const percentage = data.percentage;
              const progressMsg = data.message;
              currentStatus = `${progressMsg} (${percentage}%)`;
              updateProgressBar(percentage);
              updateStatusDisplay(currentStatus);
              break;
              
            case 'source_found':
              const sourceName = data.source;
              const sourceIndex = data.index;
              const score = data.score;
              addSourceToList(sourceIndex, sourceName, score);
              currentStatus = `📚 Found source ${sourceIndex}: ${sourceName}`;
              updateStatusDisplay(currentStatus);
              break;
              
            case 'code_block_start':
              const language = data.language;
              accumulatedText += `\n\n\`\`\`${language}\n`;
              updateResponseDisplay(accumulatedText);
              break;
              
            case 'code':
              accumulatedText += data.text;
              updateResponseDisplay(accumulatedText);
              break;
              
            case 'code_block_end':
              accumulatedText += '\n```\n';
              updateResponseDisplay(accumulatedText);
              break;
              
            case 'token':
              accumulatedText += data.text;
              updateResponseDisplay(accumulatedText);
              break;
              
            case 'done':
              handleCompletion(data.metadata);
              break;
              
            case 'error':
              handleError(data.error);
              break;
          }
        } catch (e) {
          console.error('Failed to parse JSON:', e);
        }
      }
    }
  }

  return {
    text: accumulatedText,
    status: currentStatus,
    metadata: null // Will be set in 'done' event
  };
}

// Helper functions
function updateStatusDisplay(status) {
  const statusEl = document.getElementById('status');
  if (statusEl) statusEl.textContent = status;
}

function updateResponseDisplay(text) {
  const responseEl = document.getElementById('response');
  if (responseEl) responseEl.textContent = text;
}

function handleCompletion(metadata) {
  console.log('Sources:', metadata.sources);
  console.log('Confidence:', metadata.quality.confidence);
  // Update UI with metadata
}

function handleError(error) {
  alert(`Error: ${error}`);
}
```

### TypeScript Example with Types

```typescript
// Type definitions
interface QueryRequest {
  query: string;
  user_id?: string;
}

interface StatusEvent {
  type: 'status';
  message: string;
}

interface TokenEvent {
  type: 'token';
  text: string;
}

interface DoneEvent {
  type: 'done';
  metadata: {
    request_id: string;
    agent: string;
    complexity: string;
    sub_queries: string[];
    sources: Array<{
      source: string;
      score: number;
      text: string;
    }>;
    elapsed_sec: number;
    quality: {
      confidence: 'high' | 'medium' | 'low';
      confidence_score: number;
      source_quality: string;
      has_sufficient_context: boolean;
      should_show_warning: boolean;
      warning_message: string | null;
    };
    enhancements: string[];
  };
}

interface ErrorEvent {
  type: 'error';
  error: string;
}

interface ProgressEvent {
  type: 'progress';
  percentage: number;
  message: string;
}

interface SourceFoundEvent {
  type: 'source_found';
  index: number;
  source: string;
  score: number;
}

interface CodeBlockStartEvent {
  type: 'code_block_start';
  language: string;
}

interface CodeEvent {
  type: 'code';
  text: string;
}

interface CodeBlockEndEvent {
  type: 'code_block_end';
}

type StreamEvent = StatusEvent | TokenEvent | DoneEvent | ErrorEvent | ProgressEvent | SourceFoundEvent | CodeBlockStartEvent | CodeEvent | CodeBlockEndEvent;

// Stream handler class
class RAGStreamClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8060') {
    this.baseUrl = baseUrl;
  }

  async streamQuery(
    query: string,
    userId: string = 'default_user',
    callbacks: {
      onStatus?: (message: string) => void;
      onToken?: (text: string, accumulated: string) => void;
      onDone?: (metadata: DoneEvent['metadata']) => void;
      onError?: (error: string) => void;
    } = {}
  ): Promise<{ text: string; metadata: DoneEvent['metadata'] | null }> {
    const response = await fetch(`${this.baseUrl}/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: query.trim(),
        user_id: userId
      } as QueryRequest)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Response body is not readable');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let accumulatedText = '';
    let metadata: DoneEvent['metadata'] | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const event = JSON.parse(jsonStr) as StreamEvent;
              
              switch (event.type) {
                case 'status':
                  callbacks.onStatus?.(event.message);
                  break;
                  
                case 'progress':
                  callbacks.onStatus?.(`${event.message} (${event.percentage}%)`);
                  break;
                  
                case 'source_found':
                  callbacks.onStatus?.(`📚 Found source ${event.index}: ${event.source}`);
                  break;
                  
                case 'code_block_start':
                  accumulatedText += `\n\n\`\`\`${event.language}\n`;
                  callbacks.onToken?.('', accumulatedText);
                  break;
                  
                case 'code':
                  accumulatedText += event.text;
                  callbacks.onToken?.(event.text, accumulatedText);
                  break;
                  
                case 'code_block_end':
                  accumulatedText += '\n```\n';
                  callbacks.onToken?.('', accumulatedText);
                  break;
                  
                case 'token':
                  accumulatedText += event.text;
                  callbacks.onToken?.(event.text, accumulatedText);
                  break;
                  
                case 'done':
                  metadata = event.metadata;
                  callbacks.onDone?.(event.metadata);
                  break;
                  
                case 'error':
                  callbacks.onError?.(event.error);
                  throw new Error(event.error);
              }
            } catch (e) {
              if (e instanceof Error && e.message) {
                throw e;
              }
              console.warn('Failed to parse event:', e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { text: accumulatedText, metadata };
  }
}

// Usage
const client = new RAGStreamClient();

client.streamQuery('What is the maternity leave policy?', 'user_123', {
  onStatus: (message) => {
    console.log('Status:', message);
    // Update UI
  },
  onToken: (text, accumulated) => {
    console.log('Token:', text);
    // Update response display
    document.getElementById('response')!.textContent = accumulated;
  },
  onDone: (metadata) => {
    console.log('Complete!', metadata);
    // Show sources, confidence, etc.
  },
  onError: (error) => {
    console.error('Error:', error);
    // Show error to user
  }
});
```

---

## React Integration Example

### React Hook for Streaming

```typescript
import { useState, useCallback, useRef } from 'react';

interface UseStreamingQueryResult {
  text: string;
  status: string;
  metadata: any | null;
  isLoading: boolean;
  error: string | null;
  streamQuery: (query: string, userId?: string) => Promise<void>;
  reset: () => void;
}

export function useStreamingQuery(baseUrl: string = 'http://localhost:8060'): UseStreamingQueryResult {
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const [metadata, setMetadata] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const streamQuery = useCallback(async (query: string, userId: string = 'default_user') => {
    // Reset state
    setText('');
    setStatus('');
    setMetadata(null);
    setError(null);
    setIsLoading(true);

    // Create abort controller for cancellation
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await fetch(`${baseUrl}/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: query.trim(), user_id: userId }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            try {
              const data = JSON.parse(jsonStr);
              
              switch (data.type) {
                case 'status':
                  setStatus(data.message);
                  break;
                  
                case 'token':
                  accumulatedText += data.text;
                  setText(accumulatedText);
                  break;
                  
                case 'done':
                  setMetadata(data.metadata);
                  setIsLoading(false);
                  break;
                  
                case 'error':
                  throw new Error(data.error);
              }
            } catch (e) {
              console.warn('Failed to parse event:', e);
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Request aborted');
      } else {
        setError(err.message || 'An error occurred');
        setIsLoading(false);
      }
    }
  }, [baseUrl]);

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setText('');
    setStatus('');
    setMetadata(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    text,
    status,
    metadata,
    isLoading,
    error,
    streamQuery,
    reset
  };
}
```

### React Component Example

```tsx
import React, { useState } from 'react';
import { useStreamingQuery } from './useStreamingQuery';

export function ChatInterface() {
  const [query, setQuery] = useState('');
  const [userId] = useState('user_123');
  const { text, status, metadata, isLoading, error, streamQuery, reset } = useStreamingQuery();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;
    await streamQuery(query, userId);
  };

  return (
    <div className="chat-container">
      <div className="status-bar">
        {status && <div className="status">{status}</div>}
        {error && <div className="error">Error: {error}</div>}
      </div>

      <div className="response-area">
        {text ? (
          <div className="response" dangerouslySetInnerHTML={{ __html: text }} />
        ) : (
          <div className="placeholder">Your response will appear here...</div>
        )}
      </div>

      {metadata && (
        <div className="metadata">
          <h4>Sources:</h4>
          <ul>
            {metadata.sources?.map((source: any, i: number) => (
              <li key={i}>{source.source}</li>
            ))}
          </ul>
          <p>Confidence: {metadata.quality?.confidence} ({metadata.quality?.confidence_score})</p>
          <p>Time: {metadata.elapsed_sec}s</p>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question..."
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !query.trim()}>
          {isLoading ? 'Sending...' : 'Send'}
        </button>
        {isLoading && (
          <button type="button" onClick={reset}>
            Cancel
          </button>
        )}
      </form>
    </div>
  );
}
```

---

## Error Handling

### Network Errors

```typescript
try {
  await streamQuery(query, userId);
} catch (error) {
  if (error instanceof TypeError && error.message.includes('fetch')) {
    // Network error - server may be down
    showError('Cannot connect to server. Please check your connection.');
  } else if (error instanceof DOMException && error.name === 'AbortError') {
    // Request was cancelled
    console.log('Request cancelled');
  } else {
    // Other errors
    showError(`Error: ${error.message}`);
  }
}
```

### HTTP Errors

```typescript
const response = await fetch(url, options);

if (!response.ok) {
  if (response.status === 400) {
    // Bad request - invalid query
    throw new Error('Invalid query. Please check your input.');
  } else if (response.status === 500) {
    // Server error
    throw new Error('Server error. Please try again later.');
  } else if (response.status === 503) {
    // Service unavailable
    throw new Error('Service temporarily unavailable.');
  }
}
```

### Timeout Handling

```typescript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 120000); // 120 seconds

try {
  const response = await fetch(url, {
    ...options,
    signal: controller.signal
  });
  clearTimeout(timeoutId);
  // Process response
} catch (error) {
  clearTimeout(timeoutId);
  if (error.name === 'AbortError') {
    throw new Error('Request timeout. Please try again.');
  }
  throw error;
}
```

### Retry Logic

```typescript
async function streamQueryWithRetry(
  query: string,
  userId: string,
  maxRetries: number = 3
): Promise<void> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await streamQuery(query, userId);
      return; // Success
    } catch (error) {
      if (attempt === maxRetries) {
        throw error; // Final attempt failed
      }
      // Wait before retry (exponential backoff)
      await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
    }
  }
}
```

---

## Best Practices

### 1. Connection Management

- **Abort on unmount**: Cancel requests when component unmounts
- **Single request**: Prevent multiple simultaneous requests
- **Cleanup**: Release readers and close connections properly

```typescript
useEffect(() => {
  const controller = new AbortController();
  
  streamQuery(query, userId, { signal: controller.signal });
  
  return () => {
    controller.abort(); // Cleanup on unmount
  };
}, [query]);
```

### 2. Buffer Management

- **Handle incomplete lines**: Keep partial lines in buffer
- **Process complete lines**: Only parse complete JSON messages
- **Memory management**: Clear buffer after processing

### 3. UI Updates

- **Debounce updates**: For very fast streams, debounce UI updates
- **Batch updates**: Use `requestAnimationFrame` for smooth rendering
- **Loading states**: Show loading indicators during streaming

```typescript
let updateTimeout: NodeJS.Timeout;
function updateUI(text: string) {
  clearTimeout(updateTimeout);
  updateTimeout = setTimeout(() => {
    setResponseText(text);
  }, 16); // ~60fps
}
```

### 4. Error Recovery

- **Graceful degradation**: Fall back to non-streaming endpoint if SSE fails
- **User feedback**: Show clear error messages
- **Retry options**: Provide retry button for failed requests

### 5. Performance

- **Avoid re-renders**: Use refs for frequently updated values
- **Virtual scrolling**: For long responses
- **Lazy loading**: Load metadata only when needed

---

## UI/UX Recommendations

### Status Indicators

Show status messages prominently:

```tsx
{status && (
  <div className="status-indicator">
    <Spinner />
    <span>{status}</span>
  </div>
)}
```

### Progressive Response Display

Update response in real-time:

```tsx
<div className="response">
  {text ? (
    <Markdown>{text}</Markdown>
  ) : (
    <div className="typing-indicator">...</div>
  )}
</div>
```

### Source Display

Show sources when available:

```tsx
{metadata?.sources && (
  <div className="sources">
    <h4>Sources:</h4>
    {metadata.sources.map((source, i) => (
      <SourceBadge key={i} source={source.source} score={source.score} />
    ))}
  </div>
)}
```

### Confidence Indicators

Display confidence level:

```tsx
{metadata?.quality && (
  <div className={`confidence confidence-${metadata.quality.confidence}`}>
    <span>Confidence: {metadata.quality.confidence}</span>
    <ProgressBar value={metadata.quality.confidence_score} />
  </div>
)}
```

### Loading States

```tsx
{isLoading && (
  <div className="loading">
    <Spinner />
    <span>Processing your question...</span>
  </div>
)}
```

### Error States

```tsx
{error && (
  <div className="error-banner">
    <Icon name="error" />
    <span>{error}</span>
    <button onClick={retry}>Retry</button>
  </div>
)}
```

---

## Testing

### Unit Tests

```typescript
describe('RAGStreamClient', () => {
  it('should parse status events', async () => {
    const client = new RAGStreamClient();
    const onStatus = jest.fn();
    
    await client.streamQuery('test', 'user', { onStatus });
    
    expect(onStatus).toHaveBeenCalledWith('🤔 Understanding your question...');
  });
  
  it('should accumulate tokens', async () => {
    const client = new RAGStreamClient();
    let accumulated = '';
    const onToken = jest.fn((text, acc) => { accumulated = acc; });
    
    await client.streamQuery('test', 'user', { onToken });
    
    expect(accumulated.length).toBeGreaterThan(0);
  });
});
```

### Integration Tests

```typescript
describe('Streaming Integration', () => {
  it('should handle complete stream', async () => {
    const response = await fetch('http://localhost:8060/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'hi', user_id: 'test' })
    });
    
    expect(response.ok).toBe(true);
    expect(response.headers.get('content-type')).toContain('text/event-stream');
  });
});
```

### Manual Testing

1. **Test basic streaming:**
   ```bash
   curl -X POST http://localhost:8060/query/stream \
     -H "Content-Type: application/json" \
     -d '{"query": "hi", "user_id": "test"}' \
     --no-buffer
   ```

2. **Test error handling:**
   - Disconnect network
   - Send invalid query
   - Test timeout scenarios

3. **Test UI:**
   - Verify status updates appear
   - Check token streaming is smooth
   - Confirm metadata displays correctly

---

## Additional Resources

### API Documentation

- **Health Check**: `GET /health` - Check server status
- **Non-streaming**: `POST /query` - Fallback endpoint
- **Reset**: `POST /reset` - Clear conversation history

### Example Implementations

- **Gradio App**: See `gradio_streaming_app.py` for Python reference
- **React Hook**: See React examples above
- **Vanilla JS**: See JavaScript examples above

### Support

For issues or questions:
1. Check server logs: `logs/rag_server.log`
2. Verify server health: `GET /health`
3. Test with curl first before frontend integration

---

## Quick Start Checklist

- [ ] Set up base URL (default: `http://localhost:8060`)
- [ ] Implement SSE reader with buffer management
- [ ] Handle all 4 event types (status, token, done, error)
- [ ] Add error handling and retry logic
- [ ] Implement UI for status, response, and metadata
- [ ] Test with various query types
- [ ] Add loading and error states
- [ ] Optimize for performance (debouncing, batching)
- [ ] Test error scenarios (network, timeout, server errors)

---

**Happy Coding! 🚀**
