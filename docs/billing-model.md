# Billing & SaaS Limits Model

This document outlines the multi-tenant SaaS plan tiers, usage tracking limits, and future billing integrations.

---

## 1. Plan Tiers (Plans Table Schema)

We support three tier levels stored in the `plans` table:

| Plan | Scan Limit | Agent Limit | Features | Target |
| :--- | :--- | :--- | :--- | :--- |
| **`free`** | 10 | 1 | Basic prompt scans | Individual Developers / Sandboxes |
| **`pilot`** | 100 | 5 | Custom checks, advanced library scans | Early Adopters / Startups |
| **`enterprise`** | Unlimited (`-1`) | Unlimited (`-1`) | Custom rules, SSO, dedicated runners | Corporate Production Teams |

- **Limits Enforcement**: High-performance scans and agent registrations check against the organization's plan limits. If a threshold is exceeded, the server returns a `402 Payment Required` HTTP response.

---

## 2. Usage Tracking Events

All tenant activity is tracked in the `usage_events` table (protected by Row-Level Security):
- `scan_executed`: Logs the timestamp, agent, run decisions, and scenario pass/fail counts.
- `last_activity` checks and audit logs can be queried from the `usage_events` history.

---

## 3. Stripe & Metered Billing Roadmap

In future releases, the billing engine will support:
1. **Stripe Webhook Syncs**: Automatically updates an organization's `plan_id` in Postgres when a subscription event occurs.
2. **Metered Billing Reports**: Daily cron jobs aggregating the count of `scan_executed` events and pushing usage reports to the Stripe usage reporting endpoint.
3. **Usage Alerts**: Slack or email alerts when organizations approach 80% and 100% of their plan limits.
