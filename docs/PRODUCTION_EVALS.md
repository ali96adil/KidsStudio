# Production Intelligence — Evals v0 (opt-in, read-only)

The first implementation is deliberately isolated: `kidsstudio.production_evals` has no queue adapter, network requests, model calls, file writes, publishing permissions or automatic retry.

## Usage
```python
from kidsstudio.production_evals import evaluate_script, aggregate_runs

result = evaluate_script("Today we learn the color blue. Blue is a beautiful color.", language="en", required_terms=("blue",))
print(result.as_dict())
```

## Meaning of results
The checks are purely mechanical: text length, required phrases and nonempty lines. PASS does **not** mean educational accuracy, originality, age appropriateness, rights compliance, Arabic quality, English quality or safety approval. Independent specialist reviews and owner release authorization remain mandatory.

`aggregate_runs` computes pass rate and mean score from caller-supplied runs. It does not itself run or pay for AI generation. For nondeterministic prompt benchmarking, record model ID, prompt revision, provider, timestamp, seeds if available, latency, cost, artifact hashes and reviewer decisions in a private local audit record. Keep personal data and raw scripts out of the public repository.

## Rollout
1. Run unit tests on the feature branch.
2. Add synthetic failure fixtures and independently validated rubrics.
3. Pilot with an opt-in local worker adapter; no automatic dispatch or release.
4. Compare against baseline and require owner approval before enabling production use.
