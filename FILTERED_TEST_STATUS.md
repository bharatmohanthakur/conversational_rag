# Filtered Test Run - Questions with Expected Answers Only

## Status: ✅ RUNNING

**Started**: 2026-01-14  
**Total Questions**: 47 (filtered from 84)  
**Questions with Expected Answers**: 47  
**Questions without Expected Answers**: 37 (skipped)  
**Estimated Duration**: ~20-25 minutes

## Why Filter?

Only questions with expected answers can be properly evaluated for accuracy. Testing all 84 questions would include 37 questions that can't be scored, making the results less meaningful.

## Monitor Progress

```bash
# Watch live progress
tail -f /home/admincsp/frontend_integration/filtered_test_run.log

# Check current question
tail -20 filtered_test_run.log | grep "Testing Question"

# Check scores
tail -30 filtered_test_run.log | grep "Accuracy Score"
```

## Expected Results

This filtered test will provide:
- **More accurate metrics** - All 47 questions can be evaluated
- **Better insights** - Focus on questions where we can measure performance
- **Faster completion** - ~20-25 minutes vs 40 minutes

## Reports Location

When complete:
- `/home/admincsp/frontend_integration/test_reports/test_summary_TIMESTAMP.json`
- `/home/admincsp/frontend_integration/test_reports/test_detailed_TIMESTAMP.json`
- `/home/admincsp/frontend_integration/test_reports/test_report_TIMESTAMP.md`
