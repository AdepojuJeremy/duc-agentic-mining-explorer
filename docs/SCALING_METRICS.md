# Scaling and Throughput Metrics

Each completed `duc-agentic mine` run enriches `runs/<run-id>/metrics.yaml` with a `derived_metrics` section. The raw counters remain unchanged; the derived section is calculated from those counters, `proposal_reviews.yaml`, the configured explorer concurrency, and optional human-review counts.

## Requested scaling metrics

| Metric | Definition |
|---|---|
| `average_explorer_calls_per_anchor` | Explorer model API requests / completed exploration rounds. One completed exploration round is treated as one anchor round. |
| `candidates_found_per_anchor` | Raw candidates recorded / completed exploration rounds. |
| `unique_candidates_per_anchor` | Unique retained candidates / completed exploration rounds. |
| `validator_promotion_rate` | Promoted candidates / completed candidate validations. |
| `grounding_pass_rate` | Final accepted, deduplicated routes / unique routes that received an automated proposal review. |
| `average_repair_attempts` | Repair attempts / unique automatically reviewed routes. |
| `usable_routes_produced_per_anchor` | Final accepted routes / completed exploration rounds. |
| `average_wall_clock_seconds_per_accepted_route` | Total run wall-clock seconds / final accepted routes. This is an effective throughput measure and therefore includes concurrency. |
| `concurrent_anchor_rounds` | Configured explorer concurrency for the run. |
| `api_requests_per_accepted_route` | Total OpenAI API requests across explorer, validator, generator and reviewer / final accepted routes. |
| `api_tokens_per_accepted_route` | Total input + output tokens across all roles / final accepted routes. |
| `human_acceptance_rate` | Human-accepted routes / human-reviewed routes, when human review counts have been supplied. Otherwise `null`. |

Additional fields include accepted routes/hour, input/output/cached tokens per accepted route, total API errors, unique reviewed-route count, and per-role requests/tokens per accepted route.

## Refresh a run's metrics

```bash
duc-agentic metrics config/makeup_1200.yaml --run-id makeup-1200
```

This recomputes `derived_metrics` from the run artifacts and writes it back into `metrics.yaml`.

## Add human acceptance counts

Human review is intentionally kept separate from automated grounding review. When counts become available:

```bash
duc-agentic record-human-review config/makeup_1200.yaml \
  --run-id makeup-1200 \
  --reviewed 100 \
  --accepted 82
```

This writes `runs/makeup-1200/human_review.yaml` and refreshes `metrics.yaml`. The command rejects impossible counts such as `accepted > reviewed`.

## Example derived section

```yaml
derived_metrics:
  average_explorer_calls_per_anchor: 4.12
  candidates_found_per_anchor: 1.84
  unique_candidates_per_anchor: 1.67
  validator_promotion_rate: 0.61
  grounding_pass_rate: 0.73
  average_repair_attempts: 0.28
  average_repair_attempts_per_accepted_route: 0.34
  usable_routes_produced_per_anchor: 0.82
  average_wall_clock_seconds_per_accepted_route: 31.4
  accepted_routes_per_hour: 114.65
  concurrent_anchor_rounds: 8
  unique_reviewed_routes: 412
  api_requests_per_accepted_route: 13.7
  api_input_tokens_per_accepted_route: 42120.5
  api_output_tokens_per_accepted_route: 6840.2
  api_tokens_per_accepted_route: 48960.7
  cached_input_tokens_per_accepted_route: 8030.1
  human_reviews_completed: 100
  human_reviews_accepted: 82
  human_acceptance_rate: 0.82
```

The example values are illustrative only.
