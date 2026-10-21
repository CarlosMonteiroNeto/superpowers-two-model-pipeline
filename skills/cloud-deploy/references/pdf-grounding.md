# Cloud Deploy — PDF Grounding (Nuvem U1-U4 merged, deduplicated)

## 1. Cloud Concepts

- Virtualization: abstraction of physical hardware into isolated virtual machines,
  enabling multi-tenancy and efficient pooling of compute, memory, and storage.
- Scaling:
  - Vertical scaling (scale up): increase CPU/RAM of a single node; simple but
    bounded by hardware limits and single point of failure.
  - Horizontal scaling (scale out): add more nodes behind a load balancer;
    preferred for elasticity and fault tolerance.
- Elasticity: automatic expansion and contraction of capacity in response to load,
  distinct from static scalability planning.
- On-demand self-service: provision resources via API/portal without provider
  interaction; enables pay-per-use metering.
- Service model triad:
  - IaaS = maximum control (VMs, networks, storage); consumer manages OS and up.
  - PaaS = application focus (runtime, build, deploy, scale, patch handled by
    provider); typical pipeline: dev -> deploy -> scale -> run -> monitor -> patch.
  - SaaS = ready-to-use application; consumer configures only usage.
- Shared-responsibility boundary: provider secures the cloud (facilities,
  hypervisor, physical network); consumer secures what is in the cloud
  (data, identities, access policy, workload configuration).
- Security baseline: IAM (least-privilege roles, federation), encryption at rest
  and in transit, certificate management, network segmentation, audit logging.
- SLA and DR: contractual availability targets drive redundancy design
  (multi-AZ, geo-replication, backup/restore, failover runbooks).
- Pay-per-use: metered billing per second/request/GB; requires cost monitoring,
  tagging, budgets, and alerts to avoid runaway consumption.

## 2. Cloud Architecture

- Datacenter building blocks: regions, availability zones, edge locations;
  isolation plus low-latency interconnects.
- Network: VPC/VNet, subnets, VPN/dedicated interconnect, load balancer (L4/L7)
  distributing traffic across healthy targets with health checks.
- Orchestration: Kubernetes schedules containers, handles rolling updates,
  self-healing, service discovery, horizontal pod autoscaling.
- Storage classes:
  - Block (e.g., EBS-class): persistent volumes attached to a single VM/node.
  - Object (e.g., S3-class): highly durable, replicated blob store for static
    assets, backups, and data lakes.
  - Managed relational (e.g., RDS-class): automated patching, backup, and
    multi-AZ failover for relational workloads.
  - Ephemeral vs persistent: instance-local disks are lost on stop/terminate;
    persistent volumes and object stores survive lifecycle events.
- Deployment models: public (shared provider), private (single tenant),
  hybrid (on-premises plus public cloud with consistent networking/identity).
- Application style:
  - Monolith: single deployable unit; simple start, harder independent scaling.
  - Microservices: independently deployable services with contracts;
    enables team autonomy and selective scaling at the cost of operational complexity.
- Resilient design: redundancy across zones, isolation (blast-radius limits),
  continuous monitoring, automated recovery (health checks plus replacement),
  elasticity under load, and tested DR procedures.

## 3. Provider Triad Table

| Capability | AWS | Azure | GCP | IBM Cloud |
|---|---|---|---|---|
| Virtual machines | EC2 | Virtual Machines | Compute Engine | Virtual Servers |
| Object storage | S3 | Blob Storage | Cloud Storage | Cloud Object Storage |
| Serverless functions | Lambda | Functions | Cloud Functions | Code Engine Functions |

- Ephemeral vs persistent: all four providers pair ephemeral execution
  (functions, spot/preemptible VMs) with persistent options (block volumes,
  object storage, managed databases).
- Pricing models: on-demand (flexible, highest unit cost), reserved/savings
  plans (commitment discount for steady load), spot/preemptible (spare capacity
  at deep discount, revocable).
- Multiregion replication: each provider offers cross-region object replication,
  multi-AZ database standby, and global load balancing for DR and latency goals.
- IaC rule: map the VM + object storage + serverless triad to the target
  provider first, then generate Terraform/CLI from that mapping table.
