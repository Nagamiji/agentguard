# Terraform (live)

The **live** `.tf` for AgentGuard/Keel. Design, rules, module tiers, and the change loop are governed by the OS repo:
- Rules & module tiers: `../../../keel/os/standards/infrastructure.md`
- Change process (plan → security → cost → **human approval** → apply): `../../../keel/loops/terraform-loop.md`
- Cloud map & dependency graph: `../../../keel/infrastructure/`
- Decision: `../../../keel/decisions/0007-infrastructure-as-code.md`

## Status
`DO-01` skeleton (providers/variables/main/outputs). **Real `[NOW]` modules land in `PLAT-01`**: `app-service`, `database` (Postgres+pgvector), `redis`, `storage` (R2), `edge` (Cloudflare). No k8s/VPC/sandbox until `[SEED+]`.

## Rules (never violate)
- No manual cloud console changes — ever.
- Every change rides the Terraform loop; `apply` is human-gated.
- Remote, locked state; secrets in a manager, never in `.tf`/state.
- `tfsec` + `checkov` + `tflint` gate every plan (wired in CI at `PLAT-02`).
