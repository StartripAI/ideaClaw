---
description: Run the IdeaClaw research pipeline to produce a real evidence-backed pack
---

# /run — IdeaClaw Research Pipeline

Execute the full IdeaClaw pipeline to turn an idea into a real, evidence-backed research pack.

## Usage

```
/run "Your research idea or question" [--profile PROFILE] [--depth standard|deep|quick]
```

Examples:
```
/run "Why is hybrid attention better than single-mechanism for long-context LLMs?"
/run "Compare PostgreSQL vs MongoDB for real-time analytics" --profile business.competitive_analysis
/run "Should our company adopt a 4-day work week?" --profile business.strategy_report --depth deep
```

## Steps

### 1. Read the IdeaClaw Skill
// turbo
Read `.agents/skills/ideaclaw/SKILL.md` to understand the full pipeline and quality standards.

### 2. Classify the Idea
Determine:
- **Domain**: cs_ml, business, medical, legal, etc.
- **Pack type**: decision, comparison, study, brief, proposal
- **Profile**: auto-detect or use user's `--profile` parameter

Load the profile to get quality criteria:
```python
cd /Users/star/ideaclaw/ideaClaw
source .venv/bin/activate
python3 -c "
from ideaclaw.quality.loader import auto_detect_profile, load_profile
profile_id = auto_detect_profile('USER_IDEA_HERE')
print(f'Profile: {profile_id}')
profile = load_profile(profile_id)
print(f'Target: {profile.target_score}')
print(f'Criteria: {[c.name for c in profile.criteria]}')
print(f'Sections: {profile.style.required_sections}')
"
```

### 3. Decompose into Sub-Questions
Use the Decomposer or do it manually — break the idea into 6-8 MECE sub-questions:
```python
python3 -c "
from ideaclaw.reasoning.decompose import Decomposer
d = Decomposer()
result = d.decompose('USER_IDEA_HERE', domain='DOMAIN', max_questions=8)
for i, q in enumerate(result.sub_questions, 1):
    print(f'Q{i}. [{q.priority}] {q.text}')
print(f'MECE: {result.is_mece}, Coverage: {result.coverage_score:.0%}')
"
```

### 4. Search for Real Sources
Use `search_web` to find 5-10 real sources. For each source:
1. Search with specific academic queries
2. Read the URL content with `read_url_content`
3. Extract key claims, data points, statistics
4. Record the URL for citation

**CRITICAL**: Use REAL sources only. Never fabricate URLs, DOIs, or author names.

### 5. Write the Pack Draft
Based on the pack type and domain, write the full research document following the section guidance from `ideaclaw/prompts/generation.py`. Every claim must be tagged:
- ✅ EVIDENCED (with source URL)
- ⚠️ INFERRED (logically derived)
- 🚫 UNCERTAIN (needs verification)

### 6. Evaluate the Draft
Run the heuristic evaluator:
```python
python3 -c "
from ideaclaw.orchestrator.evaluator import UnifiedEvaluator
from ideaclaw.orchestrator.loop import load_profile
from pathlib import Path

evaluator = UnifiedEvaluator()
profile = load_profile(Path('ideaclaw/orchestrator/profiles/PROFILE.yaml'))
draft = open('/tmp/draft.md').read()
sources = ['source1', 'source2', ...]  # list of source identifiers
scores = evaluator.evaluate(profile, draft, sources, calibrate=True)
meta = evaluator.meta_score(scores, profile)
print(f'Composite: {meta[\"composite\"]:.1%}')
for dim, val in sorted(scores.items(), key=lambda x: -x[1]):
    print(f'  {dim}: {val:.1%}')
if meta['weak_dims']:
    print(f'Weak: {meta[\"weak_dims\"]}')
"
```

### 7. Iterate if Needed
If composite score < target or weak dimensions exist:
- Improve the draft targeting weak dimensions
- Add more evidence for unsupported claims
- Deepen analysis in thin sections
- Re-evaluate after changes

### 8. Save the Pack
Save the final pack.md to the project's artifacts directory:
```
artifacts/ic-YYYYMMDD-HHMMSS-HASH/
  pack.md          ← The main deliverable
  manifest.json    ← Run metadata
  sources.json     ← All sources with URLs
```

### 9. Store in Memory
```python
python3 -c "
from ideaclaw.knowledge.memory import Memory, MemoryItem
from pathlib import Path
mem = Memory(memory_dir=Path('output/memory'))
item = MemoryItem(
    id='RUN_ID', idea='IDEA', scenario_id='PROFILE_ID',
    category='DOMAIN',
    insights=['insight1', 'insight2', 'insight3'],
    pitfalls=['pitfall1'],
    best_practices=['practice1'],
    final_score=SCORE, iteration_count=N,
)
mem._memories.append(item)
mem._save()
print(f'Stored. Memory count: {len(mem._memories)}')
"
```

## Quality Checklist (before completing)

- [ ] Every factual claim has a real source URL
- [ ] No placeholder text ("Option A", "Finding 1", "TBD")
- [ ] Real company/model/paper names used (not generic)
- [ ] Data tables have real numbers (not made up)
- [ ] Sources section has working URLs
- [ ] Pack type matches the user's intent
- [ ] All required sections for the domain are present
