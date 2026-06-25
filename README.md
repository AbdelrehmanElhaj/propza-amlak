# Propza — Saudi Property Management System

A Saudi-first property management platform built on **Odoo 17**, covering the full real estate lifecycle: properties, tenancies, rent collection, CRM leads & reservations, maintenance, broker commissions, AI property matching, and deep integration with the **Ejar ECRS** platform — all purpose-built for the Saudi market.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Module Reference](#module-reference)
- [Infrastructure](#infrastructure)
- [Quick Start](#quick-start)
- [Demo Database](#demo-database)
- [Scripts Reference](#scripts-reference)
- [Configuration](#configuration)
- [Ejar ECRS Integration](#ejar-ecrs-integration)
- [Messaging Gateway](#messaging-gateway)
- [Roles & Permissions](#roles--permissions)
- [Saudi Compliance](#saudi-compliance)
- [Development Guide](#development-guide)

---

## Overview

Propza replaces generic property management add-ons with a system purpose-built for the Saudi rental market.

- **Arabic-first** — all UI labels, templates, and data in Arabic; locale `ar_001`, timezone `Asia/Riyadh`, currency SAR
- **Saudi regulations built in** — Riyadh rent freeze (2025–2030), Ejar ECRS contract registration, NID/Iqama validation, IBAN in SA format, VAT
- **Async Ejar integration** — non-blocking contract submission via OCA `queue_job`; webhook callbacks with HMAC-SHA256 validation; circuit breaker per company
- **Multi-provider messaging** — WhatsApp + SMS notifications via **Unifonic** or **UltraMsg**, switchable from Settings with no code changes
- **Role-aware** — 7 RBAC groups with ORM-level record rules; API access also restricted
- **AI Property Match** — scoring engine in `sa_crm_ai_match` ranks properties against lead preferences (type, region, budget, area, rooms, furnishing) and presents the top 8 matches in one click
- **No vendor lock-in** — thin `sa_property_base` core extended cleanly by all other modules

### Main Menu

| # | App | Arabic | Notes |
|---|-----|--------|-------|
| 1 | لوحة التحكم | Dashboard | Standalone KPI app |
| 2 | النظام الأساسي | Core System | Properties, owners, tenants, brokers, inspections |
| 3 | إدارة علاقات العملاء | CRM | Leads, showings, reservations, deals — agents & managers only |
| 4 | إدارة عقود الإيجار | Rental Contracts | Contracts, payments (all + overdue), commissions, SADAD invoices |
| 5 | إدارة الصيانة | Maintenance | Requests, work orders, periodic contracts, technicians |
| 6 | منصة إيجار | Ejar Platform | ECRS contracts, brokerage profiles, sync logs |
| 7 | المحاسبة المالية | Financial Accounting | Odoo built-in accounting — customers, vendors, journals, reports |
| 8 | حسابي | My Account | User profile, verifications, documents |

Owners, tenants, and brokers are direct children of **النظام الأساسي** (no intermediate "Parties" group). Rent payments live under **إدارة عقود الإيجار** alongside commissions and SADAD invoices.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  sa_dashboard   sa_portal   sa_mobile_tech   sa_notifications    │  ← Presentation
├──────────────────────────────────────────────────────────────────┤
│  sa_crm  sa_crm_ai_match  sa_broker_commission  sa_sadad          │  ← CRM & Financial
├──────────────────────────────────────────────────────────────────┤
│                     sa_rental_cycle                              │  ← Rental workflow
├────────────────────┬─────────────────────────────────────────────┤
│     sa_property    │            sa_maintenance                   │  ← Domain models
├────────────────────┴─────────────────────────────────────────────┤
│          l10n_sa_ejar        sa_security    sa_user_profile      │  ← Localisation & RBAC
├──────────────────────────────────────────────────────────────────┤
│                     sa_property_base                             │  ← Foundation
├──────────────────────────────────────────────────────────────────┤
│          Odoo 17  (account, mail, portal, queue_job)             │  ← Core
└──────────────────────────────────────────────────────────────────┘
```

**Dependency graph:**
```
sa_property_base
├── l10n_sa_ejar          (+ queue_job)
│   └── sa_property
│       └── sa_rental_cycle
│           ├── sa_broker_commission
│           ├── sa_notifications
│           └── sa_sadad
├── sa_maintenance
│   └── sa_mobile_tech
├── sa_user_profile
├── sa_dashboard
└── sa_security
    ├── sa_crm
    │   └── sa_crm_ai_match
    └── sa_portal
```

> **Load order rule:** `sa_security` is the top-level orchestration module. Feature modules (`sa_maintenance`, `sa_property_base`, etc.) must NOT depend on `sa_security` — doing so creates a circular dependency. PMS group ACL and record rules for those modules are defined inside `sa_security` instead.

---

## Module Reference

### `sa_property_base` — Foundation

Minimal Saudi-shaped core. Defines the two central models and the root menu entry.

| Model | Purpose |
|-------|---------|
| `property.property` | Physical real estate unit — address, type, owner, area, deed |
| `property.tenancy` | Rental contract linking property, tenant, and payment schedule |
| `sa.property.inspection` | Move-in / move-out condition reports with room-by-room line items |

---

### `l10n_sa_ejar` — Ejar ECRS Integration

Full async integration with the Saudi Ejar platform (ECRS v4).

**Core models**

| Model | Purpose |
|-------|---------|
| `ejar.brokerage.profile` | Office identity registered with Ejar (CR, VAT, license, address) |
| `ejar.contract` | Ejar contract record with 9-state machine |
| `ejar.contract.party` | Lessors, tenants, and representatives per contract |
| `ejar.contract.unit` | Property units linked to each contract |
| `ejar.sync.log` | Immutable audit log for every outbound API call and inbound webhook |

**Ejar contract states**
```
draft → building → ready → submitting → submitted → approved
                                      ↘ rejected
                                               ↘ expired / cancelled
```

**Async processing via `queue_job`**
- Three dedicated queue channels: `root.ejar.contracts`, `root.ejar.polling`, `root.ejar.documents`
- Per-job retry with exponential back-off (up to 20 retries for polling)
- Dead-letter handling: on permanent failure, contract resets to `ready` + Odoo activity created

**Webhook support**
- Endpoint: `POST /ejar/webhook`
- HMAC-SHA256 signature validation
- Replay attack prevention (±300 s timestamp window)
- Idempotent processing via `idempotency_key`
- Events: `contract.approved`, `contract.rejected`, `acknowledgement.completed`, `document.verification`, `status.update`

**Saudi compliance fields on `property.property` and `property.tenancy`**
- `deed_number` — رقم الصك
- `national_address_code` — رقم العنوان الوطني
- `sa_region_id` → `sa.region` (14 official Saudi regions)
- `sa_city_id` → `sa.city`
- `tenant_id_type` / `tenant_national_id` — NID, Iqama, GCC ID
- `ejar_payment_schedule` — monthly / quarterly / biannual / annual

---

### `sa_property` — Property & Tenancy Views

Extends base models with full Saudi-specific views.

**Property subtypes:** `villa` · `apartment` · `floor` · `annex` · `land` · `shop` · `office` · `warehouse`

---

### `sa_rental_cycle` — Complete Rental Workflow

End-to-end rental operations: payment schedules, wizards, owner dashboard, compliance reports.

**Payment statuses:** `draft` · `pending` · `paid` · `overdue` · `partial`

**Wizards:** payment recording · tenancy termination · renewal (with Riyadh rent-freeze guard)

**Scheduled job:** `sa_rental_cron` — daily flip of `pending` → `overdue`

---

### `sa_crm` — CRM & Deal Pipeline

Customer relationship management module covering the full pre-tenancy sales cycle.

**Models**

| Model | Purpose |
|-------|---------|
| `sa.crm.lead` | Lead / opportunity / deal — tracks the full sales lifecycle |
| `sa.crm.reservation` | Property reservation linked to a lead |
| `sa.crm.showing` | Field showing (جولة ميدانية) scheduled for a lead |
| `sa.crm.stage` | Configurable kanban pipeline stages |

### `sa_crm_ai_match` — AI Property Match for CRM

Adds intelligent property recommendation directly to the CRM lead form.

- Extends `sa.crm.lead` with `recommended_property_ids`, `recommended_count`, and `recommendation_note`
- Uses a scoring heuristic across property type, preferred region, rooms, bathrooms, area, budget, furnishing, and special features
- Selects the top 8 matching properties and opens them in a tree/form view
- Provides an Arabic action button for CRM agents to generate recommendations immediately

**Lead lifecycle (enforced by button visibility)**

```
طلب (lead)
  → تأهيل كفرصة
فرصة (opportunity)
  → احجز العقار          (opens reservation form — property required)
حجز مسودة (draft reservation)
  → تأكيد الحجز          (activates reservation; checks for conflicts)
حجز مؤكد (active reservation)
  → تحويل إلى صفقة       (converts reservation; marks lead as won)
صفقة (deal / won)
  → إنشاء عقد إيجار      (creates property.tenancy + ejar.contract in one step)
```

**Key rules:**
- "تحويل إلى صفقة" is hidden until a confirmed (active) reservation exists
- Reservations conflict-check: one active reservation per property at a time
- Expired reservations are auto-cancelled by a daily cron job
- Creating an Ejar contract also creates a linked `property.tenancy` (draft), pre-filled from lead data

**Linking to the rental lifecycle**

When "إنشاء عقد إيجار" is clicked on a won deal:
1. A `property.tenancy` record is created in `draft` state
2. An `ejar.contract` is created with `tenancy_id` pointing to that tenancy
3. `tenancy.ejar_contract_id` is set (bidirectional link)
4. Both are stored on the lead (`lead.tenancy_id`, `lead.contract_id`)

Activating the tenancy (`تشغيل`) automatically sets `property.state = on_rent` and assigns `tenant_partner_id`.

**Access:** restricted to `group_pms_agent` and `group_pms_manager` — owners, technicians, and portal users have no access.

---

### `sa_maintenance` — Maintenance Management

| Model | Purpose |
|-------|---------|
| `sa.maintenance.request` | Reported issue (category, priority, property, tenant) |
| `sa.maintenance.work_order` | Work assigned to a specific technician |
| `sa.maintenance.contract` | Periodic maintenance agreement |
| `sa.maintenance.skill` | Technician speciality taxonomy |

**Categories:** `plumbing` · `electrical` · `ac` · `painting` · `carpentry` · `cleaning` · `pest` · `appliance` · `other`

**Request state machine:** `new → approved → scheduled → in_progress → done`

**Cost breakdown:** materials + labour + transport → computed total; cost bearer: owner / tenant / split

**Periodic contracts:** auto-generate maintenance requests via daily cron (`cron_generate_due_services`)

**Sequences:** `MNT/YYYY/NNNNN` for requests · `WO/YYYY/NNNNN` for work orders

> `sa_maintenance` does NOT depend on `sa_security` (would be circular). PMS group ACL and record rules for maintenance models are defined in `sa_security`.

---

### `sa_user_profile` — Tenant Profile & Identity

Extended profile fields on `res.partner` for tenants and owners.

- Gender, date of birth, bio
- Saudi national address fields (region, district, building number, postal code)
- `sa.user.verification` — KYC workflow: `draft → submitted → verified / rejected`
- `sa.user.document` — document vault (national ID, lease contract, salary letter, etc.)

---

### `sa_broker_commission` — Broker Commissions

Links broker partners to tenancy contracts and manages commission payment flow.

**Commission basis:** `percentage` (% of annual rent) or `fixed` (SAR amount)

**Payment patterns:** `on_signup` · `monthly` · `split`

**Financial flow:** Confirm → payment schedule → create vendor bill → post → register payment

---

### `sa_notifications` — Multi-Provider Messaging & Alerts

Automated Arabic notifications across email, WhatsApp, and SMS. Supports **multiple messaging providers** switchable from Settings without code changes.

**7 automated notification triggers:**

| Trigger | Recipients | Channel |
|---------|-----------|---------|
| Rent payment reminder (N days before due) | Tenant | Email + WhatsApp/SMS |
| Overdue payment alert (days 1, 7, 14, 30) | Tenant | Email + WhatsApp/SMS |
| Contract expiry warning (N days before end) | Tenant + Owner | Email + WhatsApp/SMS |
| Lease renewal proposed | Owner | Email + WhatsApp/SMS |
| Maintenance request received | Tenant | Email + WhatsApp/SMS |
| Maintenance work order assigned | Technician | Email + WhatsApp/SMS |
| Maintenance completed | Tenant | Email + WhatsApp/SMS |

**3 daily cron jobs:** payment reminders · overdue alerts · contract expiry checks

**Messaging providers:**

| Provider | WhatsApp | SMS | Configuration |
|----------|----------|-----|---------------|
| **Unifonic** | ✅ | ✅ (fallback) | App SID + Bearer Token + Sender ID |
| **UltraMsg** | ✅ | ❌ (WA only) | Instance ID + Token |
| **Disabled** | — | — | No credentials needed |

**Key models:**
- `sa.messaging.gateway` — central provider router; reads `messaging_provider` setting and dispatches to the correct service; contains shared phone normalization for Saudi numbers (`9665XXXXXXXX`)
- `sa.unifonic.service` — Unifonic REST/CPaaS API integration (inherits gateway)
- `sa.ultramsg.service` — UltraMsg REST API integration (inherits gateway)
- `sa.notifications.helper` — cron and trigger helper; delegates all WhatsApp/SMS calls through the gateway

**Phone normalization** — `_normalize_phone()` converts any Saudi format to E.164:
```
+966-5-XXXX-XXXX  →  9665XXXXXXXX
05XXXXXXXX        →  9665XXXXXXXX
9665XXXXXXXX      →  9665XXXXXXXX  (no-op)
```

**Configuring the provider** — Settings → إعدادات تنبيهات PMS → بوابة WhatsApp والرسائل النصية

---

### `sa_sadad` — SADAD Payment Simulator

Simulates the Saudi SADAD payment network for development and demo. Webhook endpoint auto-marks `sa.rent.payment` as paid on callback.

> **Production note:** Real SADAD integration requires an agreement with SAMA and a bank partnership.

---

### `sa_dashboard` — KPI Dashboard

Single-page dashboard: KPI cards (properties, active tenancies, monthly revenue, arrears), 12-month revenue trend, occupancy donut, maintenance cost chart, overdue tenant list. All data respects record rules.

---

### `sa_portal` — Tenant Self-Service Portal

| URL | Content |
|-----|---------|
| `/my/contracts` | Lease agreement list + property details |
| `/my/payments` | Payment schedule and account statement |
| `/my/maintenance` | Maintenance requests + new request form |
| `/my/inspections` | Inspection reports (read-only) |

---

### `sa_mobile_tech` — Field Technician Mobile UI

Mobile-optimised kanban ("My Work Today") with swipe-friendly work orders, before/after photo capture, and large action buttons. Restricted to `group_pms_technician`.

---

### `sa_security` — RBAC & Record Rules

Central security module. Seven roles enforced at ORM level.

| Group | Arabic | Scope |
|-------|--------|-------|
| `group_pms_admin` | مدير النظام | Full access + settings |
| `group_pms_manager` | مدير العقارات | All operational data |
| `group_pms_accountant` | المحاسب | Financial records |
| `group_pms_agent` | موظف خدمة عملاء | CRM + read + create |
| `group_pms_owner` | مالك عقار | Own portfolio only |
| `group_pms_technician` | فني صيانة | Assigned work orders only |
| `group_pms_tenant_portal` | مستأجر (بوابة) | Portal `/my/…` own records only |

This module also owns ACL entries and record rules for models defined in `sa_maintenance` and other feature modules that load before it.

---

## Infrastructure

| Component | Image | Port |
|-----------|-------|------|
| PostgreSQL 15 | `postgres:15` | 5432 (internal) |
| Odoo 17 | `odoo:17.0` | 8069 (internal only) |
| Nginx | `nginx:alpine` | 80 → 443 (HTTPS) |

### Docker volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `odoo-db-data` | PostgreSQL data dir | Database persistence |
| `odoo-web-data` | `/var/lib/odoo` | Filestore (attachments, sessions) |
| `./addons` | `/mnt/extra-addons` | Custom modules |
| `./config` | `/etc/odoo` | `odoo.conf` |
| `./config/nginx.conf` | `/etc/nginx/conf.d/default.conf` | Nginx reverse proxy config |
| `./config/certs` | `/etc/nginx/certs` | TLS certificate and key |

### SSL / HTTPS

Nginx sits in front of Odoo and handles all TLS termination.

- **HTTP (port 80)** → 301 redirect to HTTPS
- **HTTPS (port 443)** → proxy to Odoo on port 8069 (internal)
- Odoo's direct port 8069 is no longer exposed to the host

`start.sh` auto-generates a **self-signed certificate** on first run (valid 10 years, SAN includes the server's public IP). Browsers will show a one-time "Not secure" warning — click **Advanced → Proceed**.

```bash
# Certificate lives at:
config/certs/nginx.crt
config/certs/nginx.key
```

To replace with a real certificate (e.g. from Let's Encrypt or a CA):
```bash
# Drop in your cert files — nginx picks them up on restart
cp fullchain.pem config/certs/nginx.crt
cp privkey.pem   config/certs/nginx.key
docker compose restart nginx
```

### `odoo.conf` key settings

```ini
admin_passwd = admin@123
db_host = db
db_port = 5432
db_user = odoo17
db_password = odoo17
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
log_level = info
workers = 0           # single-process; increase for production
max_cron_threads = 1
list_db = False       # hides database manager from login page
proxy_mode = True     # required when behind nginx — trusts X-Forwarded-* headers

[queue_job]
channels = root:4,root.ejar:8,root.ejar.contracts:2,root.ejar.polling:10,root.ejar.documents:3
```

---

## Quick Start

### Prerequisites

- Docker ≥ 24
- Git
- SSH access to the server (or run locally)

### 1. Install Docker (Ubuntu)

```bash
bash install-docker.sh
```

### 2. Clone and start containers

```bash
git clone git@github.com:AbdelrehmanElhaj/propza-amlak.git
cd propza-amlak
bash start.sh
```

### 3. Create the database and seed demo data

```bash
# Full setup with demo data — recommended for first run
bash setup-demo.sh

# Custom database name
bash setup-demo.sh demodb

# Full teardown and rebuild from scratch
bash setup-demo.sh -f demodb

# Install modules only, skip demo data
bash setup-demo.sh --no-demo demodb
```

### 4. Open in browser

```
https://<server-ip>
Database: demodb
Admin:    admin@propza.sa  /  admin
Demo:     (any demo email)  /  demo
```

> The browser will warn about the self-signed certificate. Click **Advanced → Proceed** to continue.

---

## Demo Database

Seeded by `setup-demo.sh`. All content in Arabic, covering realistic Saudi scenarios across Riyadh, Jeddah, and Dammam:

| Category | Count | Details |
|----------|-------|---------|
| Brokerage Profile | 1 | Propza, Riyadh, UAT credentials |
| Owners (ملاك) | 12 | 6 individuals + 6 companies |
| Tenants (مستأجرون) | 28 | 25 individuals + 3 companies; mix of NID, Iqama |
| Brokers (وسطاء) | 6 | 2 companies + 4 individuals |
| Technicians (فنيون) | 10 | Companies + individuals; plumbing, electrical, HVAC, painting, carpentry |
| Properties (عقارات) | 32 | Villas, apartments, offices, warehouses, shops, penthouse |
| Tenancies (عقود إيجار) | 24 | Running · confirmed · draft · expired; monthly/quarterly/semi-annual/annual schedules |
| Rent Payments (دفعات) | 76 | Paid · pending · overdue; SAR deposits included |
| Inspections (معاينات) | 11 | Signed · complete · draft |
| Maintenance Requests | 20 | All states: new · approved · scheduled · in_progress · done |
| Work Orders | 10 | Scheduled · in_progress · done |
| Maintenance Contracts | 4 | HVAC, electrical, plumbing, full-service (all active) |
| Broker Commissions | 9 | Confirmed; percentage and fixed basis |
| **Ejar ECRS Contracts** | **10** | All states covered: draft · building · ready · submitted · approved · rejected |
| Contract Parties | 18 | Lessors + tenants; synced · pending · failed |
| Contract Units | 9 | Villa · apartment · office; various furnishing states |
| Sync Logs | 10 | Outbound + inbound; success · error |
| ID Verifications | 19 | Verified · submitted · draft · rejected |
| User Documents | 24 | National IDs, lease contracts, salary letters, CR certificates |
| CRM Leads | 20 | Pipeline: new → contact → showing → negotiation → won/lost |
| CRM Showings | 16 | Field tours linked to leads |
| CRM Reservations | 6 | Draft · active · expired · converted |
| System Users | 23 | Internal + portal — password: `demo` |

**Login credentials**

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@propza.sa` | `admin` |
| Property Manager | `manager@propza-demo.sa` | `demo` |
| Accountant | `accountant@propza-demo.sa` | `demo` |
| Agent | `agent@propza-demo.sa` | `demo` |
| Owner (individual) | `m.qahtani@propza-demo.sa` | `demo` |
| Owner (company) | `info@wahaa-dev.sa` | `demo` |
| Tenant (individual) | `k.rashidi@propza-demo.sa` | `demo` |
| Tenant (company) | `info@bustan-rental.sa` | `demo` |
| Broker | `info@wafir-broker.sa` | `demo` |
| Technician | `info@hassan-plumbing.sa` | `demo` |

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `start.sh` | Start containers; auto-generates SSL cert on first run |
| `stop.sh` | Stop containers |
| `logs.sh` | Tail Odoo container logs |
| `install-docker.sh` | Install Docker + Compose on Ubuntu |
| `setup-demo.sh` | All-in-one: create DB, install modules, configure company, seed demo data |

### `setup-demo.sh` flags

| Flag | Effect |
|------|--------|
| *(none)* | Create DB + install all modules + configure + seed demo data (default DB: `demodb`) |
| `-f` / `--fresh` | Drop existing DB first, then full setup |
| `-u` / `--upgrade` | Upgrade modules on existing DB and re-seed data |
| `--no-demo` | Create DB + install modules only, skip demo data |

```bash
# Examples
bash setup-demo.sh                         # full setup with demo data (DB: demodb)
bash setup-demo.sh mydb                    # custom database name
bash setup-demo.sh -f demodb               # drop and rebuild from scratch
bash setup-demo.sh -u demodb               # upgrade modules + re-seed
bash setup-demo.sh --no-demo demodb        # install only, no demo data
ODOO_DB=demodb bash setup-demo.sh          # database name via env var
```

---

## Configuration

### Upgrading a module after code changes

```bash
bash setup-demo.sh -u demodb
# or upgrade a specific module directly:
docker exec odoo17 odoo -d demodb -u sa_notifications --stop-after-init
docker restart odoo17
```

### Running the Odoo shell

```bash
docker exec -it odoo17 odoo shell -d demodb
```

### Watching logs

```bash
bash logs.sh
# or:
docker logs -f odoo17
```

### Clearing stale asset bundles

```bash
docker exec odoo17-db psql -U odoo17 -d demodb \
  -c "DELETE FROM ir_attachment WHERE res_model='ir.ui.view' AND name LIKE '%.assets%';"
docker restart odoo17
```

### Production workers

```ini
# config/odoo.conf
workers = 4
max_cron_threads = 2
```

Add a reverse proxy (nginx / Caddy) in front of port 8069.

---

## Ejar ECRS Integration

### Authentication

`Basic Base64(api_key:api_secret)` header. Credentials stored as Odoo system parameters:

```
ejar.api.key.company_{id}
ejar.api.secret.company_{id}
ejar.api.environment.company_{id}   # uat | production
```

Configure at: **Settings → Technical → Parameters → System Parameters** (search: `ejar.api`)

### Contract workflow

1. Create `ejar.contract` (automatically via CRM deal, or manually)
2. **بدء الإعداد** → add parties (lessor + tenant) and units
3. **تأكيد الاكتمال** → moves to `ready`
4. **إرسال إلى إيجار** → enqueues `queue_job`; UI returns immediately
5. Background worker submits to ECRS; contract transitions to `submitted`
6. Ejar responds via webhook → contract moves to `approved` or `rejected`

### CRM → Ejar shortcut

When a CRM deal's "إنشاء عقد إيجار" button is clicked, the system automatically:
- Creates `property.tenancy` (draft) pre-filled from lead data
- Creates `ejar.contract` linked via `tenancy_id`
- Sets `tenancy.ejar_contract_id` (bidirectional)
- Opens the Ejar contract form for review before submission

### Webhook setup

```bash
# 1. Generate a secret
openssl rand -hex 32

# 2. Store in System Parameters
ejar.webhook.secret.company_{id}  →  <generated secret>

# 3. Configure Ejar to POST callbacks to:
https://your-odoo.com/ejar/webhook
```

### Brokerage profile constraints

| Field | Constraint |
|-------|-----------|
| `cr_number` / `unified_number` | Exactly 10 digits |
| `vat_number` | Exactly 15 digits |
| `national_address_code` | 4 letters + 4 digits (e.g., `RIYD0001`) |
| `brokerage_fee` | ≤ 2.5% of annual rent |

---

## Messaging Gateway

The `sa_notifications` module provides a **multi-provider messaging gateway** (`sa.messaging.gateway`) that routes WhatsApp and SMS notifications to the configured provider without touching trigger code.

### Provider selection

Configure at: **Settings → إعدادات تنبيهات PMS → بوابة WhatsApp والرسائل النصية**

| Provider | `messaging_provider` value | WhatsApp | SMS |
|----------|---------------------------|----------|-----|
| Unifonic | `unifonic` | ✅ | ✅ (fallback) |
| UltraMsg | `ultramsg` | ✅ | ❌ |
| Disabled | `disabled` | — | — |

### Unifonic setup

```
Settings → PMS Notifications → Provider: Unifonic

Required credentials:
  sa_notifications.unifonic_app_sid          ← SMS App SID
  sa_notifications.unifonic_sender_id        ← SMS Sender ID (e.g. "Propza")
  sa_notifications.unifonic_token            ← WhatsApp Bearer Token
  sa_notifications.unifonic_whatsapp_sender  ← WhatsApp Business Number (9665XXXXXXXX)
```

API endpoints used:
```
SMS:       POST https://api.unifonic.com/rest/Messages/Send
WhatsApp:  POST https://messaging.unifonic.com/v2/messages
```

### UltraMsg setup

```
Settings → PMS Notifications → Provider: UltraMsg

Required credentials:
  sa_notifications.ultramsg_instance_id  ← e.g. "instance123456"
  sa_notifications.ultramsg_token        ← API Token from ultramsg.com dashboard
```

API endpoint used:
```
POST https://api.ultramsg.com/{instance_id}/messages/chat
Content-Type: application/x-www-form-urlencoded
Body: token={token}&to=+9665XXXXXXXX&body={message}
```

### Gateway routing logic

```python
# sa.messaging.gateway._get_provider()
provider = cfg('messaging_provider')   # 'unifonic' | 'ultramsg' | 'disabled'
# Backward compat: if unset, falls back to legacy unifonic_enabled flag

# sa.messaging.gateway._send_whatsapp_sms()
if provider == 'unifonic':
    try WA → fallback to SMS
elif provider == 'ultramsg':
    WA only (no SMS)
else:
    debug log, return False
```

### Backward compatibility

Existing installations that use `unifonic_enabled=True` continue to work without any change — the gateway detects the legacy flag and routes to Unifonic automatically. No database migration needed.

---

## Roles & Permissions

| Role | Backend | Properties | Tenancies | Payments | CRM | Maintenance | Ejar | Settings |
|------|---------|------------|-----------|----------|-----|-------------|------|----------|
| Admin | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ |
| Manager | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ❌ |
| Accountant | ✅ | Read | ✅ All | ✅ All | ❌ UI | Read | Read | ❌ |
| Agent | ✅ | Read+Create | Read+Create | Read | ✅ Full | Read+Create | Read | ❌ |
| Owner | ✅ Own | Own only | Own only | Own only | ❌ | Own only | ❌ | ❌ |
| Technician | ✅ (maint.) | ❌ | ❌ | ❌ | ❌ | Assigned only | ❌ | ❌ |
| Tenant | Portal only | ❌ | Own only | Own only | ❌ | Own only | ❌ | ❌ |

Record rules are enforced at the ORM level — not just the UI — so API access is also restricted.

> **Accountant note:** The accountant has `base.group_user` internal access so can reach CRM records programmatically, but the CRM menu is hidden in the UI (`groups="sa_security.group_pms_agent"`).

---

## Saudi Compliance

### Riyadh Rent Freeze (2025–2030)

Royal decree prohibits rent increases on Riyadh properties until September 2030. Enforced as a `_constraint` on `property.tenancy`:

```python
if property.sa_region_id.code == 'RUH' and renewal_rent_increase_pct > 0:
    raise UserError('لا يُسمح بزيادة الإيجار في عقارات الرياض حتى سبتمبر 2030')
```

The renewal wizard also shows a yellow warning banner for Riyadh properties.

### National IDs & IBAN

All partner and property forms enforce:
- رقم الهوية الوطنية or رقم الإقامة with expiry date
- رقم العنوان الوطني (4-letter + 4-digit short address)
- IBAN starting with `SA` (24 characters)

### Ejar Brokerage Fee Cap

`ejar.contract` enforces `brokerage_fee ≤ 2.5%` of annual rent via `_check_brokerage_fee_cap`.

---

## Development Guide

### Repository structure

```
propza-amlak/
├── addons/
│   ├── sa_property_base/
│   ├── l10n_sa_ejar/
│   │   ├── models/
│   │   │   ├── ejar_contract.py
│   │   │   ├── ejar_contract_jobs.py    ← queue_job integration
│   │   │   ├── ejar_contract_party.py
│   │   │   ├── ejar_contract_unit.py
│   │   │   ├── ejar_sync_log.py
│   │   │   └── ejar_brokerage_profile.py
│   │   └── controllers/                 ← webhook endpoint
│   ├── sa_property/
│   ├── sa_rental_cycle/
│   ├── sa_crm/                          ← CRM: leads, reservations, showings, deals
│   ├── sa_crm_ai_match/                 ← AI property matching for CRM leads
│   ├── sa_maintenance/                  ← Maintenance: requests, work orders, contracts
│   ├── sa_mobile_tech/
│   ├── sa_broker_commission/
│   ├── sa_notifications/
│   │   └── models/
│   │       ├── messaging_gateway.py     ← multi-provider router (sa.messaging.gateway)
│   │       ├── unifonic_service.py      ← Unifonic SMS + WA (inherits gateway)
│   │       └── ultramsg_service.py      ← UltraMsg WA-only (inherits gateway)
│   ├── sa_sadad/
│   ├── sa_dashboard/
│   ├── sa_portal/
│   ├── sa_security/
│   ├── sa_user_profile/
│   └── queue_job/                       ← OCA: async job queue (Ejar integration)
├── config/odoo.conf
├── docker-compose.yml
├── docs/USER_MANUAL.md
├── setup-demo.sh                        ← all-in-one: install + configure + demo data
├── start.sh  stop.sh  logs.sh
└── install-docker.sh
```

### Adding a new messaging provider

1. Create `addons/sa_notifications/models/my_provider_service.py` — AbstractModel inheriting `sa.messaging.gateway`
2. Implement `_my_provider_send_whatsapp(phone, message)` (and optionally `_send_sms`)
3. Add a branch in `messaging_gateway._send_whatsapp_sms()` for the new provider name
4. Add credentials fields to `res_config_settings.py` and the settings view
5. Add `'my_provider'` to the `sa_messaging_provider` selection list
6. Import the new file in `models/__init__.py` after `messaging_gateway`

### XML load order rule

Inherited views that reference `inherit_id` from another file must load after that file. Wizards must load before any view that inherits from them.

```python
# Correct pattern in __manifest__.py
'data': [
    'security/ejar_security.xml',
    'security/ir.model.access.csv',
    'data/...',
    'views/base_views.xml',          # define base views first
    'wizard/wizard_views.xml',       # wizards before anything that inherits them
    'views/inherited_views.xml',     # inherits from both above
    'views/menu.xml',                # menus always last
],
```

### Module dependency rules

- `sa_security` depends on all feature modules → loads last among custom addons
- Feature modules (`sa_maintenance`, `sa_property_base`, etc.) must NOT list `sa_security` in `depends` — circular dependency silently breaks all module loading
- Modules that need PMS group restrictions in their menus must either: (a) depend on `sa_security` (like `sa_crm`), or (b) have their menu group overrides declared in `sa_security/data/menu_overrides.xml`
- Portal user `create()` methods that call `ir.sequence` must use `.sudo()` — portal users lack sequence read access

### Git workflow

```bash
git checkout -b feature/my-feature
# make changes
git add addons/sa_crm/
git commit -m "feat(sa_crm): description"
git push origin feature/my-feature
# PR → merge → pull on server → restart
```

### Server deployment

```bash
ssh proptech-amlak "cd ~/propza-amlak && git pull && bash setup-demo.sh -u demodb 2>&1"
```

**Server:** `13.50.5.37` — `ubuntu@proptech-amlak` (SSH alias)

---

**Built by Abdelrehman Elhaj**

| | |
|---|---|
| Email | a.elhaj@proptech.sa |
| LinkedIn | [abdelrehman-elhaj](https://www.linkedin.com/in/abdelrehman-elhaj-972a49257/) |

*Odoo 17 · PostgreSQL 15 · Docker · OCA queue_job · Unifonic · UltraMsg*
