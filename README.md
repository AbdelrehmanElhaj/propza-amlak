# Propza — Saudi Property Management System

A Saudi-first property management platform built on **Odoo 17**, covering the full real estate lifecycle: properties, tenancies, rent collection, CRM leads & reservations, maintenance, broker commissions, and deep integration with the **Ejar ECRS** platform — all purpose-built for the Saudi market.

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
- [Roles & Permissions](#roles--permissions)
- [Saudi Compliance](#saudi-compliance)
- [Development Guide](#development-guide)

---

## Overview

Propza replaces generic property management add-ons with a system purpose-built for the Saudi rental market.

- **Arabic-first** — all UI labels, templates, and data in Arabic; locale `ar_001`, timezone `Asia/Riyadh`, currency SAR
- **Saudi regulations built in** — Riyadh rent freeze (2025–2030), Ejar ECRS contract registration, NID/Iqama validation, IBAN in SA format, VAT
- **Async Ejar integration** — non-blocking contract submission via OCA `queue_job`; webhook callbacks with HMAC-SHA256 validation; circuit breaker per company
- **Role-aware** — 7 RBAC groups with ORM-level record rules; API access also restricted
- **AI Property Match** — intelligent CRM lead recommendations based on preferred region, budget, type, area, rooms, and tenant preferences
- **No vendor lock-in** — thin `sa_property_base` core extended cleanly by all other modules

### Main Menu

| # | App | Arabic | Notes |
|---|-----|--------|-------|
| 1 | لوحة التحكم | Dashboard | Standalone KPI app |
| 2 | إدارة العقارات | Property Management | Properties, tenancies, payments, commissions, inspections |
| 3 | CRM العملاء | CRM | Leads, showings, reservations, deals — agents & managers only |
| 4 | إيجار | Ejar | ECRS contracts, brokerage profiles, sync logs |
| 5 | الصيانة | Maintenance | Requests, work orders, periodic contracts |
| 6 | حسابي | My Account | User profile, verifications, documents |

Rent payments (الدفعات) live under **إدارة العقارات** as a sub-group with "جميع الدفعات" and "دفعات متأخرة".

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  sa_dashboard   sa_portal   sa_mobile_tech   sa_notifications    │  ← Presentation
├──────────────────────────────────────────────────────────────────┤
│   sa_crm        sa_broker_commission        sa_sadad             │  ← CRM & Financial
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

### `sa_notifications` — Automated Arabic Alerts

Seven email templates with configurable cron triggers: rent reminders, overdue alerts, contract expiry warnings, maintenance confirmations, technician assignments.

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
| Odoo 17 | `odoo:17.0` | 8069 |

### Docker volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `odoo-db-data` | PostgreSQL data dir | Database persistence |
| `odoo-web-data` | `/var/lib/odoo` | Filestore (attachments, sessions) |
| `./addons` | `/mnt/extra-addons` | Custom modules |
| `./config` | `/etc/odoo` | `odoo.conf` |

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

### 3. Create the database (choose one)

```bash
# Clean setup with demo data — recommended for new deployments
bash create-demodb.sh --with-demo propza

# Clean setup without demo data
bash create-demodb.sh propza

# Full teardown and rebuild from scratch
bash create-demodb.sh -f --with-demo propza
```

### 4. Open in browser

```
http://localhost:8069
Database: propza
Admin:    admin@propza.sa  /  admin
Demo users: (any demo email)  /  demo
```

---

## Demo Database

Loaded by `create-demo-data.sh`. All content in Arabic, covering realistic Saudi scenarios:

| Category | Count | Details |
|----------|-------|---------|
| Brokerage Profile | 1 | Propza, Riyadh, UAT credentials |
| Owners (ملاك) | 4 | 3 individuals + 1 company |
| Tenants (مستأجرون) | 10 | Mix of NID, Iqama; 6 verified · 2 pending · 2 draft/rejected |
| Brokers (وسطاء) | 3 | 2 individuals + 1 company |
| Technicians (فنيون) | 3 | Plumbing / Electrical+HVAC / Painting+Carpentry |
| Properties (عقارات) | 12 | 8 residential + 4 commercial; Riyadh, Jeddah, Dammam |
| Tenancies (عقود إيجار) | 11 | 7 running · 1 confirmed · 3 draft |
| Rent Payments (دفعات) | 31 | 22 paid · 8 pending · 1 overdue |
| Inspections (معاينات) | 5 | 3 signed · 1 complete · 1 draft |
| Maintenance Requests | 10 | new×2 · approved×4 · scheduled×1 · in_progress×1 · done×2 |
| Work Orders | 4 | 2 scheduled · 2 done |
| Maintenance Contracts | 2 | HVAC + plumbing (both active) |
| Broker Commissions | 4 | All confirmed — 172,200 SAR total |
| **Ejar ECRS Contracts** | **6** | One per state: draft · building · ready · submitted · approved · rejected |
| Contract Parties | 10 | 5 lessors + 5 tenants; 7 synced · 2 pending · 1 failed |
| Contract Units | 5 | villa×1 · apartment×3 · office×1; various furnishing states |
| Sync Logs | 10 | 8 outbound + 2 inbound; 8 success · 2 error |
| ID Verifications | 10 | 6 verified · 2 submitted · 2 draft/rejected |
| User Documents | 12 | National IDs, lease contracts, salary letters |
| System Users | 24 | 12 internal + 12 portal — password: `demo` |

**Login credentials**

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@propza.sa` | `admin` |
| Property Manager | `manager@propza-demo.sa` | `demo` |
| Accountant | `accountant@propza-demo.sa` | `demo` |
| Agent | `agent@propza-demo.sa` | `demo` |
| Owner (sample) | `m.qahtani@propza-demo.sa` | `demo` |
| Tenant (sample) | `k.rashidi@propza-demo.sa` | `demo` |

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `start.sh` | Start containers (`docker compose up -d`) |
| `stop.sh` | Stop containers |
| `logs.sh` | Tail Odoo container logs |
| `install-docker.sh` | Install Docker + compose on Ubuntu |
| `install-addons.sh` | Install or upgrade custom addons on any database |
| `create-demodb.sh` | Create database, install modules, configure; supports `--fresh` and `--with-demo` |
| `create-demo-data.sh` | Seed database with full Arabic Saudi demo data |

### `create-demodb.sh` flags

| Flag | Effect |
|------|--------|
| *(none)* | Create DB + install + configure (skips if DB already exists) |
| `-u` | Upgrade all modules on existing DB |
| `-f` / `--fresh` | Drop existing DB, terminate connections, recreate from scratch |
| `--with-demo` | Also run `create-demo-data.sh` after install |
| `-f --with-demo` | Full clean teardown + install + demo data in one command |

```bash
# Examples
bash create-demodb.sh propza                       # new install
bash create-demodb.sh -u propza                    # upgrade modules
bash create-demodb.sh -f --with-demo propza        # full reset + demo data
ODOO_DB=propza bash create-demodb.sh --with-demo  # use env var for DB name
```

### `install-addons.sh` flags

```bash
bash install-addons.sh propza              # install all custom addons
bash install-addons.sh -u propza           # upgrade all custom addons
bash install-addons.sh --configure propza  # install + configure company (SAR, SA, Arabic)
bash install-addons.sh --list              # print discovered module names
bash install-addons.sh --modules sa_property_base,l10n_sa_ejar propza  # specific modules
```

---

## Configuration

### Upgrading a module after code changes

```bash
bash install-addons.sh -u propza
# or upgrade a specific module:
COMPOSE=$(bash .compose)
$COMPOSE run --rm web odoo -d propza -u l10n_sa_ejar --stop-after-init
$COMPOSE restart web
```

### Running the Odoo shell

```bash
COMPOSE=$(bash .compose)
$COMPOSE run --rm -T web odoo shell -d propza << 'PYEOF'
# Python code
company = env['res.company'].search([], limit=1)
print(company.name, company.currency_id.name)
PYEOF
```

### Watching logs

```bash
bash logs.sh
# or:
docker logs -f odoo17
```

### Clearing stale asset bundles

```bash
docker exec odoo17-db psql -U odoo17 -d propza \
  -c "DELETE FROM ir_attachment WHERE res_model='ir.ui.view' AND name LIKE '%.assets%';"
$(bash .compose) restart web
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
proptech-ejar/
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
│   ├── sa_maintenance/                  ← Maintenance: requests, work orders, contracts
│   ├── sa_mobile_tech/
│   ├── sa_broker_commission/
│   ├── sa_notifications/
│   ├── sa_sadad/
│   ├── sa_dashboard/
│   ├── sa_portal/
│   ├── sa_security/
│   └── sa_user_profile/
├── config/odoo.conf
├── docker-compose.yml
├── install-addons.sh
├── create-demodb.sh
├── create-demo-data.sh
├── start.sh  stop.sh  logs.sh
└── install-docker.sh
```

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
ssh proptech-amlak "cd ~/propza-amlak && git pull && ODOO_DB=propza bash install-addons.sh propza 2>&1"
```

**Server:** `13.50.5.37` — `ubuntu@proptech-amlak` (SSH alias)

---

**Built by Abdelrehman Elhaj**

| | |
|---|---|
| Email | a.elhaj@proptech.sa |
| LinkedIn | [abdelrehman-elhaj](https://www.linkedin.com/in/abdelrehman-elhaj-972a49257/) |

*Odoo 17 · PostgreSQL 15 · Docker · OCA queue_job*
