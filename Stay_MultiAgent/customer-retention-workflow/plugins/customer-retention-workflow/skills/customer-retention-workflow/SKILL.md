# Skill: customer-retention-workflow

## Purpose
Predict customer **churn** with a base model and produce an auditable,
policy-compliant **retention decision** through a real multi-agent workflow.
The skill combines a predictive model, deterministic business code, four
specialist agents, typed contracts, a mandatory quality gate, bounded
iteration, structured traceability and human authority.

## When to use
Trigger this skill whenever the task is to decide *what to do with a customer
who might leave* a system, business, bank or subscription — i.e. churn /
abandono scoring plus a retention action.

## Architecture (real multi-agent, not a single LLM call)

```
Supervisor
   ├── (parallel) Behavior Analyst  -> BehaviorReport
   ├── (parallel) Value Analyst     -> ValueReport
   ├── Offer Specialist             -> OfferProposal
   ├── Reviewer (quality gate)      -> ReviewResult
   └── Consolidation                -> WorkflowDecision
```

* **Behavior Analyst** — runs the base churn model, maps probability to a risk
  band, extracts interpretable churn signals. Emits `BehaviorReport`.
* **Value Analyst** — computes CLV, expected value, cost of loss, importance
  tier and segment. Emits `ValueReport`.
* **Offer Specialist** — reads the retention policy, selects a compliant offer,
  computes cost, discount, expected benefit and ROI. Emits `OfferProposal`.
* **Reviewer** — performs no analysis; validates consistency, policy limits,
  completeness and hallucinations. Emits `ReviewResult` (approve / reject /
  needs_revision).
* **Supervisor** — coordinates, decides parallelism, delegates, requests the
  review, enforces Human-in-the-Loop approval and consolidates the final
  `WorkflowDecision`.

## Business rule
The final action combines **churn risk + customer value + offer cost**. When an
offer cost exceeds `policy.approval_cost_threshold`, the workflow **must** pause
and request human approval (Human-in-the-Loop). It cannot be skipped.

## Inputs
| Input | Required | Description |
|-------|----------|-------------|
| `csv` | yes | `challenges/session7/churn/customers.csv` |
| `policy` | yes | `challenges/session7/churn/politica_retencion.md` |
| `model` | no | `challenges/session7/model_base.py` (falls back to heuristic) |

## Output
A JSON report: one `WorkflowDecision` per customer plus the complete
`AgentTrace` list (timestamp, duration, model, tokens, warnings, errors,
status) for full traceability.

## How to run
```bash
python scripts/run_workflow.py \
  --csv challenges/session7/churn/customers.csv \
  --policy challenges/session7/churn/politica_retencion.md \
  --model challenges/session7/model_base.py \
  --out report.json
```
Add `--interactive` to approve expensive offers from the console.

## Guarantees
* Agents never share memory — they communicate only via typed artifacts.
* No free text between agents; every hop is a validated Pydantic model.
* The workflow cannot finish without a Reviewer decision (quality gate).
