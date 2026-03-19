---
description: Run quality benchmark on existing IdeaClaw packs
---

# /benchmark — Quality Benchmark

Evaluate the quality of existing pack.md files using IdeaClaw's evaluation system.

## Usage

```
/benchmark [--dir PATH] [--profile PROFILE]
```

## Steps

### 1. Find Pack Files
Locate pack.md files in the specified directory (default: `artifacts/`):
```bash
find artifacts/ -name "pack.md" -type f
```

### 2. Evaluate Each Pack
For each pack.md, run the evaluator:
```python
cd /Users/star/ideaclaw/ideaClaw && source .venv/bin/activate
python3 -c "
from ideaclaw.orchestrator.evaluator import UnifiedEvaluator
from ideaclaw.orchestrator.loop import load_profile
from pathlib import Path

evaluator = UnifiedEvaluator()
profile = load_profile(Path('ideaclaw/orchestrator/profiles/arxiv_preprint.yaml'))
draft = Path('PACK_PATH').read_text()
scores = evaluator.evaluate(profile, draft, [], calibrate=True)
meta = evaluator.meta_score(scores, profile)
print(f'Score: {meta[\"composite\"]:.1%}')
for d, v in sorted(scores.items(), key=lambda x: -x[1]):
    print(f'  {d}: {v:.1%}')
"
```

### 3. Generate Report
Create a comparison table of all evaluated packs with scores, weak dimensions, and pass/fail status.
