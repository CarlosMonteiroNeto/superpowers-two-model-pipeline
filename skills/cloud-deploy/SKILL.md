---
name: cloud-deploy
description: Use when choosing IaaS/PaaS/SaaS, mapping services across AWS/Azure/GCP, or planning resilient cloud deployment and IaC.
---

# Cloud Deploy

## When to Use This Skill
- IaaS=control / PaaS=focus on app / SaaS=ready app decision.
- Provider mapping (VM + object storage + serverless triad) for Terraform/CLI generation.
- Resilience: redundancy, isolation, monitoring, automated recovery, elasticity.
- Triad shorthand: EC2 + S3 + Lambda maps to Azure/GCP equivalents before IaC.

## Route elsewhere
- CI/CD pipeline authoring -> external ops-engineering-skills cicd-tooling (approval required).
- Cost deep-dive -> external cloud-platform-skills FinOps skill (approval required).

## Checklist (grounded: Nuvem U1-U4 merged)
1. Decide IaaS/PaaS/SaaS by control-vs-focus rule; note shared-responsibility boundary.
2. Map VM + object storage + serverless triad to target provider before writing IaC.
3. Require: IAM, encryption rest+transit, SLA/redundancy/LB/geo-replication/DR, pay-per-use monitoring.
4. Prefer PaaS pipeline dev->deploy->scale->run->monitor->patch for app focus.
5. Output: provider mapping table + deploy checklist for the brief.
