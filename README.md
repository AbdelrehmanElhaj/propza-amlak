# propza-amlak Property Management System

A Saudi-first property management system built on **Odoo 17**, covering the full real estate lifecycle: properties, tenancies, rent collection, maintenance, broker commissions, SADAD payments, and a self-service tenant portal — with deep compliance for the Saudi market (Ejar, ZATCA, Riyadh rent freeze).

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
- [Roles & Permissions](#roles--permissions)
- [Saudi Compliance](#saudi-compliance)
- [Development Guide](#development-guide)

---

## Overview

Propza replaces generic property management add-ons with a system purpose-built for the Saudi rental market. Key design decisions:

- **No vendor lock-in** — thin `sa_property_base` core that other modules extend cleanly
- **Arabic-first** — all UI labels, email templates, and data in Arabic; locale `ar_001`, timezone `Asia/Riyadh`, currency SAR
- **Saudi regulations built in** — Riyadh rent freeze (2025–2030), Ejar contract tracking, tenant national ID / Iqama, ZATCA audit trail
- **Role-aware** — 7 RBAC groups with enforced record rules; every user sees only what they are authorised to see

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  sa_dashboard   sa_portal   sa_mobile_tech   sa_notifications   │  ← Presentation layer
├─────────────────────────────────────────────────────────────────┤
│        sa_broker_commission        sa_sadad                     │  ← Financial integrations
├─────────────────────────────────────────────────────────────────┤
│                    sa_rental_cycle                              │  ← Full rental workflow
├────────────────────┬────────────────────────────────────────────┤
│     sa_property    │           sa_maintenance                   │  ← Domain models
├────────────────────┴────────────────────────────────────────────┤
│             l10n_sa_ejar      sa_security                       │  ← Localisation & RBAC
├─────────────────────────────────────────────────────────────────┤
│                    sa_property_base                             │  ← Foundation
├─────────────────────────────────────────────────────────────────┤
│             Odoo 17  (account, mail, portal, contacts)          │  ← Core Odoo
└─────────────────────────────────────────────────────────────────┘
```

**Module load order** (dependency graph):

```
sa_property_base
├── l10n_sa_ejar
│   └── sa_property
│       └── sa_rental_cycle
│           ├── sa_broker_commission
│           ├── sa_notifications
│           └── sa_sadad
├── sa_maintenance
│   └── sa_mobile_tech
├── sa_dashboard
└── sa_security
    └── sa_portal
```

---

## Module Reference

### 1. `sa_property_base` — Foundation

The minimal core. Defines the two central models and the root menu entry that all other modules extend.

| Model | Purpose |
|-------|---------|
| `property.property` | A physical real estate unit (address, type, owner, area) |
| `property.tenancy` | A rental contract linking a property, tenant, and payment schedule |
| `property.inspection` | Move-in / move-out condition reports with room-by-room line items |

**Key features**
- Sequences for property and tenancy references
- Mail thread & activity mixin on all models (full chatter)
- Inspection PDF report and lease contract PDF report
- Hides Odoo's default Discuss menu (clean app grid)

---

### 2. `l10n_sa_ejar` — Saudi Localisation & Ejar Integration

Adds all Saudi-specific fields and the Ejar platform connector.

**Fields added to `property.property`**
- `deed_number` — رقم الصك (property title deed)
- `national_address` — رقم العنوان الوطني
- `sa_region_id` → `sa.region` (14 official Saudi administrative regions)

**Fields added to `property.tenancy`**
- `tenant_id_type` — national_id / iqama / gcc / commercial
- `tenant_national_id` — ID or Iqama number
- `ejar_contract_number` — Ejar reference
- `ejar_status` — pending / registered / active / expired
- `sadad_reference` — SADAD payment code

**Ejar sync wizard** — credentials-ready connector (development mode returns mock data; production requires REGA API key).

**Riyadh rent freeze** — `_check_rent_freeze()` constraint enforced on all Riyadh (`sa_region_id.code = 'RI'`) property tenancy renewals; blocks any `renewal_rent_increase_pct > 0` until September 2030.

---

### 3. `sa_property` — Property & Tenancy Views

Extends base models with Saudi-specific views and property types.

**Property types** (loaded via `sa_property_types.xml`):
`villa` · `apartment` · `floor` · `annex` · `land` · `shop` · `office` · `warehouse`

**Adds to views**
- Full Saudi property form (deed, national address, region, area m²)
- Tenancy form with identity section (ID type, number, expiry, Iqama scan)
- Kanban and list views for both models

---

### 4. `sa_rental_cycle` — Complete Rental Workflow

The end-to-end rental operations module. Central to the system.

**Payment schedule**
- Generated automatically on tenancy confirmation based on frequency (monthly / quarterly / semi-annual / annual)
- Each line is a `sa.rent.payment` record with due date, amount, and status

**Payment statuses**
| Status | Meaning |
|--------|---------|
| `draft` | Not yet due |
| `due` | Due today or past due |
| `paid` | Collected (linked to `account.payment`) |
| `overdue` | Past due with no payment |
| `partial` | Partially collected |

**Wizards**
- `sa.payment.wizard` — record a rent payment; generates journal entry
- `sa.end.tenancy.wizard` — terminate a contract; reconciles deposit, final dues
- `sa.tenancy.renewal.wizard` — renew with optional rent increase (blocked for Riyadh)

**Owner dashboard** — Kanban view per owner showing income, occupancy, and arrears across their portfolio.

**Compliance reports**
- Active contracts register (with colour-coded expiry)
- Revenue by owner (pivot)
- Contracts expiring within 60 days
- Arrears aging (pivot)
- Tenant account statement (PDF)

**Scheduled job** — `sa_rental_cron` runs daily to flip `draft` → `due` and `due` → `overdue` based on today's date.

---

### 5. `sa_maintenance` — Maintenance Management

Full maintenance lifecycle from request to completion, including contractor management.

**Models**

| Model | Purpose |
|-------|---------|
| `sa.maintenance.request` | A reported issue (category, priority, property, tenant) |
| `sa.maintenance.work_order` | Assigned work to a specific technician |
| `sa.maintenance.contract` | Periodic maintenance agreement (monthly, quarterly, annual) |
| `sa.maintenance.skill` | Technician speciality taxonomy |

**Request categories**: `plumbing` · `electrical` · `ac` · `painting` · `carpentry` · `civil` · `other`

**Request state machine**
```
new → approved → scheduled → in_progress → done
                                         ↘ cancelled
```

**Cost tracking** — Three cost lines per request: materials, labour, transportation. Cost bearer: `owner` or `tenant`.

**Attachments** — Before/after photos, contractor quotations, invoices stored as `ir.attachment`.

**Maintenance contracts** — Periodic contracts with automatic request generation via `action_generate_request()`. Cron can auto-generate at interval.

**Technician / contractor partner fields**
- `is_technician` — boolean on `res.partner`
- `sa_skill_ids` — many2many to `sa.maintenance.skill`
- `sa_hourly_rate`, `sa_call_out_fee`, `sa_response_hours`

---

### 6. `sa_mobile_tech` — Field Technician Mobile UI

Mobile-optimised Odoo interface for technicians in the field.

- Kanban "My Work Today" view — swipe-friendly, sorted by scheduled time
- Single-column form with large action buttons (`Start` / `Done` / `Upload Photo`)
- Before/after photo capture widget per work order
- Responsive CSS for phone screen widths
- Default landing page is the technician's kanban (no app grid)
- Restricted to `group_pms_technician`

---

### 7. `sa_broker_commission` — Broker Commissions

Links broker partners to tenancy contracts and manages the commission financial flow.

**Commission model** (`sa.broker.commission`)
- Linked to a `property.tenancy` and a broker `res.partner`
- Commission basis: `percentage` (% of annual rent) or `fixed` (SAR amount)
- Payment patterns: `one_time` · `monthly` · `installment`
- State machine: `draft` → `confirmed` → `paid`

**Financial flow**
1. Confirm commission → payment schedule generated
2. Per payment line → "Create Invoice" → Odoo vendor bill (`account.move` type `in_invoice`)
3. Post bill → Register payment → commission line flips to `paid`

**Reports**
- Monthly broker commission summary
- Annual broker commission report

---

### 8. `sa_notifications` — Automated Alerts

Seven Arabic email templates with configurable cron triggers.

| Template | Trigger |
|----------|---------|
| تذكير دفعة الإيجار | 7 days before due date |
| تنبيه متأخرات الإيجار | Day of / after overdue |
| تنبيه انتهاء العقد | 60 / 30 / 14 days before expiry |
| تأكيد طلب الصيانة | On maintenance request creation (to tenant) |
| إسناد أمر العمل | On work order assignment (to technician) |
| إتمام الصيانة | On work order completion (to tenant) |
| تجديد تلقائي للعقد | On auto-renewal trigger |

**Settings** — 9 toggle switches under `Settings → إدارة العقارات — التنبيهات` to enable/disable each category independently.

---

### 9. `sa_sadad` — SADAD Payment Simulator

Simulates the Saudi SADAD payment network for development and demo purposes.

**`sa.sadad.invoice` model**
- 15-digit SADAD invoice number (auto-sequenced)
- Biller code configurable in settings
- QR code generated from invoice data
- Validity period configurable (default 7 days)
- Webhook endpoint (`/sadad/webhook`) simulates SADAD callback and auto-marks `sa.rent.payment` as paid

**PDF receipt** — Arabic-formatted payment receipt with QR code.

> **Production note:** Real SADAD integration requires an agreement with SAMA and a bank partnership. This module is a functional simulator only.

---

### 10. `sa_dashboard` — KPI Dashboard

Interactive single-page dashboard embedded inside Odoo (not a new browser tab).

**KPI cards**
- إجمالي العقارات — total properties
- عقود سارية — active tenancies
- إيرادات هذا الشهر — current month revenue (SAR)
- متأخرات — total overdue rent (SAR)

**Charts** (Chart.js)
- 12-month revenue trend line
- Property occupancy donut (occupied vs available)
- Maintenance cost by category bar chart

**Tables**
- Top 5 overdue tenants (amount + days overdue)
- Top 5 contracts expiring soon (date + property)

All data respects `sa_security` record rules — owners see only their portfolio; managers see all.

---

### 11. `sa_portal` — Tenant Self-Service Portal

Four Odoo portal pages accessible at `/my/...` after tenant portal login.

| URL | Content |
|-----|---------|
| `/my/contracts` | Lease agreement list + property details |
| `/my/payments` | Payment schedule, stat cards, account statement |
| `/my/maintenance` | Maintenance request list + new request form |
| `/my/inspections` | Inspection reports (read-only) |

Data is filtered by `sa_security` record rules so tenants only see their own records.

---

### 12. `sa_security` — RBAC & Record Rules

Central security module. All other modules depend on the groups defined here.

**Groups (7 roles)**

| Group | Arabic | Access Level |
|-------|--------|-------------|
| `group_pms_admin` | مدير النظام | Full access to all models + settings |
| `group_pms_manager` | مدير العقارات | All operational data; no system settings |
| `group_pms_accountant` | المحاسب | Financial records; read-only on properties |
| `group_pms_agent` | موظف خدمة عملاء | Read + create; limited write |
| `group_pms_owner` | مالك عقار | Own properties, tenancies, maintenance only |
| `group_pms_technician` | فني صيانة | Assigned work orders and requests only |
| `group_pms_tenant` | مستأجر (بوابة) | Portal access (`/my/...`) to own records |

**Record rules** (enforced at ORM level)
- Owners see only properties where `owner_partner_id = current_user.partner_id`
- Technicians see only work orders where `technician_id = current_user.partner_id`
- Portal tenants see only tenancies / payments / maintenance where `partner_id = current_user.partner_id`

**Additional features**
- Audit log (`pms.audit.log`) — every model write tracked with user, timestamp, field, old/new value
- Last login tracking per user
- Permission matrix page (HTML) — visual overview of role × model × CRUD

---

## Infrastructure

### Stack

| Component | Image | Port |
|-----------|-------|------|
| PostgreSQL 15 | `postgres:15` | 5432 (internal) |
| Odoo 17 | `odoo:17.0` | 8069 |

### Docker volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `odoo-db-data` | PostgreSQL data dir | Database persistence |
| `odoo-web-data` | `/var/lib/odoo` | Filestore (attachments, sessions) |
| `./addons` | `/mnt/extra-addons` | Custom module hot-reload |
| `./config` | `/etc/odoo` | `odoo.conf` |

### `odoo.conf` defaults

```ini
admin_passwd = admin@123
db_host = db
db_port = 5432
db_user = odoo17
db_password = odoo17
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
log_level = info
workers = 0          # single-process (dev mode); increase for production
max_cron_threads = 1
list_db = False      # hides database manager from login page
```

---

## Quick Start

### Prerequisites

- Docker ≥ 24
- `docker-compose` v1 CLI (the `docker-compose` binary, not the v2 `docker compose` plugin)
- Git

### 1. Install Docker (Ubuntu)

```bash
bash install-docker.sh
```

### 2. Clone and start

```bash
git clone git@github.com:AbdelrehmanElhaj/Propza-Saudi.git
cd Propza-Saudi/odoo17
bash setup.sh        # first-time: pulls images, creates volumes, starts containers
```

### 3. Create the demo database

```bash
bash create_demodb.sh     # ~5 minutes; installs all 12 modules
bash create_demo_data.sh  # ~2 minutes; seeds Arabic demo data
```

### 4. Open in browser

```
http://localhost:8069
Database: demodb
Login:    demo@demo.com
Password: demo
```

---

## Demo Database

The `demodb` database ships with realistic Saudi demo data (all content in Arabic):

| Category | Count | Detail |
|----------|-------|--------|
| الملاك (Owners) | 4 | 3 individuals + 1 company |
| المستأجرون (Tenants) | 8 | Mix of national ID and Iqama holders |
| الوسطاء (Brokers) | 3 | 2 individuals + 1 company |
| الفنيون (Technicians) | 3 | Plumbing / Electrical+HVAC / Painting+Carpentry |
| العقارات (Properties) | 12 | Villas, apartments, offices, warehouse, shop |
| Cities | 3 | الرياض · جدة · الدمام |
| عقود الإيجار (Tenancies) | 9 | 6 active · 1 confirmed · 1 draft · 1 expired |
| الدفعات (Rent payments) | 31 | Various statuses |
| المعاينات (Inspections) | 5 | 3 signed · 1 complete · 1 draft |
| طلبات الصيانة (Maintenance) | 8 | All categories and statuses represented |
| أوامر العمل (Work orders) | 4 | 1 scheduled · 2 done · 1 in-progress |
| عقود صيانة (Maint. contracts) | 2 | HVAC + plumbing (both active) |
| عمولات الوسطاء (Commissions) | 4 | All confirmed and paid |

**Admin credentials:** `demo@demo.com` / `demo`

---

## Scripts Reference

All scripts live in `odoo17/` and must be run from that directory.

| Script | Purpose |
|--------|---------|
| `setup.sh` | First-time setup: pull images, create volumes, start containers |
| `start.sh` | Start containers (`docker-compose up -d`) |
| `stop.sh` | Stop containers |
| `restart.sh` | Restart Odoo container only |
| `status.sh` | Show container status and recent logs |
| `logs.sh` | Tail Odoo logs |
| `backup.sh` | Dump all databases to `odoo17/backups/` |
| `reset.sh` | Wipe database and recreate (destructive) |
| `create_demodb.sh` | Create `demodb`, install all 12 modules, configure Arabic + SAR |
| `create_demo_data.sh` | Seed `demodb` with Arabic Saudi demo data |

### `create_demodb.sh` internals

1. Verifies containers are running
2. Aborts if `demodb` already exists (safe re-run)
3. Runs `odoo -d demodb --without-demo=all --load-language ar_001 -i <all_modules> --stop-after-init`
4. Opens Odoo shell to: activate SAR currency, set company country to Saudi Arabia, set admin credentials and Arabic locale

### `create_demo_data.sh` internals

Pipes a single Python script to `odoo shell -d demodb`. Creates all records in dependency order with `env.cr.commit()` checkpoints after each group so partial failures don't roll back everything.

---

## Configuration

### Adding a new database

```bash
# Inside odoo17/
docker-compose run --rm web odoo \
  -d mydb \
  --without-demo=all \
  --load-language ar_001 \
  -i sa_property_base,l10n_sa_ejar,sa_property,sa_security,sa_maintenance,sa_notifications,sa_rental_cycle,sa_sadad,sa_broker_commission,sa_dashboard,sa_portal,sa_mobile_tech \
  --stop-after-init
```

### Upgrading a module after code changes

```bash
docker-compose run --rm web odoo \
  -d demodb \
  -u sa_rental_cycle \
  --stop-after-init
```

Then restart Odoo: `bash restart.sh`

### Changing log level

Edit `odoo17/config/odoo.conf`:
```ini
log_level = debug   # or: info, warn, error, critical
```
Then `bash restart.sh`.

### Production workers

```ini
workers = 4
max_cron_threads = 2
```
Also add a reverse proxy (nginx) in front of port 8069.

---

## Roles & Permissions

| Role | Login to Odoo backend | Properties | Tenancies | Payments | Maintenance | Brokers | Settings |
|------|----------------------|------------|-----------|----------|-------------|---------|----------|
| Admin | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ |
| Manager | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ✅ All | ❌ |
| Accountant | ✅ | Read | ✅ All | ✅ All | Read | ✅ All | ❌ |
| Agent | ✅ | Read + Create | Read + Create | Read | Read + Create | Read | ❌ |
| Owner | ✅ Own only | Own only | Own only | Own only | Own only | ❌ | ❌ |
| Technician | ✅ (maintenance only) | ❌ | ❌ | ❌ | Assigned only | ❌ | ❌ |
| Tenant | Portal `/my/` only | ❌ | Own only | Own only | Own only | ❌ | ❌ |

Record rules are enforced at the ORM level — not just UI — so API access is also restricted.

---

## Saudi Compliance

### Riyadh Rent Freeze

Royal decree prohibits rent increases on Riyadh properties from 2025 to September 2030. Enforced by `_check_rent_freeze()` in `l10n_sa_ejar/models/sa_tenancy_renewal.py`:

```python
if property.sa_region_id.code == 'RI' and renewal_rent_increase_pct > 0:
    raise UserError(_('لا يُسمح بزيادة الإيجار في عقارات الرياض حتى سبتمبر 2030'))
```

The renewal wizard also shows a yellow warning banner when a Riyadh property is selected.

### Ejar Platform

`l10n_sa_ejar` stores the Ejar contract number and sync status. The sync wizard sends contract data to the REGA API. In development mode a mock response is returned; production deployment requires:
- REGA API credentials in `Settings → l10n_sa_ejar`
- HTTPS endpoint accessible from the server

### ZATCA Audit Trail

`sa_security` logs every write to a tracked model into `pms.audit.log` with:
- User, timestamp
- Model and record ID
- Field name, old value, new value

Posted `account.move` and `account.payment` records are protected from deletion by override of `unlink()`.

### National Address & IDs

All partner and property forms collect:
- رقم الهوية الوطنية or رقم الإقامة (with expiry)
- رقم العنوان الوطني (Saudi short address)
- IBAN in SA format (24 characters starting with `SA`)

---

## Development Guide

### Repository structure

```
propza-dev-v0.0.0/
├── odoo17/
│   ├── addons/
│   │   ├── sa_property_base/
│   │   │   ├── __manifest__.py
│   │   │   ├── models/
│   │   │   ├── views/
│   │   │   │   ├── menu_root.xml       ← defines root menu early (loaded first)
│   │   │   │   └── menu.xml            ← child menus (loaded after actions)
│   │   │   ├── data/
│   │   │   ├── security/
│   │   │   └── report/
│   │   ├── l10n_sa_ejar/
│   │   ├── sa_property/
│   │   ├── sa_rental_cycle/
│   │   ├── sa_maintenance/
│   │   ├── sa_mobile_tech/
│   │   ├── sa_broker_commission/
│   │   ├── sa_notifications/
│   │   ├── sa_sadad/
│   │   ├── sa_dashboard/
│   │   ├── sa_portal/
│   │   └── sa_security/
│   ├── config/odoo.conf
│   ├── docker-compose.yml
│   └── *.sh
├── TESTING_GUIDE.md
└── README.md
```

### XML load order rule

Every module that defines a root `<menuitem>` **must** put it in a separate `views/menu_root.xml` file, loaded **first** in `__manifest__.py` → `data`. Child menus that reference actions must come **after** the views that define those actions.

```python
# Correct pattern in __manifest__.py
'data': [
    'security/ir.model.access.csv',
    'views/menu_root.xml',      # ← root menuitem first
    'views/model_views.xml',    # ← defines actions
    'views/menu.xml',           # ← child menuitems last
],
```

### Running Odoo shell

```bash
cd odoo17
docker-compose run --rm -T web odoo shell -d demodb << 'PYEOF'
# Python code here
env['res.partner'].search([('is_tenant', '=', True)])
PYEOF
```

### Watching logs

```bash
bash logs.sh          # tails odoo17 container logs
# or directly:
docker logs -f odoo17
```

### Clearing stale asset bundles

If JavaScript changes are not appearing after a module upgrade:

```bash
docker exec odoo17-db psql -U odoo17 -d demodb \
  -c "DELETE FROM ir_attachment WHERE res_model='ir.ui.view' AND name LIKE '%.assets%';"
bash restart.sh
```

### Running module upgrade

```bash
docker-compose run --rm web odoo -d demodb -u sa_dashboard --stop-after-init
bash restart.sh
```

### Git workflow

```bash
git checkout -b feature/my-feature
# make changes
git add odoo17/addons/sa_my_module/
git commit -m "feat(sa_my_module): description"
git push origin feature/my-feature
# open PR → merge → pull on EC2 → restart Odoo
```

### EC2 deployment

```bash
# On your local machine
ssh -i Propza-Saudi-dev.pem ubuntu@ec2-51-21-218-85.eu-north-1.compute.amazonaws.com \
  "cd ~/Propza-Saudi && git pull origin main && cd odoo17 && docker-compose restart web"
```

---

---

**Built by Abdelrehman Elhaj**

| | |
|---|---|
| Email | hdr333@gmail.com |
| Mobile | +966 57 377 1364 |
| LinkedIn | [abdelrehman-elhaj](https://www.linkedin.com/in/abdelrehman-elhaj-972a49257/) |

*Odoo 17 · PostgreSQL 15 · Docker*
