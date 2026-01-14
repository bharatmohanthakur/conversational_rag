# AI Test Agent for RAG System Evaluation

## Overview

This is an advanced, conversational AI test agent that comprehensively evaluates the RAG system by:

1. **Loading test questions** from CSV file (~84 valid questions)
2. **Sending queries** to the RAG server
3. **Deep evaluation** using LLM reasoning (thinks like a human tester)
4. **Generating detailed reports** with metrics, reasoning, and suggestions
5. **Conversational thinking** - evaluates responses as a human would

## Features

### 🧠 Deep Evaluation
- Uses LLM to think deeply about each response
- Evaluates accuracy, completeness, relevance, and semantic similarity
- Provides conversational reasoning (explains thinking step-by-step)
- Identifies issues and suggests improvements

### 📊 Comprehensive Metrics
- **Accuracy Score** (0-10): Overall quality assessment
- **Semantic Similarity** (0-1): How similar to expected answer
- **Completeness Score** (0-1): Coverage of expected information
- **Relevance Score** (0-1): Directness to the question
- **Response Time**: Performance measurement

### 📁 Detailed Reports
- **JSON Summary**: High-level statistics and category breakdown
- **JSON Detailed**: Complete results for all questions
- **Markdown Report**: Human-readable detailed analysis

## Usage

### Basic Usage

```bash
# Test all questions (~84 questions, takes ~30-40 minutes)
python3 test_agent.py

# Test first 10 questions (for quick testing)
python3 test_agent.py --limit 10

# Quiet mode (less verbose output)
python3 test_agent.py --limit 50 --quiet

# Custom server URL
python3 test_agent.py --server http://localhost:8060
```

### Command Line Options

- `--limit N`: Test only first N questions (useful for quick testing)
- `--quiet`: Reduce verbose output (only show progress)
- `--server URL`: Override RAG server URL (default: http://localhost:8060)

## Requirements

### Environment Variables

The agent needs Azure OpenAI credentials for evaluation:

```bash
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_CHAT_DEPLOYMENT=gpt-4o-mini
```

### Python Dependencies

```bash
pip install requests openai python-dotenv
```

## Output

Reports are saved to `/home/admincsp/frontend_integration/test_reports/`:

1. **test_summary_TIMESTAMP.json**: Summary statistics and category breakdown
2. **test_detailed_TIMESTAMP.json**: Complete results for all questions
3. **test_report_TIMESTAMP.md**: Human-readable markdown report

### Report Structure

#### Summary Report
```json
{
  "timestamp": "20260113_143022",
  "stats": {
    "total": 84,
    "passed": 60,
    "failed": 20,
    "errors": 4,
    "avg_accuracy": 7.5,
    "avg_response_time": 28.3
  },
  "categories": {
    "Insurance": {
      "total": 50,
      "passed": 40,
      "failed": 10,
      "avg_accuracy": 8.2
    }
  }
}
```

#### Detailed Report
Each question includes:
- Original question and expected answer
- Actual AI response
- All metrics (accuracy, similarity, completeness, relevance)
- Deep evaluation reasoning
- Issues found
- Improvement suggestions
- Response time and sources

## How It Works

### 1. Question Loading
- Reads CSV file with test questions
- Parses category, question, expected answer, and owner
- Skips empty or invalid rows

### 2. Query Execution
- Sends HTTP POST to `/query` endpoint
- Captures response, sources, confidence, and timing
- Handles errors and timeouts gracefully

### 3. Deep Evaluation
- Uses Azure OpenAI to evaluate each response
- Thinks conversationally about quality
- Compares actual vs expected answers
- Identifies strengths and weaknesses

### 4. Report Generation
- Calculates statistics
- Groups by category
- Generates multiple report formats
- Provides actionable insights

## Evaluation Criteria

The agent evaluates responses on:

1. **Understanding**: Does AI understand the question?
2. **Accuracy**: Is information correct?
3. **Completeness**: Are all important points covered?
4. **Relevance**: Is it directly answering the question?
5. **Clarity**: Is it well-structured?
6. **Missing Information**: What's absent?
7. **Extra Information**: Is there unnecessary content?
8. **Tone & Style**: Is it professional?

## Example Output

```
🚀 Starting comprehensive test run
📊 Total questions: 1048
🌐 RAG Server: http://localhost:8060
⏰ Started at: 2026-01-13 14:30:22

================================================================================
📋 Testing Question #2
Category: Insurance
Question: does my insurance covers me outside my residence country?...
================================================================================
⏱️  Response time: 28.45s
✅ Got response (523 chars)
📚 Sources: 3
🎯 Confidence: HIGH
🧠 Deep evaluation in progress...
📊 Accuracy Score: 8.5/10.0
📈 Semantic Similarity: 0.87
✅ Completeness: 0.92
🎯 Relevance: 0.95
⚠️  Issues: Minor formatting issue, Could mention reimbursement process more clearly

📈 Progress: 10/1048 (1%)
```

## Tips

1. **Start Small**: Use `--limit 10` to test the agent first
2. **Check Server**: Ensure RAG server is running before starting
3. **Monitor Progress**: Watch for errors or timeouts
4. **Review Reports**: Check markdown report for detailed insights
5. **Category Analysis**: Use summary JSON to identify weak categories

## Troubleshooting

### Server Connection Error
```
❌ Cannot connect to RAG server at http://localhost:8060
```
**Solution**: Ensure RAG server is running on port 8060

### Evaluation Errors
If evaluation fails, the agent will:
- Continue testing other questions
- Use default scores (5.0)
- Log the error for review

### Timeout Issues
If queries timeout:
- Check server performance
- Increase timeout in code (default: 120s)
- Test with smaller limit first

## Advanced Usage

### Custom Evaluation
Modify `ConversationalEvaluator.evaluate_response()` to customize evaluation criteria.

### Custom Reports
Extend `_generate_markdown_report()` to add custom report sections.

### Parallel Testing
For faster testing, you can modify the code to use async/threading (not included by default to avoid overwhelming the server).

## Notes

- The agent is designed to be conversational and think deeply
- Evaluation uses LLM reasoning, not just keyword matching
- Reports include actionable improvement suggestions
- All results are saved for later analysis
