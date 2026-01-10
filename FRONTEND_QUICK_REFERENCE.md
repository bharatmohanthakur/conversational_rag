# Frontend Streaming Integration - Quick Reference

Quick copy-paste examples for common scenarios.

## Basic Setup

### TypeScript Types

```typescript
interface StreamEvent {
  type: 'status' | 'token' | 'done' | 'error' | 'progress' | 'source_found' | 'code_block_start' | 'code' | 'code_block_end';
  message?: string;      // For status/progress events
  text?: string;         // For token/code events
  metadata?: any;        // For done events
  error?: string;        // For error events
  percentage?: number;   // For progress events
  index?: number;        // For source_found events
  source?: string;       // For source_found events
  score?: number;        // For source_found events
  language?: string;     // For code_block_start events
}
```

### Minimal Working Example

```typescript
async function streamQuery(query: string, userId: string = 'default_user') {
  const response = await fetch('http://localhost:8060/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, user_id: userId })
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let text = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        
        if (data.type === 'token' || data.type === 'code') {
          text += data.text;
          // Update UI here
        } else if (data.type === 'code_block_start') {
          text += `\n\n\`\`\`${data.language}\n`;
        } else if (data.type === 'code_block_end') {
          text += '\n```\n';
        } else if (data.type === 'progress') {
          // Update progress bar: data.percentage, data.message
        } else if (data.type === 'source_found') {
          // Add source: data.index, data.source, data.score
        } else if (data.type === 'done') {
          // Handle completion
          return { text, metadata: data.metadata };
        }
      }
    }
  }
}
```

## React Hook (Minimal)

```typescript
import { useState } from 'react';

export function useStream() {
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const stream = async (query: string) => {
    setLoading(true);
    setText('');
    
    const response = await fetch('http://localhost:8060/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, user_id: 'user' })
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          
          if (data.type === 'status') setStatus(data.message);
          if (data.type === 'token') {
            accumulated += data.text;
            setText(accumulated);
          }
          if (data.type === 'done') {
            setLoading(false);
            return data.metadata;
          }
        }
      }
    }
  };

  return { text, status, loading, stream };
}
```

## Vue 3 Composition API

```typescript
import { ref } from 'vue';

export function useStreaming() {
  const text = ref('');
  const status = ref('');
  const loading = ref(false);

  const streamQuery = async (query: string) => {
    loading.value = true;
    text.value = '';
    
    const response = await fetch('http://localhost:8060/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, user_id: 'user' })
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          
          if (data.type === 'status') status.value = data.message;
          if (data.type === 'token') {
            accumulated += data.text;
            text.value = accumulated;
          }
          if (data.type === 'done') {
            loading.value = false;
            return data.metadata;
          }
        }
      }
    }
  };

  return { text, status, loading, streamQuery };
}
```

## Error Handling

```typescript
try {
  await streamQuery(query);
} catch (error) {
  if (error instanceof TypeError) {
    // Network error
    console.error('Connection failed');
  } else {
    // Other error
    console.error('Error:', error);
  }
}
```

## Cancellation

```typescript
const controller = new AbortController();

fetch(url, {
  signal: controller.signal,
  // ... other options
});

// Cancel request
controller.abort();
```

## Status Messages Reference

- `"🤔 Understanding your question..."` - Initial processing
- `"👤 Analyzing your context..."` - Context analysis
- `"🔍 Searching knowledge base..."` - RAG retrieval
- `"✨ Crafting response..."` - Response generation

## Common Issues

**Issue**: Tokens not appearing
**Fix**: Check buffer handling - incomplete lines must be kept

**Issue**: JSON parse errors
**Fix**: Only parse complete lines, skip empty lines

**Issue**: Connection drops
**Fix**: Implement retry logic with exponential backoff

**Issue**: Memory leaks
**Fix**: Always release reader and abort on unmount
