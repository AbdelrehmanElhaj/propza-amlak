#!/bin/bash
# Propza — all-in-one demo setup.
#
# Usage:
#   ./setup-demo.sh [DB]           Create DB, install modules, seed demo data  (default: demodb)
#   ./setup-demo.sh -f [DB]        Drop existing DB first, then full setup
#   ./setup-demo.sh -u [DB]        Upgrade modules on existing DB, re-seed data
#   ./setup-demo.sh --no-demo [DB] Create DB + install modules only
#
# Environment:
#   ODOO_DB          Database name override
#   ADMIN_EMAIL      Admin login (default: admin@propza.sa)
#   ADMIN_PASSWORD   Admin password (default: admin)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ADDONS_DIR="$ROOT/addons"
DB="${ODOO_DB:-demodb}"
FRESH=false
UPGRADE=false
WITH_DEMO=true

# ── Auto-detect compose command ───────────────────────────────────────────────
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    echo "ERROR: Docker Compose not found." >&2; exit 1
fi

usage() {
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    echo ""
}

# ── Helpers ───────────────────────────────────────────────────────────────────
require_containers() {
    if ! docker ps --format '{{.Names}}' | grep -q '^odoo17$'; then
        echo "ERROR: Odoo container is not running. Start it first: ./start.sh" >&2
        exit 1
    fi
}

db_exists() {
    docker exec odoo17-db psql -U odoo17 -d postgres -lqt 2>/dev/null \
        | cut -d'|' -f1 | tr -d ' ' | grep -qx "$1"
}

drop_db() {
    local db="$1"
    echo "Terminating connections to '$db'..."
    docker exec odoo17-db psql -U odoo17 -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$db' AND pid <> pg_backend_pid();" \
        >/dev/null 2>&1 || true
    echo "Dropping '$db'..."
    docker exec odoo17-db psql -U odoo17 -d postgres -c "DROP DATABASE IF EXISTS \"$db\";"
}

discover_modules() {
    local mods=()
    for d in "$ADDONS_DIR"/*/; do
        [ -f "${d}__manifest__.py" ] || continue
        mods+=("$(basename "$d")")
    done
    [ "${#mods[@]}" -gt 0 ] || { echo "ERROR: No modules in $ADDONS_DIR" >&2; exit 1; }
    (IFS=','; echo "${mods[*]}")
}

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        -f|--fresh)   FRESH=true; shift ;;
        -u|--upgrade) UPGRADE=true; shift ;;
        --no-demo)    WITH_DEMO=false; shift ;;
        -*) echo "ERROR: Unknown option: $1" >&2; usage; exit 1 ;;
        *)  DB="$1"; shift ;;
    esac
done

require_containers

echo "=========================================="
echo "  Propza Demo Setup — $DB"
echo "=========================================="
echo ""

# Drop if --fresh
if [ "$FRESH" = true ] && db_exists "$DB"; then
    drop_db "$DB"
fi

# ── Module install / upgrade ──────────────────────────────────────────────────
MODULES="$(discover_modules)"
MODULE_COUNT="$(echo "$MODULES" | tr ',' '\n' | wc -l)"
LOG_FILE="$ROOT/logs/install-${DB}-$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$ROOT/logs"

# Determine install action flag
#   existing DB + explicit -u flag  → upgrade
#   existing DB + no flag           → install (idempotent; skips already-installed modules)
#   new DB                          → install
ACTION_FLAG="-i"
[ "$UPGRADE" = true ] && ACTION_FLAG="-u"

if db_exists "$DB" && [ "$UPGRADE" = false ] && [ "$WITH_DEMO" = false ]; then
    echo "Database '$DB' already exists and --no-demo was requested. Nothing to do."
    echo "Use -f to recreate, -u to upgrade, or omit --no-demo to re-seed data."
    exit 0
fi

echo "Running odoo $ACTION_FLAG on $MODULE_COUNT modules (log → $LOG_FILE)..."
echo ""

set +e
$COMPOSE run --rm -T web odoo \
    -d "$DB" \
    --without-demo=all \
    --load-language ar_001 \
    "$ACTION_FLAG" "$MODULES" \
    --stop-after-init \
    2>&1 | tee "$LOG_FILE"
INSTALL_STATUS=${PIPESTATUS[0]}
set -e

if [ "$INSTALL_STATUS" -ne 0 ]; then
    echo ""; echo "ERROR: Module install failed. See $LOG_FILE" >&2
    exit "$INSTALL_STATUS"
fi

# ── Company / locale configuration ────────────────────────────────────────────
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@propza.sa}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

echo ""; echo "Configuring company (SAR, Saudi Arabia, Arabic, Ejar UAT)..."

$COMPOSE run --rm -T web odoo shell -d "$DB" << PYEOF
SAR = env['res.currency'].with_context(active_test=False).search([('name','=','SAR')], limit=1)
SA  = env['res.country'].search([('code','=','SA')], limit=1)
company = env.company

if SAR:
    SAR.write({'active': True})
    env.cr.execute('UPDATE res_company SET currency_id = %s WHERE id = %s', (SAR.id, company.id))
if SA:
    company.country_id = SA
company.write({
    'name':  'Propza Real Estate Brokerage',
    'phone': company.phone or '+966000000000',
})

admin = env['res.users'].search([('login','=','${ADMIN_EMAIL}')], limit=1) \
     or env['res.users'].browse(2)
if admin:
    admin.write({
        'login':    '${ADMIN_EMAIL}',
        'email':    '${ADMIN_EMAIL}',
        'lang':     'ar_001',
        'tz':       'Asia/Riyadh',
        'password': '${ADMIN_PASSWORD}',
    })

params = env['ir.config_parameter'].sudo()
params.set_param('ejar.api.key.company_%d'    % company.id, 'PLACEHOLDER_API_KEY')
params.set_param('ejar.api.secret.company_%d' % company.id, 'PLACEHOLDER_API_SECRET')
params.set_param('ejar.api.environment.company_%d' % company.id, 'uat')
params.set_param('ejar.api.simulation', 'True')

r_riyadh = env['sa.region'].search([('code','=','RUH')], limit=1)
c_riyadh = env['sa.city'].search([('name_ar','ilike','الرياض')], limit=1)
if not env['ejar.brokerage.profile'].search([('company_id','=',company.id)], limit=1):
    env['ejar.brokerage.profile'].create({
        'company_id':            company.id,
        'office_name_ar':        'شركة بروبزا للوساطة العقارية',
        'office_name_en':        'Propza Real Estate Brokerage',
        'cr_number':             '1000000001',
        'unified_number':        '1000000001',
        'license_number':        'FB-LICENSE-001',
        'license_expiry':        '2027-12-31',
        'vat_number':            '300000000000001',
        'national_address_code': 'RIYD0001',
        'building_number':       '1234',
        'street_ar':             'شارع الملك عبدالعزيز',
        'district_ar':           'حي العليا',
        'sa_region_id':          r_riyadh.id if r_riyadh else False,
        'sa_city_id':            c_riyadh.id if c_riyadh else False,
        'postal_code':           '12211',
        'is_verified':           False,
    })

env.cr.commit()
print('Company configured.')
PYEOF

echo ""; echo "Restarting Odoo..."
$COMPOSE restart web

# ── Demo data ─────────────────────────────────────────────────────────────────
if [ "$WITH_DEMO" = false ]; then
    echo ""
    echo "=========================================="
    echo "  Setup complete (no demo data)"
    echo "=========================================="
    echo "  URL:    http://localhost:8069"
    echo "  DB:     $DB"
    echo "  Admin:  ${ADMIN_EMAIL:-admin@propza.sa} / ${ADMIN_PASSWORD:-admin}"
    echo ""
    exit 0
fi

echo ""; echo "Seeding demo data (2-3 minutes)..."
echo ""

$COMPOSE run --rm -T web odoo shell -d "$DB" << 'PYEOF'
import datetime
today = datetime.date.today()
ago   = lambda d: today - datetime.timedelta(days=d)
ahead = lambda d: today + datetime.timedelta(days=d)
dt    = lambda d, h=9: datetime.datetime.combine(d, datetime.time(h, 0))

# ══════════════════════════════════════════════════════════════════════════════
# 0 — Environment
# ══════════════════════════════════════════════════════════════════════════════
SAR     = env['res.currency'].with_context(active_test=False).search([('name','=','SAR')], limit=1)
company = env['res.company'].search([], limit=1)
SA      = env['res.country'].search([('code','=','SA')], limit=1)

def region(code):
    return env['sa.region'].search([('code','=',code)], limit=1)
def city_sa(name):
    return env['sa.city'].search([('name_ar','ilike',name)], limit=1)

r_riyadh = region('RUH') or env['sa.region'].search([], limit=1)
r_jeddah = region('MKH') or r_riyadh
r_dammam = region('EAS') or r_riyadh

c_riyadh = city_sa('الرياض') or env['sa.city'].search([], limit=1)
c_jeddah = city_sa('جدة')    or c_riyadh
c_dammam = city_sa('الدمام') or c_riyadh

ejar_profile = env['ejar.brokerage.profile'].search([('company_id','=',company.id)], limit=1)

# ══════════════════════════════════════════════════════════════════════════════
# 1 — Owners (12)
# ══════════════════════════════════════════════════════════════════════════════
print("1/16  الملاك…")

def owner(vals):
    return env['res.partner'].create({'is_property_owner': True, 'country_id': SA.id, **vals})

owner1 = owner({'name':'محمد بن عبدالله القحطاني','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1023456789',
    'sa_iban':'SA0380000000608010167519','phone':'+966501234001',
    'email':'m.qahtani@propza-demo.sa','city':'الرياض'})
owner2 = owner({'name':'فاطمة بنت سعد الزهراني','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1056789012',
    'sa_iban':'SA4420000001234567891234','phone':'+966502234002',
    'email':'f.zahrani@propza-demo.sa','city':'جدة'})
owner3 = owner({'name':'سالم بن أحمد العتيبي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1078901234',
    'sa_iban':'SA6220000003456789012345','phone':'+966503234003',
    'email':'s.otaibi@propza-demo.sa','city':'الدمام'})
owner4 = owner({'name':'شركة الواحة للتطوير العقاري','company_type':'company',
    'sa_cr_number':'1010345678','sa_iban':'SA1020000005678901234567',
    'phone':'+966114001400','email':'info@alwaha-re.sa','city':'الرياض'})
owner5 = owner({'name':'شركة الدرعية القابضة','company_type':'company',
    'sa_cr_number':'1010987654','sa_iban':'SA9720000007890123456789',
    'phone':'+966116543210','email':'info@diriyah-holdings.sa','city':'الرياض'})

owner6  = owner({'name':'ناصر بن سعد الحربي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1089012340',
    'sa_iban':'SA1980000008901234000012','phone':'+966504234006',
    'email':'n.harbi@propza-demo.sa','city':'الرياض'})
owner7  = owner({'name':'هيلة بنت محمد المطيري','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1012034567',
    'sa_iban':'SA5480000009012034560001','phone':'+966502234007',
    'email':'h.motairi@propza-demo.sa','city':'جدة'})
owner8  = owner({'name':'راشد بن عبدالله الشمري','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1034590123',
    'sa_iban':'SA7680000000345901230001','phone':'+966503234008',
    'email':'r.shammari@propza-demo.sa','city':'المدينة المنورة'})
owner9  = owner({'name':'شركة المملكة للتطوير العقاري','company_type':'company',
    'sa_cr_number':'4030654321','sa_iban':'SA3220000002345678000001',
    'phone':'+966126543211','email':'info@mamlaka-re.sa','city':'جدة'})
owner10 = owner({'name':'شركة الخليج للاستثمار العقاري','company_type':'company',
    'sa_cr_number':'2050123456','sa_iban':'SA4420000004567890000001',
    'phone':'+966381112222','email':'info@gulf-invest.sa','city':'الدمام'})
owner11 = owner({'name':'شركة نجد للتطوير والإنشاء','company_type':'company',
    'sa_cr_number':'1010765431','sa_iban':'SA8820000003456789000001',
    'phone':'+966112223334','email':'invest@najd-dev.sa','city':'الرياض'})
owner12 = owner({'name':'شركة رؤية للتطوير والاستثمار','company_type':'company',
    'sa_cr_number':'1010234567','sa_iban':'SA6620000005678901000001',
    'phone':'+966113334445','email':'info@ruya-dev.sa','city':'الرياض'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 2 — Tenants (28)
# ══════════════════════════════════════════════════════════════════════════════
print("2/16  المستأجرون…")

def tenant(vals):
    return env['res.partner'].create({'is_tenant': True, 'country_id': SA.id, **vals})

tenant1  = tenant({'name':'خالد بن عبدالله الراشدي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1098765432',
    'phone':'+966503100001','email':'k.rashidi@propza-demo.sa'})
tenant2  = tenant({'name':'عمر محمد الفاروق','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1034512678',
    'phone':'+966503100002','email':'o.farouq@propza-demo.sa'})
tenant3  = tenant({'name':'نورة سعد الحمدان','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1067891234',
    'phone':'+966503100003','email':'n.hamdan@propza-demo.sa'})
tenant4  = tenant({'name':'عائشة أحمد مالك','company_type':'person',
    'sa_id_type':'iqama','sa_national_id':'2123456789',
    'sa_id_expiry':str(ahead(180)),
    'phone':'+966503100004','email':'a.malik@propza-demo.sa'})
tenant5  = tenant({'name':'أحمد يوسف العمري','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1055443322',
    'phone':'+966503100005','email':'a.omari@propza-demo.sa'})
tenant6  = tenant({'name':'سارة عبدالرحمن الدوسري','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1066778899',
    'phone':'+966503100006','email':'s.dosari@propza-demo.sa'})
tenant7  = tenant({'name':'محمد علي الشهري','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1077889900',
    'phone':'+966503100007','email':'m.shehri@propza-demo.sa'})
tenant8  = tenant({'name':'ريم عبدالعزيز القرني','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1088990011',
    'phone':'+966503100008','email':'r.qarni@propza-demo.sa'})
tenant9  = tenant({'name':'فيصل محمد الغامدي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1099887766',
    'phone':'+966503100009','email':'f.ghamdi@propza-demo.sa'})
tenant10 = tenant({'name':'لمى عبدالله الزهراني','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1044332211',
    'phone':'+966503100010','email':'l.zahrani@propza-demo.sa'})
tenant11 = tenant({'name':'شركة البستان للتأجير التجاري','company_type':'company',
    'sa_cr_number':'4030112233','phone':'+966505100011',
    'email':'leasing@albostan.sa'})

tenant12 = tenant({'name':'وليد محمد السبيعي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1011223344',
    'phone':'+966503100012','email':'w.subaie@propza-demo.sa'})
tenant13 = tenant({'name':'منال بنت أحمد الحازمي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1022334451',
    'phone':'+966503100013','email':'m.hazmi@propza-demo.sa'})
tenant14 = tenant({'name':'طارق عبدالعزيز المالكي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1033445562',
    'phone':'+966503100014','email':'t.malki@propza-demo.sa'})
tenant15 = tenant({'name':'هند ناصر النومي','company_type':'person',
    'sa_id_type':'iqama','sa_national_id':'2234567891',
    'sa_id_expiry':str(ahead(365)),
    'phone':'+966503100015','email':'h.noomi@propza-demo.sa'})
tenant16 = tenant({'name':'يوسف بن علي القرشي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1044556671',
    'phone':'+966503100016','email':'y.qurashi@propza-demo.sa'})
tenant17 = tenant({'name':'أسماء بنت خالد العنزي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1055667782',
    'phone':'+966503100017','email':'a.anazi@propza-demo.sa'})
tenant18 = tenant({'name':'سلطان بن أحمد البقمي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1066779901',
    'phone':'+966503100018','email':'s.baqami@propza-demo.sa'})
tenant19 = tenant({'name':'رانيا محمد الحربي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1077991122',
    'phone':'+966503100019','email':'r.harbi2@propza-demo.sa'})
tenant20 = tenant({'name':'عبدالرحمن بن سعد الصالح','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1088001123',
    'phone':'+966503100020','email':'a.saleh@propza-demo.sa'})
tenant21 = tenant({'name':'نهى بنت محمد كريم','company_type':'person',
    'sa_id_type':'iqama','sa_national_id':'2345678902',
    'sa_id_expiry':str(ahead(270)),
    'phone':'+966503100021','email':'n.karim@propza-demo.sa'})
tenant22 = tenant({'name':'بندر بن فهد الرشيد','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1099112234',
    'phone':'+966503100022','email':'b.rashid@propza-demo.sa'})
tenant23 = tenant({'name':'ميساء بنت عبدالله القحطاني','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1011334456',
    'phone':'+966503100023','email':'m.qahtani2@propza-demo.sa'})
tenant24 = tenant({'name':'عمار بن إبراهيم الحماد','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1022445567',
    'phone':'+966503100024','email':'a.hammad@propza-demo.sa'})
tenant25 = tenant({'name':'دانة بنت سعود الرشيدي','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1033556672',
    'phone':'+966503100025','email':'d.rashidi2@propza-demo.sa'})
tenant26 = tenant({'name':'شركة الأفق للأعمال والتجارة','company_type':'company',
    'sa_cr_number':'1010556677','phone':'+966115001100',
    'email':'info@ufuq-trade.sa'})
tenant27 = tenant({'name':'شركة المتحدة للتجارة العقارية','company_type':'company',
    'sa_cr_number':'4030445566','phone':'+966507001200',
    'email':'leasing@muttahida-re.sa'})
tenant28 = tenant({'name':'شركة رؤية التجارية للخدمات','company_type':'company',
    'sa_cr_number':'1010334455','phone':'+966114002200',
    'email':'services@ruya-commercial.sa'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 3 — Brokers (6)
# ══════════════════════════════════════════════════════════════════════════════
print("3/16  الوسطاء…")

def broker(vals):
    return env['res.partner'].create({'is_broker': True, 'country_id': SA.id, **vals})

broker1 = broker({'name':'شركة الوافر للوساطة العقارية','company_type':'company',
    'broker_license':'BRK-2024-00123','sa_cr_number':'4030234567',
    'phone':'+966122345678','email':'info@alwafer-broker.sa','city':'الرياض'})
broker2 = broker({'name':'طارق بن محمد الغامدي','company_type':'person',
    'broker_license':'BRK-2024-00456','sa_id_type':'national_id',
    'sa_national_id':'1045678901','phone':'+966504200002','email':'t.ghamdi@broker.sa'})
broker3 = broker({'name':'هند بنت سليمان العمودي','company_type':'person',
    'broker_license':'BRK-2024-00789','sa_id_type':'national_id',
    'sa_national_id':'1099001122','phone':'+966504200003','email':'h.amodi@broker.sa'})

broker4 = broker({'name':'شركة بيت الكفاءة للوساطة العقارية','company_type':'company',
    'broker_license':'BRK-2024-01010','sa_cr_number':'1010112233',
    'phone':'+966124001400','email':'info@kafaa-broker.sa','city':'جدة'})
broker5 = broker({'name':'ريان بن محمد الحسين','company_type':'person',
    'broker_license':'BRK-2024-01111','sa_id_type':'national_id',
    'sa_national_id':'1011000111','phone':'+966504200005','email':'r.hussain@broker.sa'})
broker6 = broker({'name':'نجلاء بنت سليمان البكر','company_type':'person',
    'broker_license':'BRK-2024-01222','sa_id_type':'national_id',
    'sa_national_id':'1022001222','phone':'+966504200006','email':'n.bakr@broker.sa'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 4 — Technicians (10)
# ══════════════════════════════════════════════════════════════════════════════
print("4/16  الفنيون…")

def skill(code):
    return env['sa.maintenance.skill'].search([('code','=',code)], limit=1)

sk_plm = skill('PLM'); sk_elc = skill('ELC')
sk_ac  = skill('ACA'); sk_pnt = skill('PNT'); sk_crp = skill('CRP')

def tech(vals):
    return env['res.partner'].create({'is_technician': True, 'country_id': SA.id, **vals})

tech1 = tech({'name':'حسن البحار للسباكة والصرف الصحي','company_type':'company',
    'sa_cr_number':'1010556677','sa_hourly_rate':80.0,'sa_call_out_fee':50.0,
    'sa_response_hours':4,'sa_skill_ids':[(6,0,sk_plm.ids)] if sk_plm else [],
    'phone':'+966112345601','email':'info@hassan-plumbing.sa','city':'الرياض'})
tech2 = tech({'name':'شركة أحمد للتقنية الكهربائية والتكييف','company_type':'company',
    'sa_cr_number':'1010667788','sa_hourly_rate':100.0,'sa_call_out_fee':75.0,
    'sa_response_hours':2,'sa_skill_ids':[(6,0,(sk_elc+sk_ac).ids)],
    'phone':'+966114502000','email':'support@ahmad-tech.sa','city':'الرياض'})
tech3 = tech({'name':'عبدالله الحربي للدهانات والأعمال الخشبية','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1033221100',
    'sa_hourly_rate':65.0,'sa_call_out_fee':30.0,'sa_response_hours':6,
    'sa_skill_ids':[(6,0,(sk_pnt+sk_crp).ids)],
    'phone':'+966505400003','email':'a.harbi@handyman.sa'})
tech4 = tech({'name':'مجموعة النخبة للصيانة الكهربائية','company_type':'company',
    'sa_cr_number':'1010876543','sa_hourly_rate':120.0,'sa_call_out_fee':60.0,
    'sa_response_hours':3,'sa_skill_ids':[(6,0,(sk_elc+sk_ac).ids)],
    'phone':'+966114503000','email':'support@elite-maintenance.sa'})
tech5 = tech({'name':'شركة الرازي للسباكة والتدفئة','company_type':'company',
    'sa_cr_number':'1010765432','sa_hourly_rate':90.0,'sa_call_out_fee':45.0,
    'sa_response_hours':4,'sa_skill_ids':[(6,0,sk_plm.ids)] if sk_plm else [],
    'phone':'+966114503111','email':'info@razi-plumbing.sa'})

tech6 = tech({'name':'شركة البناء الحديث للصيانة الشاملة','company_type':'company',
    'sa_cr_number':'1010445566','sa_hourly_rate':95.0,'sa_call_out_fee':55.0,
    'sa_response_hours':3,'sa_skill_ids':[(6,0,(sk_elc+sk_pnt).ids)],
    'phone':'+966112345602','email':'info@modern-build.sa','city':'الرياض'})
tech7 = tech({'name':'شركة القمة لخدمات المباني','company_type':'company',
    'sa_cr_number':'1010554433','sa_hourly_rate':85.0,'sa_call_out_fee':40.0,
    'sa_response_hours':5,'sa_skill_ids':[(6,0,(sk_plm+sk_pnt).ids)],
    'phone':'+966124006000','email':'info@qimma-services.sa','city':'جدة'})
tech8 = tech({'name':'مجموعة السعادة للتكييف والتبريد','company_type':'company',
    'sa_cr_number':'1010663322','sa_hourly_rate':110.0,'sa_call_out_fee':65.0,
    'sa_response_hours':2,'sa_skill_ids':[(6,0,(sk_ac+sk_elc).ids)],
    'phone':'+966384506000','email':'info@saada-hvac.sa','city':'الدمام'})
tech9 = tech({'name':'علي النعيمي للأعمال اليدوية','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1034002333',
    'sa_hourly_rate':55.0,'sa_call_out_fee':25.0,'sa_response_hours':8,
    'sa_skill_ids':[(6,0,(sk_crp+sk_pnt).ids)],
    'phone':'+966505400009','email':'a.naimy@handyman.sa'})
tech10 = tech({'name':'فهد الحبشي للتركيبات الكهربائية','company_type':'person',
    'sa_id_type':'national_id','sa_national_id':'1045003444',
    'sa_hourly_rate':75.0,'sa_call_out_fee':35.0,'sa_response_hours':4,
    'sa_skill_ids':[(6,0,sk_elc.ids)] if sk_elc else [],
    'phone':'+966505400010','email':'f.habashi@electrician.sa'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 5 — Properties (32)
# ══════════════════════════════════════════════════════════════════════════════
print("5/16  العقارات…")

def prop(vals):
    return env['property.property'].create({'currency_id': SAR.id, **vals})

# Villas
prop1 = prop({'name':'فيلا الروضة ١٢','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner1.id,'rent_amount':80000,'deposit_amount':80000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الروضة',
    'sa_street':'شارع الإمام سعود','sa_building_no':'12','sa_postal_code':'12241',
    'sa_area_sqm':450,'sa_rooms':5,'sa_bathrooms':4,'sa_parking':2,
    'sa_pool':True,'sa_garden':True,'sa_furnished':'unfurnished','sa_condition':'excellent',
    'sa_year_built':2018,'sa_deed_number':'و-٢٠١٨-رض-٠٠١٢٣٤',
    'description':'فيلا فاخرة من طابقين بحديقة خاصة ومسبح. تقع في حي الروضة الراقي.'})
prop2 = prop({'name':'فيلا النزهة ٨','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner2.id,'rent_amount':95000,'deposit_amount':95000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي النزهة',
    'sa_street':'شارع الأمير سلطان','sa_building_no':'8',
    'sa_area_sqm':520,'sa_rooms':6,'sa_bathrooms':5,'sa_parking':3,
    'sa_pool':True,'sa_furnished':'semi','sa_condition':'excellent','sa_year_built':2020,
    'description':'فيلا واسعة مع إطلالة على الحديقة، مناسبة للعائلات الكبيرة.'})
prop3 = prop({'name':'فيلا النرجس ٣','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner4.id,'rent_amount':110000,'deposit_amount':110000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي النرجس',
    'sa_building_no':'3','sa_area_sqm':600,'sa_rooms':6,'sa_bathrooms':5,'sa_parking':3,
    'sa_pool':True,'sa_garden':True,'sa_furnished':'fully','sa_condition':'excellent',
    'sa_year_built':2022,'sa_deed_number':'و-٢٠٢٢-رض-٠٠٤٥٦٧',
    'description':'فيلا حديثة مجهزة بالكامل وجاهزة للسكن.'})
prop13 = prop({'name':'فيلا النسيم ١٥','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner5.id,'rent_amount':72000,'deposit_amount':72000,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي النسيم',
    'sa_street':'شارع الأمير محمد بن فهد',
    'sa_area_sqm':430,'sa_rooms':5,'sa_bathrooms':4,'sa_parking':2,
    'sa_pool':True,'sa_garden':True,'sa_furnished':'semi','sa_condition':'good',
    'sa_year_built':2017,'description':'فيلا عائلية فاخرة مطلة على حديقة مشتركة.'})

# Riyadh apartments
prop4 = prop({'name':'شقة العليا – ٣ب','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner1.id,'rent_amount':45000,'deposit_amount':22500,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_street':'طريق الملك فهد','sa_floor_number':3,'sa_total_floors':10,
    'sa_area_sqm':140,'sa_rooms':3,'sa_bathrooms':2,'sa_elevator':True,
    'sa_furnished':'semi','sa_condition':'good','sa_year_built':2015,
    'description':'شقة ثلاث غرف في برج راقٍ بحي العليا، قريبة من الخدمات.'})
prop5 = prop({'name':'شقة الملقا – ٧أ','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner1.id,'rent_amount':48000,'deposit_amount':24000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الملقا',
    'sa_floor_number':7,'sa_total_floors':15,'sa_area_sqm':160,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good',
    'description':'شقة فسيحة قريبة من المدارس والمجمعات التجارية.'})

# Jeddah & Dammam apartments
prop6 = prop({'name':'شقة الحمراء – ١٥','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner2.id,'rent_amount':42000,'deposit_amount':21000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي الحمراء',
    'sa_floor_number':2,'sa_area_sqm':130,'sa_rooms':3,'sa_bathrooms':2,
    'sa_furnished':'semi','sa_condition':'good',
    'description':'شقة مطلة على الشارع في حي الحمراء الراقي بجدة.'})
prop7 = prop({'name':'شقة المرجان – ٢٢','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner3.id,'rent_amount':38000,'deposit_amount':19000,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي المرجان',
    'sa_floor_number':4,'sa_area_sqm':120,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','sa_year_built':2019,
    'description':'شقة حديثة في حي المرجان بالدمام، قريبة من الخدمات.'})
prop8 = prop({'name':'شقة الدانة – ١٠د','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner3.id,'rent_amount':35000,'deposit_amount':17500,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي الدانة',
    'sa_floor_number':1,'sa_area_sqm':110,'sa_rooms':2,'sa_bathrooms':2,
    'sa_furnished':'unfurnished','sa_condition':'good',
    'description':'شقة بسعر مناسب في حي الدانة، مناسبة للأفراد والعائلات الصغيرة.'})

# Offices
prop9 = prop({'name':'مكتب بيزنس باي – ٢٠١','property_type':'commercial','sa_property_subtype':'office',
    'owner_partner_id':owner4.id,'rent_amount':120000,'deposit_amount':60000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_street':'طريق الملك فهد','sa_floor_number':20,'sa_total_floors':30,
    'sa_area_sqm':280,'sa_elevator':True,'sa_furnished':'fully','sa_condition':'excellent',
    'sa_year_built':2022,'description':'مكتب تنفيذي بإطلالة بانورامية على الرياض.'})
prop10 = prop({'name':'مكتب طريق الملك فهد – أ','property_type':'commercial','sa_property_subtype':'office',
    'owner_partner_id':owner4.id,'rent_amount':85000,'deposit_amount':42500,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الورود',
    'sa_floor_number':5,'sa_area_sqm':200,'sa_elevator':True,
    'sa_furnished':'semi','sa_condition':'good',
    'description':'مكتب في موقع استراتيجي على طريق الملك فهد.'})

# Commercial
prop11 = prop({'name':'محل الشميسي التجاري – ٥','property_type':'commercial','sa_property_subtype':'shop',
    'owner_partner_id':owner3.id,'rent_amount':55000,'deposit_amount':55000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الشميسي',
    'sa_area_sqm':90,'sa_condition':'good','sa_year_built':2014,
    'description':'محل تجاري يُصلح للبيع بالتجزئة والمطاعم.'})
prop12 = prop({'name':'مستودع الرياض الصناعي – ٥','property_type':'commercial','sa_property_subtype':'warehouse',
    'owner_partner_id':owner4.id,'rent_amount':60000,'deposit_amount':60000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'المدينة الصناعية الثانية',
    'sa_area_sqm':800,'sa_condition':'good','sa_year_built':2016,
    'description':'مستودع واسع مناسب للتخزين والتوزيع.'})
prop14 = prop({'name':'محل العليا التجاري – ١٢','property_type':'commercial','sa_property_subtype':'shop',
    'owner_partner_id':owner5.id,'rent_amount':65000,'deposit_amount':65000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_area_sqm':110,'sa_condition':'good','sa_year_built':2019,
    'description':'محل تجاري مجهز في قلب منطقة العليا، مثالي للمطاعم أو البيع بالتجزئة.'})

# More Villas
prop15 = prop({'name':'فيلا الياسمين ٧','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner6.id,'rent_amount':90000,'deposit_amount':90000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الياسمين',
    'sa_street':'شارع الأمير عبدالعزيز','sa_building_no':'7',
    'sa_area_sqm':480,'sa_rooms':5,'sa_bathrooms':4,'sa_parking':2,
    'sa_pool':False,'sa_garden':True,'sa_furnished':'unfurnished','sa_condition':'excellent',
    'sa_year_built':2019,'sa_deed_number':'و-٢٠١٩-رض-٠٠٢٣٤٥',
    'description':'فيلا عائلية حديثة في حي الياسمين مع حديقة خاصة ومواقف خاصة.'})
prop16 = prop({'name':'فيلا الشاطئ ٤','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner7.id,'rent_amount':105000,'deposit_amount':105000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي الشاطئ',
    'sa_street':'طريق الكورنيش','sa_building_no':'4',
    'sa_area_sqm':550,'sa_rooms':6,'sa_bathrooms':5,'sa_parking':3,
    'sa_pool':True,'sa_garden':True,'sa_furnished':'semi','sa_condition':'excellent',
    'sa_year_built':2021,'sa_deed_number':'ج-٢٠٢١-جد-٠٠١١١١',
    'description':'فيلا فاخرة بالقرب من كورنيش جدة، إطلالة على البحر من الطابق العلوي.'})
prop17 = prop({'name':'فيلا الفردوس ٩','property_type':'residential','sa_property_subtype':'villa',
    'owner_partner_id':owner10.id,'rent_amount':78000,'deposit_amount':78000,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي الفردوس',
    'sa_area_sqm':420,'sa_rooms':5,'sa_bathrooms':4,'sa_parking':2,
    'sa_pool':False,'sa_garden':True,'sa_furnished':'unfurnished','sa_condition':'good',
    'sa_year_built':2016,'description':'فيلا واسعة في حي الفردوس بالدمام، قريبة من الخدمات والمدارس.'})

# More Apartments — Riyadh
prop18 = prop({'name':'شقة العقيق – ٥ج','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner6.id,'rent_amount':52000,'deposit_amount':26000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العقيق',
    'sa_floor_number':5,'sa_total_floors':12,'sa_area_sqm':170,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'semi','sa_condition':'excellent','sa_year_built':2020,
    'description':'شقة فسيحة في برج حديث بحي العقيق، مجهزة جزئياً وجاهزة للسكن.'})
prop19 = prop({'name':'شقة الورود – ٨أ','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner11.id,'rent_amount':40000,'deposit_amount':20000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي الورود',
    'sa_floor_number':8,'sa_total_floors':14,'sa_area_sqm':145,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','sa_year_built':2017,
    'description':'شقة في برج الورود، قريبة من طريق الملك فهد وسهلة الوصول.'})
prop20 = prop({'name':'شقة النخيل – ٢د','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner12.id,'rent_amount':36000,'deposit_amount':18000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي النخيل',
    'sa_floor_number':2,'sa_total_floors':8,'sa_area_sqm':125,'sa_rooms':2,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','sa_year_built':2016,
    'description':'شقة مريحة في حي النخيل، مناسبة للعائلات الصغيرة والأفراد.'})

# More Apartments — Jeddah
prop21 = prop({'name':'شقة الأندلس – ١١ب','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner9.id,'rent_amount':50000,'deposit_amount':25000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي الأندلس',
    'sa_floor_number':11,'sa_total_floors':18,'sa_area_sqm':155,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'excellent','sa_year_built':2022,
    'description':'شقة في برج الأندلس الحديث بجدة، إطلالة على المدينة.'})
prop22 = prop({'name':'شقة الصفا – ٦ه','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner7.id,'rent_amount':44000,'deposit_amount':22000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي الصفا',
    'sa_floor_number':6,'sa_total_floors':10,'sa_area_sqm':135,'sa_rooms':3,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'semi','sa_condition':'good','sa_year_built':2018,
    'description':'شقة نظيفة ومجهزة جزئياً في حي الصفا، قريبة من المراكز التجارية.'})

# More Apartments — Dammam
prop23 = prop({'name':'شقة الزهراء – ٣ب','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner10.id,'rent_amount':33000,'deposit_amount':16500,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي الزهراء',
    'sa_floor_number':3,'sa_total_floors':6,'sa_area_sqm':115,'sa_rooms':2,'sa_bathrooms':2,
    'sa_elevator':True,'sa_furnished':'unfurnished','sa_condition':'good','sa_year_built':2015,
    'description':'شقة اقتصادية في حي الزهراء، مناسبة للأفراد والعائلات ذات الميزانية المحدودة.'})

# More Offices
prop24 = prop({'name':'مكتب الأعمال الذكية – ١٢و','property_type':'commercial','sa_property_subtype':'office',
    'owner_partner_id':owner11.id,'rent_amount':95000,'deposit_amount':47500,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_street':'طريق الملك عبدالعزيز','sa_floor_number':12,'sa_total_floors':20,
    'sa_area_sqm':230,'sa_elevator':True,'sa_furnished':'fully','sa_condition':'excellent',
    'sa_year_built':2023,'description':'مكتب تنفيذي مجهز بالكامل في مجمع الأعمال الذكية.'})
prop25 = prop({'name':'مكتب النور التجاري – ٤ب','property_type':'commercial','sa_property_subtype':'office',
    'owner_partner_id':owner9.id,'rent_amount':72000,'deposit_amount':36000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي النور',
    'sa_floor_number':4,'sa_area_sqm':180,'sa_elevator':True,
    'sa_furnished':'semi','sa_condition':'good','sa_year_built':2019,
    'description':'مكتب في موقع مركزي بجدة مع مواقف خاصة.'})
prop26 = prop({'name':'مكتب الهوفوف الإداري – ٢أ','property_type':'commercial','sa_property_subtype':'office',
    'owner_partner_id':owner10.id,'rent_amount':68000,'deposit_amount':34000,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'حي العقربية',
    'sa_floor_number':2,'sa_area_sqm':165,'sa_elevator':True,
    'sa_furnished':'semi','sa_condition':'good','sa_year_built':2017,
    'description':'مكتب إداري متكامل في المنطقة الشرقية، قريب من الميناء.'})

# More Warehouses
prop27 = prop({'name':'مستودع جدة الصناعي – ١٢','property_type':'commercial','sa_property_subtype':'warehouse',
    'owner_partner_id':owner9.id,'rent_amount':75000,'deposit_amount':75000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'المنطقة الصناعية',
    'sa_area_sqm':1200,'sa_condition':'good','sa_year_built':2018,
    'description':'مستودع صناعي ضخم بارتفاع ١٢ متراً مناسب للتخزين الثقيل والتوزيع.'})
prop28 = prop({'name':'مستودع الدمام اللوجستي – ٣','property_type':'commercial','sa_property_subtype':'warehouse',
    'owner_partner_id':owner10.id,'rent_amount':55000,'deposit_amount':55000,
    'sa_region_id':r_dammam.id,'sa_city_id':c_dammam.id,'sa_district':'المدينة الصناعية',
    'sa_area_sqm':700,'sa_condition':'good','sa_year_built':2015,
    'description':'مستودع لوجستي قرب ميناء الدمام، مزود بمنصات تحميل وبوابات أمنية.'})

# More Shops / Retail
prop29 = prop({'name':'محل جدة التجاري – ٨','property_type':'commercial','sa_property_subtype':'shop',
    'owner_partner_id':owner9.id,'rent_amount':58000,'deposit_amount':58000,
    'sa_region_id':r_jeddah.id,'sa_city_id':c_jeddah.id,'sa_district':'حي البلد',
    'sa_area_sqm':100,'sa_condition':'good','sa_year_built':2013,
    'description':'محل تجاري في قلب حي البلد التاريخي بجدة، حركة مشاة عالية.'})
prop30 = prop({'name':'صالة عرض الرياض – ١','property_type':'commercial','sa_property_subtype':'shop',
    'owner_partner_id':owner12.id,'rent_amount':88000,'deposit_amount':88000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_area_sqm':200,'sa_condition':'excellent','sa_year_built':2021,
    'description':'صالة عرض واجهة مزدوجة في شارع العليا التجاري، مناسبة للأثاث والسيارات.'})

# Studio / special units
prop31 = prop({'name':'استوديو النخبة – ٩ج','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner11.id,'rent_amount':28000,'deposit_amount':14000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي النزهة',
    'sa_floor_number':9,'sa_total_floors':15,'sa_area_sqm':65,'sa_rooms':1,'sa_bathrooms':1,
    'sa_elevator':True,'sa_furnished':'fully','sa_condition':'excellent','sa_year_built':2023,
    'description':'استوديو مؤثث بالكامل مناسب للأفراد، يشمل الإنترنت والمرافق.'})
prop32 = prop({'name':'شقة بنتهاوس القمة – ٢٠أ','property_type':'residential','sa_property_subtype':'apartment',
    'owner_partner_id':owner12.id,'rent_amount':130000,'deposit_amount':130000,
    'sa_region_id':r_riyadh.id,'sa_city_id':c_riyadh.id,'sa_district':'حي العليا',
    'sa_floor_number':20,'sa_total_floors':20,'sa_area_sqm':350,'sa_rooms':4,'sa_bathrooms':3,
    'sa_elevator':True,'sa_furnished':'fully','sa_condition':'excellent','sa_year_built':2022,
    'description':'بنتهاوس فاخر في الطابق العلوي مع تراس خاص وإطلالة ٣٦٠ درجة على الرياض.'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 6 — Tenancies (24)
# ══════════════════════════════════════════════════════════════════════════════
print("6/16  عقود الإيجار…")

def tenancy(vals, confirm=True, start=True):
    t = env['property.tenancy'].create({'currency_id': SAR.id, **vals})
    if confirm: t.action_confirm()
    if start:   t.action_start()
    return t

# ع١ — خالد في فيلا الروضة — قيد التشغيل ٦ أشهر، ربع سنوي
t1 = tenancy({'property_id':prop1.id,'partner_id':tenant1.id,
    'start_date':str(ago(180)),'end_date':str(ahead(185)),'duration':12,'interval_type':'months',
    'rent_amount':80000,'deposit_amount':80000,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker1.id,'tenant_id_type':'national_id','tenant_national_id':'1098765432',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع٢ — عمر في شقة العليا — ٣ أشهر، ربع سنوي
t2 = tenancy({'property_id':prop4.id,'partner_id':tenant2.id,
    'start_date':str(ago(90)),'end_date':str(ahead(275)),'duration':12,'interval_type':'months',
    'rent_amount':45000,'deposit_amount':22500,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker2.id,'tenant_id_type':'national_id','tenant_national_id':'1034512678',
    'sublease_allowed':False})

# ع٣ — نورة في شقة الملقا — دفعة متأخرة، شهري
t3 = tenancy({'property_id':prop5.id,'partner_id':tenant3.id,
    'start_date':str(ago(120)),'end_date':str(ahead(245)),'duration':12,'interval_type':'months',
    'rent_amount':48000,'deposit_amount':24000,'payment_method':'mada',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly','ejar_payment_schedule':'monthly',
    'tenant_id_type':'national_id','tenant_national_id':'1067891234','sublease_allowed':False})

# ع٤ — عائشة في شقة الحمراء — تنتهي خلال ٢٨ يومًا، سنوي
t4 = tenancy({'property_id':prop6.id,'partner_id':tenant4.id,
    'start_date':str(ago(337)),'end_date':str(ahead(28)),'duration':12,'interval_type':'months',
    'rent_amount':42000,'deposit_amount':21000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'annual','ejar_payment_schedule':'annual',
    'sa_broker_id':broker3.id,'tenant_id_type':'iqama','tenant_national_id':'2123456789',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع٥ — أحمد في مكتب بيزنس باي — تجاري، منتهي
t5 = tenancy({'property_id':prop9.id,'partner_id':tenant5.id,
    'start_date':str(ago(365)),'end_date':str(today),'duration':12,'interval_type':'months',
    'rent_amount':120000,'deposit_amount':60000,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker1.id,'tenant_id_type':'national_id','tenant_national_id':'1055443322',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع٦ — سارة في شقة المرجان — شهري
t6 = tenancy({'property_id':prop7.id,'partner_id':tenant6.id,
    'start_date':str(ago(60)),'end_date':str(ahead(305)),'duration':12,'interval_type':'months',
    'rent_amount':38000,'deposit_amount':19000,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly','ejar_payment_schedule':'monthly',
    'tenant_id_type':'national_id','tenant_national_id':'1066778899','sublease_allowed':False})

# ع٧ — محمد في المحل التجاري — نصف سنوي
t7 = tenancy({'property_id':prop11.id,'partner_id':tenant7.id,
    'start_date':str(ago(240)),'end_date':str(ahead(125)),'duration':12,'interval_type':'months',
    'rent_amount':55000,'deposit_amount':55000,'payment_method':'cheque',
    'sa_contract_type':'commercial','sa_payment_schedule':'semi_annual','ejar_payment_schedule':'semi_annual',
    'sa_broker_id':broker3.id,'tenant_id_type':'national_id','tenant_national_id':'1077889900',
    'sublease_allowed':False})

# ع٨ — ريم في شقة الدانة — مؤكد لم يبدأ بعد
t8 = tenancy({'property_id':prop8.id,'partner_id':tenant8.id,
    'start_date':str(ahead(15)),'end_date':str(ahead(380)),'duration':12,'interval_type':'months',
    'rent_amount':35000,'deposit_amount':17500,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'quarterly',
    'tenant_id_type':'national_id','tenant_national_id':'1088990011'},
    confirm=True, start=False)

# ع٩ — فيلا النرجس — مسودة
t9 = tenancy({'property_id':prop3.id,'partner_id':tenant9.id,
    'start_date':str(ahead(45)),'end_date':str(ahead(410)),'duration':12,'interval_type':'months',
    'rent_amount':110000,'deposit_amount':110000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'semi_annual'},
    confirm=False, start=False)

# ع١٠ — فيلا النسيم — قائم في الدمام
t10 = tenancy({'property_id':prop13.id,'partner_id':tenant11.id,
    'start_date':str(ago(30)),'end_date':str(ahead(335)),'duration':12,'interval_type':'months',
    'rent_amount':72000,'deposit_amount':72000,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly','ejar_payment_schedule':'monthly',
    'tenant_id_type':'national_id','tenant_national_id':'2098765431','sa_broker_id':broker3.id})

# ع١١ — محل العليا — تجاري قائم
t11 = tenancy({'property_id':prop14.id,'partner_id':tenant5.id,
    'start_date':str(ago(10)),'end_date':str(ahead(355)),'duration':12,'interval_type':'months',
    'rent_amount':65000,'deposit_amount':65000,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'tenant_id_type':'national_id','tenant_national_id':'1055443322','sa_broker_id':broker2.id})

# ع١٢ — وليد في شقة العقيق — نشط، شهري
t12 = tenancy({'property_id':prop18.id,'partner_id':tenant12.id,
    'start_date':str(ago(150)),'end_date':str(ahead(215)),'duration':12,'interval_type':'months',
    'rent_amount':52000,'deposit_amount':26000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly','ejar_payment_schedule':'monthly',
    'sa_broker_id':broker4.id,'tenant_id_type':'national_id','tenant_national_id':'1011223344',
    'sublease_allowed':False,'auto_renew':False})

# ع١٣ — منال في شقة الورود — نشط، ربع سنوي
t13 = tenancy({'property_id':prop19.id,'partner_id':tenant13.id,
    'start_date':str(ago(200)),'end_date':str(ahead(165)),'duration':12,'interval_type':'months',
    'rent_amount':40000,'deposit_amount':20000,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker5.id,'tenant_id_type':'national_id','tenant_national_id':'1022334451',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع١٤ — طارق في شقة النخيل — نشط، نصف سنوي
t14 = tenancy({'property_id':prop20.id,'partner_id':tenant14.id,
    'start_date':str(ago(100)),'end_date':str(ahead(265)),'duration':12,'interval_type':'months',
    'rent_amount':36000,'deposit_amount':36000,'payment_method':'cheque',
    'sa_contract_type':'residential','sa_payment_schedule':'semi_annual','ejar_payment_schedule':'semi_annual',
    'tenant_id_type':'national_id','tenant_national_id':'1033445562','sublease_allowed':False})

# ع١٥ — هند في شقة الأندلس — نشط، ربع سنوي، مقيمة
t15 = tenancy({'property_id':prop21.id,'partner_id':tenant15.id,
    'start_date':str(ago(75)),'end_date':str(ahead(290)),'duration':12,'interval_type':'months',
    'rent_amount':50000,'deposit_amount':25000,'payment_method':'mada',
    'sa_contract_type':'residential','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker4.id,'tenant_id_type':'iqama','tenant_national_id':'2234567891',
    'sublease_allowed':False})

# ع١٦ — يوسف في شقة الصفا — نشط، سنوي
t16 = tenancy({'property_id':prop22.id,'partner_id':tenant16.id,
    'start_date':str(ago(270)),'end_date':str(ahead(95)),'duration':12,'interval_type':'months',
    'rent_amount':44000,'deposit_amount':22000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'annual','ejar_payment_schedule':'annual',
    'sa_broker_id':broker6.id,'tenant_id_type':'national_id','tenant_national_id':'1044556671',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع١٧ — أسماء في شقة الزهراء — نشط، شهري
t17 = tenancy({'property_id':prop23.id,'partner_id':tenant17.id,
    'start_date':str(ago(45)),'end_date':str(ahead(320)),'duration':12,'interval_type':'months',
    'rent_amount':33000,'deposit_amount':16500,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly','ejar_payment_schedule':'monthly',
    'tenant_id_type':'national_id','tenant_national_id':'1055667782','sublease_allowed':False})

# ع١٨ — سلطان في مكتب الأعمال الذكية — تجاري نشط، ربع سنوي
t18 = tenancy({'property_id':prop24.id,'partner_id':tenant18.id,
    'start_date':str(ago(160)),'end_date':str(ahead(205)),'duration':12,'interval_type':'months',
    'rent_amount':95000,'deposit_amount':47500,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker1.id,'tenant_id_type':'national_id','tenant_national_id':'1066779901',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

# ع١٩ — شركة الأفق في مكتب النور — تجاري نشط
t19 = tenancy({'property_id':prop25.id,'partner_id':tenant26.id,
    'start_date':str(ago(50)),'end_date':str(ahead(315)),'duration':12,'interval_type':'months',
    'rent_amount':72000,'deposit_amount':36000,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'quarterly','ejar_payment_schedule':'quarterly',
    'sa_broker_id':broker4.id,'sublease_allowed':False})

# ع٢٠ — شركة المتحدة في مستودع جدة — تجاري نشط، نصف سنوي
t20 = tenancy({'property_id':prop27.id,'partner_id':tenant27.id,
    'start_date':str(ago(120)),'end_date':str(ahead(245)),'duration':12,'interval_type':'months',
    'rent_amount':75000,'deposit_amount':75000,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'semi_annual','ejar_payment_schedule':'semi_annual',
    'sa_broker_id':broker1.id,'sublease_allowed':False})

# ع٢١ — رانيا في فيلا الياسمين — مؤكد، لم يبدأ
t21 = tenancy({'property_id':prop15.id,'partner_id':tenant19.id,
    'start_date':str(ahead(20)),'end_date':str(ahead(385)),'duration':12,'interval_type':'months',
    'rent_amount':90000,'deposit_amount':90000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'semi_annual',
    'sa_broker_id':broker5.id,'tenant_id_type':'national_id','tenant_national_id':'1077991122',
    'sublease_allowed':False},
    confirm=True, start=False)

# ع٢٢ — عبدالرحمن في شقة النخبة — مسودة
t22 = tenancy({'property_id':prop31.id,'partner_id':tenant20.id,
    'start_date':str(ahead(30)),'end_date':str(ahead(395)),'duration':12,'interval_type':'months',
    'rent_amount':28000,'deposit_amount':14000,'payment_method':'sadad',
    'sa_contract_type':'residential','sa_payment_schedule':'monthly'},
    confirm=False, start=False)

# ع٢٣ — شركة رؤية في صالة العرض — تجاري نشط، سنوي
t23 = tenancy({'property_id':prop30.id,'partner_id':tenant28.id,
    'start_date':str(ago(20)),'end_date':str(ahead(345)),'duration':12,'interval_type':'months',
    'rent_amount':88000,'deposit_amount':88000,'payment_method':'bank_transfer',
    'sa_contract_type':'commercial','sa_payment_schedule':'annual','ejar_payment_schedule':'annual',
    'sa_broker_id':broker6.id,'sublease_allowed':False})

# ع٢٤ — بندر في فيلا الشاطئ — نشط، نصف سنوي
t24 = tenancy({'property_id':prop16.id,'partner_id':tenant22.id,
    'start_date':str(ago(90)),'end_date':str(ahead(275)),'duration':12,'interval_type':'months',
    'rent_amount':105000,'deposit_amount':105000,'payment_method':'bank_transfer',
    'sa_contract_type':'residential','sa_payment_schedule':'semi_annual','ejar_payment_schedule':'semi_annual',
    'sa_broker_id':broker4.id,'tenant_id_type':'national_id','tenant_national_id':'1099112234',
    'sublease_allowed':False,'auto_renew':True,'renewal_period_months':12,'renewal_rent_increase_pct':0.0})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 7 — Rent Payments
# ══════════════════════════════════════════════════════════════════════════════
print("7/16  دفعات الإيجار…")

def pay(ten, due, amount, state='pending', paid_on=None, method=None, ptype='rent', label=''):
    v = {'tenancy_id':ten.id,'due_date':str(due),'amount':amount,
         'payment_type':ptype,'state':state,'period_label':label}
    if paid_on: v['payment_date']=str(paid_on); v['amount_paid']=amount
    if method:  v['payment_method']=method
    return env['sa.rent.payment'].create(v)

def deposit(ten, on, amount, method='bank_transfer'):
    pay(ten, on, amount, 'paid', on, method, 'deposit', 'وديعة تأمين')

# ع١ — خالد، ربع سنوي
deposit(t1, ago(180), 80000, 'sadad')
pay(t1, ago(180), 20000, 'paid',    ago(178), 'sadad',         label='الربع الأول')
pay(t1, ago(90),  20000, 'paid',    ago(88),  'sadad',         label='الربع الثاني')
pay(t1, ahead(0), 20000, 'pending',                            label='الربع الثالث – مستحق اليوم')
pay(t1, ahead(90),20000, 'pending',                            label='الربع الرابع')

# ع٢ — عمر، ربع سنوي
deposit(t2, ago(90), 22500, 'bank_transfer')
pay(t2, ago(90),    11250, 'paid',    ago(88), 'bank_transfer', label='الربع الأول')
pay(t2, ahead(0),   11250, 'pending',                           label='الربع الثاني')
pay(t2, ahead(90),  11250, 'pending',                           label='الربع الثالث')
pay(t2, ahead(180), 11250, 'pending',                           label='الربع الرابع')

# ع٣ — نورة، شهري — الشهر الرابع متأخر
deposit(t3, ago(120), 24000, 'mada')
monthly3 = round(48000/12, 2)
for due, st, pd, lbl in [
    (ago(120),'paid',   ago(118),'الشهر الأول'),
    (ago(90), 'paid',   ago(88), 'الشهر الثاني'),
    (ago(60), 'paid',   ago(58), 'الشهر الثالث'),
    (ago(30), 'overdue',None,    'الشهر الرابع – متأخر'),
    (today,   'pending',None,    'الشهر الخامس'),
]:
    pay(t3, due, monthly3, st, pd, 'mada' if pd else None, label=lbl)

# ع٤ — عائشة، سنوي مدفوع بالكامل
deposit(t4, ago(337), 21000, 'bank_transfer')
pay(t4, ago(337), 42000, 'paid', ago(335), 'bank_transfer', label='الإيجار السنوي ٢٠٢٥–٢٠٢٦')

# ع٥ — أحمد، ربع سنوي — جميع أرباعه مدفوعة
deposit(t5, ago(365), 60000, 'bank_transfer')
for due, lbl in [(ago(365),'الربع الأول'),(ago(275),'الربع الثاني'),
                 (ago(185),'الربع الثالث'),(ago(95),'الربع الرابع')]:
    pay(t5, due, 30000, 'paid', due+datetime.timedelta(2), 'bank_transfer', label=lbl)

# ع٦ — سارة، شهري
deposit(t6, ago(60), 19000, 'sadad')
monthly6 = round(38000/12, 2)
for due, st, pd, lbl in [
    (ago(60),'paid',  ago(58),'الشهر الأول'),
    (ago(30),'paid',  ago(28),'الشهر الثاني'),
    (today,  'pending',None,  'الشهر الثالث'),
]:
    pay(t6, due, monthly6, st, pd, 'sadad' if pd else None, label=lbl)

# ع٧ — محمد، نصف سنوي
deposit(t7, ago(240), 55000, 'cheque')
pay(t7, ago(240), 27500, 'paid',    ago(238), 'cheque', label='النصف الأول')
pay(t7, ahead(125),   27500, 'pending',                  label='النصف الثاني')

# ع٨ — ريم، وديعة فقط
deposit(t8, today, 17500, 'bank_transfer')

# ع١٢ — وليد، شهري — ٤ أشهر مدفوعة، الشهر الخامس متأخر
deposit(t12, ago(150), 26000, 'bank_transfer')
monthly12 = round(52000/12, 2)
for due, st, pd, lbl in [
    (ago(150),'paid',   ago(148),'الشهر الأول'),
    (ago(120),'paid',   ago(118),'الشهر الثاني'),
    (ago(90), 'paid',   ago(88), 'الشهر الثالث'),
    (ago(60), 'paid',   ago(58), 'الشهر الرابع'),
    (ago(30), 'overdue',None,    'الشهر الخامس – متأخر'),
    (today,   'pending',None,    'الشهر السادس'),
]:
    pay(t12, due, monthly12, st, pd, 'bank_transfer' if pd else None, label=lbl)

# ع١٣ — منال، ربع سنوي
deposit(t13, ago(200), 20000, 'sadad')
pay(t13, ago(200), 10000, 'paid',    ago(198), 'sadad',  label='الربع الأول')
pay(t13, ago(110), 10000, 'paid',    ago(108), 'sadad',  label='الربع الثاني')
pay(t13, ahead(0), 10000, 'pending',                     label='الربع الثالث')
pay(t13, ahead(90),10000, 'pending',                     label='الربع الرابع')

# ع١٤ — طارق، نصف سنوي — النصف الأول مدفوع
deposit(t14, ago(100), 36000, 'cheque')
pay(t14, ago(100), 18000, 'paid',    ago(98),  'cheque', label='النصف الأول')
pay(t14, ahead(82),18000, 'pending',                     label='النصف الثاني')

# ع١٥ — هند، ربع سنوي
deposit(t15, ago(75), 25000, 'mada')
pay(t15, ago(75),   12500, 'paid',    ago(73),  'mada',  label='الربع الأول')
pay(t15, ahead(15), 12500, 'pending',                    label='الربع الثاني')
pay(t15, ahead(105),12500, 'pending',                    label='الربع الثالث')
pay(t15, ahead(195),12500, 'pending',                    label='الربع الرابع')

# ع١٦ — يوسف، سنوي — مدفوع بالكامل
deposit(t16, ago(270), 22000, 'bank_transfer')
pay(t16, ago(270), 44000, 'paid', ago(268), 'bank_transfer', label='الإيجار السنوي')

# ع١٧ — أسماء، شهري — شهرين مدفوع
deposit(t17, ago(45), 16500, 'sadad')
monthly17 = round(33000/12, 2)
for due, st, pd, lbl in [
    (ago(45),'paid',  ago(43),'الشهر الأول'),
    (ago(15),'paid',  ago(13),'الشهر الثاني'),
    (today,  'pending',None,  'الشهر الثالث'),
]:
    pay(t17, due, monthly17, st, pd, 'sadad' if pd else None, label=lbl)

# ع١٨ — سلطان، ربع سنوي تجاري — قسطان مدفوعان
deposit(t18, ago(160), 47500, 'bank_transfer')
pay(t18, ago(160), 23750, 'paid',    ago(158), 'bank_transfer', label='الربع الأول')
pay(t18, ago(70),  23750, 'paid',    ago(68),  'bank_transfer', label='الربع الثاني')
pay(t18, ahead(20),23750, 'pending',                            label='الربع الثالث')
pay(t18, ahead(110),23750,'pending',                            label='الربع الرابع')

# ع١٩ — شركة الأفق، ربع سنوي — قسط أول مدفوع
deposit(t19, ago(50), 36000, 'bank_transfer')
pay(t19, ago(50),   18000, 'paid',    ago(48),  'bank_transfer', label='الربع الأول')
pay(t19, ahead(40), 18000, 'pending',                            label='الربع الثاني')
pay(t19, ahead(130),18000, 'pending',                            label='الربع الثالث')
pay(t19, ahead(220),18000, 'pending',                            label='الربع الرابع')

# ع٢٠ — شركة المتحدة، نصف سنوي — النصف الأول مدفوع
deposit(t20, ago(120), 75000, 'bank_transfer')
pay(t20, ago(120), 37500, 'paid',    ago(118), 'bank_transfer', label='النصف الأول')
pay(t20, ahead(125),37500, 'pending',                           label='النصف الثاني')

# ع٢١ — رانيا، وديعة فقط (عقد مؤكد لم يبدأ)
deposit(t21, today, 90000, 'bank_transfer')

# ع٢٤ — بندر، نصف سنوي — النصف الأول مدفوع
deposit(t24, ago(90), 105000, 'bank_transfer')
pay(t24, ago(90),   52500, 'paid',    ago(88),  'bank_transfer', label='النصف الأول')
pay(t24, ahead(185),52500, 'pending',                            label='النصف الثاني')

# ع٢٣ — شركة رؤية، سنوي — مدفوع بالكامل
deposit(t23, ago(20), 88000, 'bank_transfer')
pay(t23, ago(20), 88000, 'paid', ago(18), 'bank_transfer', label='الإيجار السنوي')

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 8 — Inspections (12)
# ══════════════════════════════════════════════════════════════════════════════
print("8/16  المعاينات…")

def inspection(vals, complete=False, sign=False):
    ins = env['sa.property.inspection'].create(vals)
    if complete or sign: ins.action_complete()
    if sign: ins.action_sign()
    return ins

inspection({'property_id':prop1.id,'tenancy_id':t1.id,'inspection_type':'move_in',
    'inspection_date':str(ago(180)),'general_condition':'excellent',
    'general_notes':'العقار في حالة ممتازة. جميع المرافق تعمل بكفاءة. الحديقة والمسبح نظيفان.',
    'line_ids':[(0,0,{'room':'living_room','item':'التكييف المركزي','condition':'good','notes':'٣ وحدات تعمل بكفاءة'}),
                (0,0,{'room':'kitchen',    'item':'خزائن المطبخ والرخام','condition':'good'}),
                (0,0,{'room':'bathroom',   'item':'تجهيزات السباكة','condition':'good','notes':'لا يوجد تسرب'}),
                (0,0,{'room':'exterior',   'item':'الحديقة والمسبح','condition':'good','notes':'صيانة جيدة'})]},
    complete=True, sign=True)

inspection({'property_id':prop6.id,'tenancy_id':t4.id,'inspection_type':'move_in',
    'inspection_date':str(ago(337)),'general_condition':'good',
    'general_notes':'الشقة في حالة جيدة مع بعض التآكل الطفيف على الجدران.',
    'line_ids':[(0,0,{'room':'living_room','item':'الجدران والدهان','condition':'minor_wear','damage_cost':800.0,'notes':'بعض الخدوش الطفيفة'}),
                (0,0,{'room':'kitchen',    'item':'الأجهزة المنزلية','condition':'good'})]},
    complete=True, sign=True)

inspection({'property_id':prop6.id,'tenancy_id':t4.id,'inspection_type':'interim',
    'inspection_date':str(today),'general_condition':'fair',
    'general_notes':'معاينة مرحلية قبيل انتهاء العقد. الجدران تحتاج إعادة طلاء.',
    'line_ids':[(0,0,{'room':'living_room','item':'الجدران','condition':'damaged','damage_cost':1500.0,'notes':'إعادة طلاء كاملة'}),
                (0,0,{'room':'bathroom',   'item':'البلاط','condition':'minor_wear','damage_cost':400.0})]})

inspection({'property_id':prop4.id,'tenancy_id':t2.id,'inspection_type':'move_in',
    'inspection_date':str(ago(90)),'general_condition':'good',
    'general_notes':'الشقة نظيفة وجاهزة للسكن.',
    'line_ids':[(0,0,{'room':'kitchen','item':'المطبخ والأجهزة','condition':'good','notes':'جهاز الغسيل جديد'})]},
    complete=True)

inspection({'property_id':prop9.id,'tenancy_id':t5.id,'inspection_type':'move_in',
    'inspection_date':str(ago(365)),'general_condition':'excellent',
    'general_notes':'المكتب مجهز بالكامل وجاهز للعمل.',
    'line_ids':[(0,0,{'room':'other','item':'شبكة الإنترنت والاتصالات','condition':'good','notes':'١ جيجابت فايبر'})]},
    complete=True, sign=True)

inspection({'property_id':prop18.id,'tenancy_id':t12.id,'inspection_type':'move_in',
    'inspection_date':str(ago(150)),'general_condition':'excellent',
    'general_notes':'الشقة في حالة ممتازة. جميع الأجهزة والتجهيزات تعمل بكفاءة.',
    'line_ids':[(0,0,{'room':'living_room','item':'التكييف والإضاءة','condition':'good'}),
                (0,0,{'room':'kitchen',    'item':'الأجهزة المنزلية','condition':'good','notes':'غسالة وثلاجة جديدة'}),
                (0,0,{'room':'bathroom',   'item':'تجهيزات الحمام','condition':'good'})]},
    complete=True, sign=True)

inspection({'property_id':prop15.id,'tenancy_id':t21.id,'inspection_type':'move_in',
    'inspection_date':str(today),'general_condition':'excellent',
    'general_notes':'الفيلا في حالة ممتازة، جاهزة للسكن. تم التسليم للمستأجرة مع توثيق كامل.',
    'line_ids':[(0,0,{'room':'living_room','item':'الأثاث والتجهيزات','condition':'good','notes':'الأثاث الموجود مُكشوف بالعقد'}),
                (0,0,{'room':'exterior',   'item':'الحديقة الخلفية','condition':'good'}),
                (0,0,{'room':'other',      'item':'مواقف السيارات والبوابة','condition':'good'})]},
    complete=True)

inspection({'property_id':prop24.id,'tenancy_id':t18.id,'inspection_type':'move_in',
    'inspection_date':str(ago(160)),'general_condition':'excellent',
    'general_notes':'المكتب مجهز بالكامل ومناسب للاستخدام الفوري.',
    'line_ids':[(0,0,{'room':'other','item':'شبكة الاتصالات وسرعة الإنترنت','condition':'good','notes':'ألياف بصرية ٥٠٠ ميجابت'}),
                (0,0,{'room':'other','item':'نظام التحكم في الوصول','condition':'good'})]},
    complete=True, sign=True)

inspection({'property_id':prop22.id,'tenancy_id':t16.id,'inspection_type':'move_in',
    'inspection_date':str(ago(270)),'general_condition':'good',
    'general_notes':'الشقة نظيفة ومرتبة، بعض التآكل الطفيف على بعض الأسطح.',
    'line_ids':[(0,0,{'room':'living_room','item':'الجدران والطلاء','condition':'minor_wear','damage_cost':600.0,'notes':'بعض الخدوش الطفيفة'}),
                (0,0,{'room':'kitchen',    'item':'الأجهزة المنزلية','condition':'good'}),
                (0,0,{'room':'bathroom',   'item':'تجهيزات الحمام','condition':'good'})]},
    complete=True, sign=True)

inspection({'property_id':prop22.id,'tenancy_id':t16.id,'inspection_type':'interim',
    'inspection_date':str(ago(90)),'general_condition':'good',
    'general_notes':'معاينة دورية. لا توجد أضرار جوهرية.',
    'line_ids':[(0,0,{'room':'living_room','item':'الجدران','condition':'good'}),
                (0,0,{'room':'kitchen',    'item':'الأجهزة','condition':'good','notes':'جميع الأجهزة تعمل بصورة طبيعية'})]},
    complete=True)

inspection({'property_id':prop27.id,'tenancy_id':t20.id,'inspection_type':'move_in',
    'inspection_date':str(ago(120)),'general_condition':'good',
    'general_notes':'المستودع نظيف وجاهز للاستخدام. تم التحقق من السقف والبوابات ومنصات التحميل.',
    'line_ids':[(0,0,{'room':'other','item':'البوابات الكهربائية','condition':'good'}),
                (0,0,{'room':'other','item':'منصات التحميل والشاحنات','condition':'good'}),
                (0,0,{'room':'other','item':'نظام الإضاءة الصناعي','condition':'good'})]},
    complete=True, sign=True)

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 9 — Maintenance Requests & Work Orders (20 + 10)
# ══════════════════════════════════════════════════════════════════════════════
print("9/16  الصيانة…")

def mreq(vals, approve=False, schedule=False, start=False, done=False):
    r = env['sa.maintenance.request'].create(vals)
    if approve or schedule or start or done: r.action_approve()
    if schedule or start or done: r.action_schedule()
    if start or done: r.action_start()
    if done: r.action_done()
    return r

# ص١ — عطل تكييف: قيد التنفيذ
req1 = mreq({'property_id':prop1.id,'tenancy_id':t1.id,'category':'ac','priority':'2',
    'description':'وحدة التكييف في غرفة النوم الرئيسية لا تبرد. ترتفع الحرارة عن ٢٨° رغم ضبط الثيرموستات.',
    'request_date':str(ago(5)),'supplier_partner_id':tech2.id,'scheduled_date':str(dt(ahead(1),10)),
    'estimated_duration':3.0,'labor_cost':300,'materials_cost':150,'cost_bearer':'owner',
    'notes':'يُرجَّح تسرب غاز التبريد.'}, approve=True, schedule=True, start=True)

# ص٢ — تسرب سباكة: معتمد
req2 = mreq({'property_id':prop4.id,'tenancy_id':t2.id,'category':'plumbing','priority':'3',
    'description':'تسرب مياه أسفل حوض المطبخ. المياه تتقطر داخل الخزانة.',
    'request_date':str(ago(2)),'supplier_partner_id':tech1.id,'scheduled_date':str(dt(today,9)),
    'estimated_duration':2.0,'labor_cost':200,'materials_cost':80,'cost_bearer':'owner'},
    approve=True)

# ص٣ — كهرباء: منجزة
req3 = mreq({'property_id':prop9.id,'tenancy_id':t5.id,'category':'electrical','priority':'2',
    'description':'وميض في ثلاثة مصابيح سقف. يُشتبه في ارتفاع التيار الكهربائي.',
    'request_date':str(ago(7)),'supplier_partner_id':tech2.id,'scheduled_date':str(dt(ago(1),14)),
    'actual_duration':2.5,'labor_cost':350,'materials_cost':220,'cost_bearer':'tenant',
    'notes':'تم استبدال المصابيح الثلاثة. المشكلة حُلّت.'},
    approve=True, schedule=True, start=True, done=True)

# ص٤ — قفل الباب: جديد
req4 = mreq({'property_id':prop5.id,'tenancy_id':t3.id,'category':'carpentry','priority':'3',
    'description':'قفل الباب الأمامي معطل. المستأجرة تدخل من الباب الخلفي.',
    'request_date':str(today),'estimated_duration':1.0,'labor_cost':150,'materials_cost':200,'cost_bearer':'owner'})

# ص٥ — طلاء: معتمد
req5 = mreq({'property_id':prop6.id,'tenancy_id':t4.id,'category':'painting','priority':'1',
    'description':'إعادة طلاء جدران غرفة المعيشة قبيل انتهاء العقد.',
    'request_date':str(ago(1)),'supplier_partner_id':tech3.id,'scheduled_date':str(dt(ahead(7),8)),
    'estimated_duration':8.0,'labor_cost':600,'materials_cost':400,'cost_bearer':'tenant'},
    approve=True)

# ص٦ — تشقق بلاط حمام: جديد
req6 = mreq({'property_id':prop7.id,'tenancy_id':t6.id,'category':'other','priority':'1',
    'description':'تلف وتشقق في بلاط حمام غرفة النوم الرئيسية.',
    'request_date':str(ago(1)),'estimated_duration':4.0,'labor_cost':400,'materials_cost':500,'cost_bearer':'owner'})

# ص٧ — خزان مياه: مجدول
req7 = mreq({'property_id':prop2.id,'category':'plumbing','priority':'2',
    'description':'الخزان العلوي يُصدر أصواتًا غريبة وضغط الماء ضعيف في الطابق الثاني.',
    'request_date':str(ago(3)),'supplier_partner_id':tech1.id,'scheduled_date':str(dt(ahead(2),11)),
    'estimated_duration':3.0,'labor_cost':250,'materials_cost':300,'cost_bearer':'owner'},
    approve=True, schedule=True)

# ص٨ — حديقة ومسبح: منجزة
req8 = mreq({'property_id':prop1.id,'tenancy_id':t1.id,'category':'other','priority':'0',
    'description':'الصيانة الدورية للحديقة والمسبح.',
    'request_date':str(ago(14)),'supplier_partner_id':tech3.id,'scheduled_date':str(dt(ago(13),8)),
    'actual_duration':6.0,'labor_cost':400,'materials_cost':150,'cost_bearer':'owner',
    'notes':'تمت الصيانة بنجاح. المسبح جاهز للاستخدام.'},
    approve=True, schedule=True, start=True, done=True)

# ص٩ — انقطاع كهربائي تجاري: مجدول
req9 = mreq({'property_id':prop10.id,'category':'electrical','priority':'3',
    'description':'انقطاع التيار في المكتب مع شرر عند اللوحة الرئيسية.',
    'request_date':str(today),'supplier_partner_id':tech4.id,'scheduled_date':str(dt(ahead(2),10)),
    'estimated_duration':2.5,'labor_cost':300,'materials_cost':250,'cost_bearer':'owner'},
    approve=True, schedule=True)

# ص١٠ — تسرب محل تجاري: معتمد
req10 = mreq({'property_id':prop11.id,'category':'plumbing','priority':'2',
    'description':'تسرب في أنابيب المياه. يحتاج استبدالاً سريعاً لمنع تلف المخزون.',
    'request_date':str(ago(1)),'supplier_partner_id':tech5.id,'scheduled_date':str(dt(ahead(3),12)),
    'estimated_duration':4.0,'labor_cost':280,'materials_cost':320,'cost_bearer':'owner'},
    approve=True)

# Work Orders
def wo(vals, schedule=False, start=False, done=False):
    w = env['sa.maintenance.work_order'].create(vals)
    if schedule or start or done: w.action_schedule()
    if start or done: w.action_start()
    if done: w.action_done()
    return w

wo({'request_id':req1.id,'technician_id':tech2.id,'scheduled_date':str(dt(ahead(1),10)),
    'description':'فحص وحدات التكييف واختبار ضغط غاز التبريد وإصلاح التسرب.',
    'duration_planned':3.0,'labor_cost':300,'materials_cost':150}, schedule=True)
wo({'request_id':req3.id,'technician_id':tech2.id,'scheduled_date':str(dt(ago(1),14)),
    'description':'استبدال ثلاثة مصابيح سقف معيبة في منطقة الاستقبال.',
    'duration_planned':2.5,'duration_actual':2.5,'labor_cost':350,'materials_cost':220},
    schedule=True, start=True, done=True)
wo({'request_id':req7.id,'technician_id':tech1.id,'scheduled_date':str(dt(ahead(2),11)),
    'description':'فحص خزان المياه وإصلاح مشكلة الضغط أو الصمامات.',
    'duration_planned':3.0,'labor_cost':250,'materials_cost':300}, schedule=True)
wo({'request_id':req8.id,'technician_id':tech3.id,'scheduled_date':str(dt(ago(14),8)),
    'description':'تنظيف المسبح وقص العشب وتشذيب الأشجار.',
    'duration_planned':6.0,'duration_actual':6.0,'labor_cost':400,'materials_cost':150},
    schedule=True, start=True, done=True)
wo({'request_id':req9.id,'technician_id':tech4.id,'scheduled_date':str(dt(ahead(2),10)),
    'description':'فحص اللوحة الكهربائية وتغيير الفيوزات والتحقق من التوصيلات.',
    'duration_planned':2.5,'labor_cost':300,'materials_cost':250}, schedule=True)

# ص١١ — تسرب سقف: فيلا الياسمين — مجدول
req11 = mreq({'property_id':prop15.id,'category':'plumbing','priority':'3',
    'description':'تسرب مياه أمطار من سطح الفيلا في منطقة الممر الداخلي بعد الهطول الأخير.',
    'request_date':str(ago(3)),'supplier_partner_id':tech5.id,'scheduled_date':str(dt(ahead(3),9)),
    'estimated_duration':4.0,'labor_cost':350,'materials_cost':400,'cost_bearer':'owner'},
    approve=True, schedule=True)

# ص١٢ — عطل مصعد: برج العليا — قيد التنفيذ
req12 = mreq({'property_id':prop18.id,'tenancy_id':t12.id,'category':'electrical','priority':'3',
    'description':'المصعد يتوقف فجأة بين الطوابق. تعطّل ثلاث مرات خلال الأسبوع الماضي.',
    'request_date':str(ago(4)),'supplier_partner_id':tech6.id,'scheduled_date':str(dt(today,8)),
    'estimated_duration':5.0,'labor_cost':500,'materials_cost':350,'cost_bearer':'owner',
    'notes':'يُشتبه في تلف متحكم الباب.'}, approve=True, schedule=True, start=True)

# ص١٣ — تلف أرضيات: شقة الأندلس — جديد
req13 = mreq({'property_id':prop21.id,'tenancy_id':t15.id,'category':'carpentry','priority':'1',
    'description':'تشقق في بلاط الأرضية بجانب نافذة الصالة. يحتاج استبدال ثلاث بلاطات.',
    'request_date':str(today),'estimated_duration':3.0,'labor_cost':300,'materials_cost':250,'cost_bearer':'tenant'})

# ص١٤ — صيانة دورية تكييف: مكتب الأعمال الذكية — مكتملة
req14 = mreq({'property_id':prop24.id,'tenancy_id':t18.id,'category':'ac','priority':'0',
    'description':'الصيانة الربع سنوية لأجهزة التكييف المركزي في المكتب.',
    'request_date':str(ago(20)),'supplier_partner_id':tech8.id,'scheduled_date':str(dt(ago(18),9)),
    'actual_duration':4.0,'labor_cost':600,'materials_cost':200,'cost_bearer':'owner',
    'notes':'تم تنظيف جميع الفلاتر وإعادة ضبط درجات الحرارة.'},
    approve=True, schedule=True, start=True, done=True)

# ص١٥ — إصلاح سور خارجي: فيلا الشاطئ — معتمد
req15 = mreq({'property_id':prop16.id,'tenancy_id':t24.id,'category':'other','priority':'1',
    'description':'كسر في جزء من السور الخارجي بعد رياح شديدة. يحتاج إصلاح عاجل لأسباب أمنية.',
    'request_date':str(ago(1)),'supplier_partner_id':tech7.id,'scheduled_date':str(dt(ahead(2),7)),
    'estimated_duration':6.0,'labor_cost':800,'materials_cost':600,'cost_bearer':'owner'},
    approve=True)

# ص١٦ — صيانة دورية كهربائية: مستودع جدة — مكتملة
req16 = mreq({'property_id':prop27.id,'tenancy_id':t20.id,'category':'electrical','priority':'2',
    'description':'فحص دوري للوحة الكهربائية الرئيسية وإحلال الأسلاك القديمة في المستودع.',
    'request_date':str(ago(30)),'supplier_partner_id':tech6.id,'scheduled_date':str(dt(ago(28),8)),
    'actual_duration':6.0,'labor_cost':700,'materials_cost':450,'cost_bearer':'owner',
    'notes':'تم استبدال ٣ دوائر كهربائية قديمة وتحديث اللوحة الرئيسية.'},
    approve=True, schedule=True, start=True, done=True)

# ص١٧ — إصلاح دش مياه ساخنة: شقة الصفا — مجدول
req17 = mreq({'property_id':prop22.id,'tenancy_id':t16.id,'category':'plumbing','priority':'2',
    'description':'سخان المياه لا يعمل بشكل صحيح — المياه لا تصل درجة الحرارة المطلوبة.',
    'request_date':str(ago(2)),'supplier_partner_id':tech7.id,'scheduled_date':str(dt(ahead(1),11)),
    'estimated_duration':2.0,'labor_cost':250,'materials_cost':180,'cost_bearer':'owner'},
    approve=True, schedule=True)

# ص١٨ — نقل أثاث واستوديو: النخبة — جديد
req18 = mreq({'property_id':prop31.id,'category':'other','priority':'0',
    'description':'إزالة بعض التركيبات القديمة في الاستوديو التي تعيق استخدامه.',
    'request_date':str(today),'estimated_duration':2.0,'labor_cost':200,'materials_cost':0,'cost_bearer':'owner'})

# ص١٩ — طلاء وتجديد: شقة الزهراء — معتمد
req19 = mreq({'property_id':prop23.id,'tenancy_id':t17.id,'category':'painting','priority':'1',
    'description':'إعادة طلاء جدران الصالة وغرفة النوم الرئيسية قبيل بدء العقد الجديد.',
    'request_date':str(ago(5)),'supplier_partner_id':tech9.id,'scheduled_date':str(dt(ahead(3),8)),
    'estimated_duration':10.0,'labor_cost':500,'materials_cost':350,'cost_bearer':'owner'},
    approve=True)

# ص٢٠ — شبكة إنترنت مكتب النور — مجدول
req20 = mreq({'property_id':prop25.id,'tenancy_id':t19.id,'category':'other','priority':'2',
    'description':'ضعف في إشارة الشبكة اللاسلكية في الجناح الشرقي من المكتب.',
    'request_date':str(ago(3)),'supplier_partner_id':tech10.id,'scheduled_date':str(dt(ahead(1),13)),
    'estimated_duration':2.0,'labor_cost':250,'materials_cost':300,'cost_bearer':'tenant',
    'notes':'يحتاج تركيب نقطة وصول إضافية.'},
    approve=True, schedule=True)

# Work orders for new requests
wo({'request_id':req11.id,'technician_id':tech5.id,'scheduled_date':str(dt(ahead(3),9)),
    'description':'فحص سطح الفيلا وسد مصادر التسرب بمادة عازلة.',
    'duration_planned':4.0,'labor_cost':350,'materials_cost':400}, schedule=True)

wo({'request_id':req14.id,'technician_id':tech8.id,'scheduled_date':str(dt(ago(18),9)),
    'description':'صيانة ربع سنوية: تنظيف الفلاتر، فحص غاز التبريد، ضبط المنظمات.',
    'duration_planned':4.0,'duration_actual':4.0,'labor_cost':600,'materials_cost':200},
    schedule=True, start=True, done=True)

wo({'request_id':req16.id,'technician_id':tech6.id,'scheduled_date':str(dt(ago(28),8)),
    'description':'استبدال الأسلاك القديمة وتحديث اللوحة الكهربائية الرئيسية.',
    'duration_planned':6.0,'duration_actual':6.0,'labor_cost':700,'materials_cost':450},
    schedule=True, start=True, done=True)

wo({'request_id':req17.id,'technician_id':tech7.id,'scheduled_date':str(dt(ahead(1),11)),
    'description':'فحص سخان المياه واستبدال عنصر التسخين إن لزم.',
    'duration_planned':2.0,'labor_cost':250,'materials_cost':180}, schedule=True)

wo({'request_id':req20.id,'technician_id':tech10.id,'scheduled_date':str(dt(ahead(1),13)),
    'description':'تركيب نقطة وصول إضافية وإعادة تهيئة الشبكة اللاسلكية.',
    'duration_planned':2.0,'labor_cost':250,'materials_cost':300}, schedule=True)

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 10 — Maintenance Contracts (4)
# ══════════════════════════════════════════════════════════════════════════════
print("10/16  عقود الصيانة…")

mc1 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':tech2.id,'property_ids':[(6,0,[prop1.id,prop9.id])],
    'category':'ac','frequency':'quarterly',
    'start_date':str(ago(90)),'end_date':str(ahead(275)),
    'service_description':'صيانة ربع سنوية لأجهزة التكييف: تنظيف الفلاتر وفحص غاز التبريد.',
    'estimated_cost_per_visit':750.0})
mc1.action_activate()

mc2 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':tech1.id,'property_ids':[(6,0,[prop4.id,prop5.id,prop7.id])],
    'category':'plumbing','frequency':'annual',
    'start_date':str(ago(30)),'end_date':str(ahead(335)),
    'service_description':'فحص وصيانة سنوية لشبكات السباكة والصرف الصحي.',
    'estimated_cost_per_visit':500.0})
mc2.action_activate()

mc3 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':tech8.id,'property_ids':[(6,0,[prop24.id,prop25.id])],
    'category':'ac','frequency':'quarterly',
    'start_date':str(ago(160)),'end_date':str(ahead(205)),
    'service_description':'صيانة ربع سنوية شاملة لأجهزة التكييف والتبريد في المكاتب التجارية.',
    'estimated_cost_per_visit':900.0})
mc3.action_activate()

mc4 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':tech6.id,'property_ids':[(6,0,[prop18.id,prop19.id,prop20.id])],
    'category':'electrical','frequency':'annual',
    'start_date':str(ago(90)),'end_date':str(ahead(275)),
    'service_description':'فحص وصيانة سنوية للمنظومة الكهربائية والمصاعد في الأبراج السكنية.',
    'estimated_cost_per_visit':1200.0})
mc4.action_activate()

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 11 — Broker Commissions (9)
# ══════════════════════════════════════════════════════════════════════════════
print("11/16  العمولات…")

def comm(vals):
    c = env['sa.broker.commission'].create(vals)
    c.action_confirm()
    return c

comm({'broker_partner_id':broker1.id,'tenancy_id':t1.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(180)),'notes':'عمولة شركة الوافر — فيلا الروضة ١٢',
    'line_ids':[(0,0,{'description':'عمولة توقيع فيلا الروضة','due_date':str(ago(180)),'amount':4000,'state':'paid'})]})

comm({'broker_partner_id':broker2.id,'tenancy_id':t2.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(90)),'notes':'عمولة طارق الغامدي — شقة العليا ٣ب',
    'line_ids':[(0,0,{'description':'عمولة شقة العليا','due_date':str(ago(90)),'amount':2250,'state':'paid'})]})

comm({'broker_partner_id':broker3.id,'tenancy_id':t4.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(337)),'notes':'عمولة هند العمودي — شقة الحمراء ١٥',
    'line_ids':[(0,0,{'description':'عمولة شقة الحمراء','due_date':str(ago(337)),'amount':2100,'state':'paid'})]})

comm({'broker_partner_id':broker1.id,'tenancy_id':t5.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'split',
    'date_signed':str(ago(365)),'notes':'عمولة شركة الوافر — مكتب بيزنس باي، قسطين',
    'line_ids':[
        (0,0,{'description':'القسط الأول عند التوقيع','due_date':str(ago(365)),'amount':3000,'state':'paid'}),
        (0,0,{'description':'القسط الثاني بعد ٦ أشهر', 'due_date':str(ago(185)),'amount':3000,'state':'paid'})]})

comm({'broker_partner_id':broker4.id,'tenancy_id':t12.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(150)),'notes':'عمولة بيت الكفاءة — شقة العقيق ٥ج',
    'line_ids':[(0,0,{'description':'عمولة شقة العقيق','due_date':str(ago(150)),'amount':2600,'state':'paid'})]})

comm({'broker_partner_id':broker5.id,'tenancy_id':t13.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(200)),'notes':'عمولة ريان الحسين — شقة الورود ٨أ',
    'line_ids':[(0,0,{'description':'عمولة شقة الورود','due_date':str(ago(200)),'amount':2000,'state':'paid'})]})

comm({'broker_partner_id':broker6.id,'tenancy_id':t16.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'on_signup',
    'date_signed':str(ago(270)),'notes':'عمولة نجلاء البكر — شقة الصفا ٦ه',
    'line_ids':[(0,0,{'description':'عمولة شقة الصفا','due_date':str(ago(270)),'amount':2200,'state':'paid'})]})

comm({'broker_partner_id':broker1.id,'tenancy_id':t18.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'split',
    'date_signed':str(ago(160)),'notes':'عمولة الوافر — مكتب الأعمال الذكية ١٢و، قسطين',
    'line_ids':[
        (0,0,{'description':'القسط الأول عند التوقيع','due_date':str(ago(160)),'amount':2375,'state':'paid'}),
        (0,0,{'description':'القسط الثاني بعد ٦ أشهر', 'due_date':str(ago(70)), 'amount':2375,'state':'paid'})]})

comm({'broker_partner_id':broker4.id,'tenancy_id':t24.id,
    'commission_type':'percentage','commission_rate':5.0,'payment_schedule':'split',
    'date_signed':str(ago(90)),'notes':'عمولة بيت الكفاءة — فيلا الشاطئ ٤، قسطين',
    'line_ids':[
        (0,0,{'description':'القسط الأول عند التوقيع','due_date':str(ago(90)), 'amount':2625,'state':'paid'}),
        (0,0,{'description':'القسط الثاني بعد ٦ أشهر', 'due_date':str(ahead(95)),'amount':2625,'state':'pending'})]})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 12 — Ejar ECRS Contracts (10 — covers all lifecycle states)
# ══════════════════════════════════════════════════════════════════════════════
print("12/16  عقود إيجار ECRS…")

def ejar_party(contract, role, entity_type, full_name_ar, id_type, id_number,
               mobile, iban=False, nationality='SA', sync_state='pending',
               cr_number=False, unified_number=False):
    vals = {'contract_id':contract.id,'role':role,'entity_type':entity_type,
            'full_name_ar':full_name_ar,'id_type':id_type,'id_number':id_number,
            'mobile':mobile,'nationality':nationality}
    if iban:           vals['iban']           = iban
    if cr_number:      vals['cr_number']      = cr_number
    if unified_number: vals['unified_number'] = unified_number
    rec = env['ejar.contract.party'].create(vals)
    if sync_state != 'pending': rec.write({'sync_state': sync_state})
    return rec

def ejar_unit(contract, property_rec, unit_number, unit_type, area,
              floor_number=0, bedrooms=0, bathrooms=0,
              finishing='finished', furnishing='unfurnished', sync_state='pending'):
    rec = env['ejar.contract.unit'].create({
        'contract_id':contract.id,'property_id':property_rec.id,
        'unit_number':unit_number,'unit_type':unit_type,'area':area,
        'floor_number':floor_number,'bedrooms':bedrooms,'bathrooms':bathrooms,
        'finishing':finishing,'furnishing':furnishing})
    if sync_state != 'pending': rec.write({'sync_state': sync_state})
    return rec

def sync_log(contract, action, direction, endpoint, http_method,
             http_status, duration_ms, status='success',
             request_body=None, response_body=None, error_message=None):
    return env['ejar.sync.log'].create({
        'company_id':company.id,'contract_id':contract.id,'action':action,
        'direction':direction,'http_method':http_method,'endpoint':endpoint,
        'http_status':http_status,'duration_ms':duration_ms,'status':status,
        'request_body':request_body or False,'response_body':response_body or False,
        'error_message':error_message or False})

base_ec = {'brokerage_profile_id':ejar_profile.id,'currency_id':SAR.id,
           'contract_sub_type':'main','sublease_allowed':False,
           'ejar_fees_paid_by':'brokerage_office','brokerage_fee_paid_by':'lessor'}

# ع.إيجار-١  فيلا الروضة — building (جارٍ الإعداد)
ec1 = env['ejar.contract'].create({**base_ec,'tenancy_id':t1.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t1.start_date,'end_date':t1.end_date,
    'rent_amount':80000,'payment_schedule':'quarterly','payment_option':'bank_transfer',
    'brokerage_fee':2000})
ec1.action_start_building()
ejar_party(ec1,'lessor','individual','محمد بن عبدالله القحطاني',
           'national_id','1023456789','+966501234001',iban='SA0380000000608010167519')
ejar_party(ec1,'tenant','individual','خالد بن عبدالله الراشدي',
           'national_id','1098765432','+966503100001')
ejar_unit(ec1,prop1,'فيلا-١٢','villa',450,bedrooms=5,bathrooms=4)

# ع.إيجار-٢  شقة الملقا — ready (جاهز للإرسال)
ec2 = env['ejar.contract'].create({**base_ec,'tenancy_id':t3.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t3.start_date,'end_date':t3.end_date,
    'rent_amount':48000,'payment_schedule':'monthly','payment_option':'mada',
    'brokerage_fee':1200})
ec2.action_start_building()
ejar_party(ec2,'lessor','individual','محمد بن عبدالله القحطاني',
           'national_id','1023456789','+966501234001',
           iban='SA0380000000608010167519',sync_state='synced')
ejar_party(ec2,'tenant','individual','نورة سعد الحمدان',
           'national_id','1067891234','+966503100003',sync_state='synced')
ejar_unit(ec2,prop5,'ملقا-٧أ','apartment',160,floor_number=7,
          bedrooms=3,bathrooms=2,sync_state='synced')
ec2.write({'ejar_status':'ready'})

# ع.إيجار-٣  شقة العليا — submitted (بانتظار موافقة إيجار)
ec3 = env['ejar.contract'].create({**base_ec,'tenancy_id':t2.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t2.start_date,'end_date':t2.end_date,
    'rent_amount':45000,'payment_schedule':'quarterly','payment_option':'bank_transfer',
    'brokerage_fee':1125,
    'ejar_contract_id':'DEMO-EJAR-003','ejar_contract_number':'1234567890'})
ec3.action_start_building()
ec3.write({'ejar_status':'submitted','ejar_last_sync':today,'submit_attempt':1})
ejar_party(ec3,'lessor','individual','محمد بن عبدالله القحطاني',
           'national_id','1023456789','+966501234001',
           iban='SA0380000000608010167519',sync_state='synced')
ejar_party(ec3,'tenant','individual','عمر محمد الفاروق',
           'national_id','1034512678','+966503100002',sync_state='synced')
ejar_unit(ec3,prop4,'عليا-٣ب','apartment',140,floor_number=3,
          bedrooms=3,bathrooms=2,sync_state='synced')
sync_log(ec3,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,842,
         request_body='{"contractType":"RESIDENTIAL"}',
         response_body='{"status":"ACCEPTED","contractId":"DEMO-EJAR-003"}')
sync_log(ec3,'contract_poll','outbound',
         '/ecrs/api/v1/contracts/DEMO-EJAR-003/status','GET',200,310,
         response_body='{"status":"PENDING_APPROVAL"}')

# ع.إيجار-٤  مكتب بيزنس باي — approved (موافق عليه)
ec4 = env['ejar.contract'].create({**base_ec,'tenancy_id':t5.id,
    'contract_type':'commercial','use_type':'commercial',
    'start_date':t5.start_date,'end_date':t5.end_date,
    'rent_amount':120000,'payment_schedule':'quarterly','payment_option':'bank_transfer',
    'brokerage_fee':3000,
    'ejar_contract_id':'DEMO-EJAR-004','ejar_contract_number':'9876543210'})
ec4.action_start_building()
ec4.write({'ejar_status':'approved','ejar_last_sync':today,'submit_attempt':1,'poll_count':3})
ejar_party(ec4,'lessor','organization','شركة الواحة للتطوير العقاري',
           'passport','1010345678','+966114001400',
           iban='SA1020000005678901234567',
           cr_number='1010345678',unified_number='1010345678',sync_state='synced')
ejar_party(ec4,'tenant','individual','أحمد يوسف العمري',
           'national_id','1055443322','+966503100005',sync_state='synced')
ejar_unit(ec4,prop9,'بيزنس-باي-٢٠١','office',280,floor_number=20,
          bathrooms=2,furnishing='furnish_new',sync_state='synced')
sync_log(ec4,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,763,
         response_body='{"status":"ACCEPTED","contractId":"DEMO-EJAR-004"}')
sync_log(ec4,'webhook_received','inbound','/ejar/webhook','POST',200,45,
         request_body='{"event":"contract.approved","contractNumber":"9876543210"}',
         response_body='{"received":true}')

# ع.إيجار-٥  شقة الحمراء — rejected (مرفوض — رقم الهوية غير مطابق)
ec5 = env['ejar.contract'].create({**base_ec,'tenancy_id':t4.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t4.start_date,'end_date':t4.end_date,
    'rent_amount':42000,'payment_schedule':'annual','payment_option':'bank_transfer',
    'brokerage_fee':1050,'ejar_contract_id':'DEMO-EJAR-005'})
ec5.action_start_building()
ec5.write({'ejar_status':'rejected','ejar_last_sync':today,'submit_attempt':1,
           'rejection_reason':'رقم الهوية غير مطابق لسجلات أبشر. يرجى مراجعة بيانات المستأجر.'})
ejar_party(ec5,'lessor','individual','فاطمة بنت سعد الزهراني',
           'national_id','1056789012','+966502234002',
           iban='SA4420000001234567891234',sync_state='synced')
ejar_party(ec5,'tenant','individual','عائشة أحمد مالك',
           'iqama','2123456789','+966503100004',nationality='PK',sync_state='failed')
ejar_unit(ec5,prop6,'حمراء-١٥','apartment',130,floor_number=2,
          bedrooms=3,bathrooms=2,sync_state='synced')
sync_log(ec5,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,891,
         response_body='{"status":"ACCEPTED","contractId":"DEMO-EJAR-005"}')
sync_log(ec5,'webhook_received','inbound','/ejar/webhook','POST',200,38,
         request_body='{"event":"contract.rejected","reason":"ID_MISMATCH"}',
         status='error',error_message='رقم الهوية غير مطابق لسجلات أبشر')

# ع.إيجار-٦  المحل التجاري — draft (مسودة لم تُرسل)
env['ejar.contract'].create({**base_ec,'tenancy_id':t7.id,
    'contract_type':'commercial','use_type':'commercial',
    'start_date':t7.start_date,'end_date':t7.end_date,
    'rent_amount':55000,'payment_schedule':'biannual','payment_option':'bank_transfer',
    'brokerage_fee':1375})

# ع.إيجار-٧  شقة العقيق — building (جارٍ الإعداد)
ec7 = env['ejar.contract'].create({**base_ec,'tenancy_id':t12.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t12.start_date,'end_date':t12.end_date,
    'rent_amount':52000,'payment_schedule':'monthly','payment_option':'bank_transfer',
    'brokerage_fee':1300})
ec7.action_start_building()
ejar_party(ec7,'lessor','individual','ناصر بن سعد الحربي',
           'national_id','1089012340','+966504234006',iban='SA1980000008901234000012')
ejar_party(ec7,'tenant','individual','وليد محمد السبيعي',
           'national_id','1011223344','+966503100012')
ejar_unit(ec7,prop18,'عقيق-٥ج','apartment',170,floor_number=5,
          bedrooms=3,bathrooms=2)

# ع.إيجار-٨  مكتب الأعمال الذكية — approved (موافق عليه)
ec8 = env['ejar.contract'].create({**base_ec,'tenancy_id':t18.id,
    'contract_type':'commercial','use_type':'commercial',
    'start_date':t18.start_date,'end_date':t18.end_date,
    'rent_amount':95000,'payment_schedule':'quarterly','payment_option':'bank_transfer',
    'brokerage_fee':2375,
    'ejar_contract_id':'DEMO-EJAR-008','ejar_contract_number':'7654321098'})
ec8.action_start_building()
ec8.write({'ejar_status':'approved','ejar_last_sync':today,'submit_attempt':1,'poll_count':2})
ejar_party(ec8,'lessor','organization','شركة نجد للتطوير والإنشاء',
           'passport','1010765431','+966112223334',
           iban='SA8820000003456789000001',cr_number='1010765431',unified_number='1010765431',
           sync_state='synced')
ejar_party(ec8,'tenant','individual','سلطان بن أحمد البقمي',
           'national_id','1066779901','+966503100018',sync_state='synced')
ejar_unit(ec8,prop24,'أعمال-١٢و','office',230,floor_number=12,
          bathrooms=2,furnishing='furnish_new',sync_state='synced')
sync_log(ec8,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,790,
         response_body='{"status":"ACCEPTED","contractId":"DEMO-EJAR-008"}')
sync_log(ec8,'webhook_received','inbound','/ejar/webhook','POST',200,42,
         request_body='{"event":"contract.approved","contractNumber":"7654321098"}',
         response_body='{"received":true}')

# ع.إيجار-٩  فيلا الشاطئ — submitted (بانتظار موافقة إيجار)
ec9 = env['ejar.contract'].create({**base_ec,'tenancy_id':t24.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t24.start_date,'end_date':t24.end_date,
    'rent_amount':105000,'payment_schedule':'biannual','payment_option':'bank_transfer',
    'brokerage_fee':2625,
    'ejar_contract_id':'DEMO-EJAR-009','ejar_contract_number':'6543210987'})
ec9.action_start_building()
ec9.write({'ejar_status':'submitted','ejar_last_sync':today,'submit_attempt':1})
ejar_party(ec9,'lessor','individual','هيلة بنت محمد المطيري',
           'national_id','1012034567','+966502234007',
           iban='SA5480000009012034560001',sync_state='synced')
ejar_party(ec9,'tenant','individual','بندر بن فهد الرشيد',
           'national_id','1099112234','+966503100022',sync_state='synced')
ejar_unit(ec9,prop16,'شاطئ-٤','villa',550,bedrooms=6,bathrooms=5,sync_state='synced')
sync_log(ec9,'contract_submit','outbound','/ecrs/api/v1/contracts','POST',200,880,
         response_body='{"status":"ACCEPTED","contractId":"DEMO-EJAR-009"}')
sync_log(ec9,'contract_poll','outbound',
         '/ecrs/api/v1/contracts/DEMO-EJAR-009/status','GET',200,295,
         response_body='{"status":"PENDING_APPROVAL"}')

# ع.إيجار-١٠  شقة الأندلس — ready (جاهز للإرسال)
ec10 = env['ejar.contract'].create({**base_ec,'tenancy_id':t15.id,
    'contract_type':'residential','use_type':'residential_families',
    'start_date':t15.start_date,'end_date':t15.end_date,
    'rent_amount':50000,'payment_schedule':'quarterly','payment_option':'mada',
    'brokerage_fee':1250})
ec10.action_start_building()
ejar_party(ec10,'lessor','organization','شركة المملكة للتطوير العقاري',
           'passport','4030654321','+966126543211',
           iban='SA3220000002345678000001',cr_number='4030654321',unified_number='4030654321',
           sync_state='synced')
ejar_party(ec10,'tenant','individual','هند ناصر النومي',
           'iqama','2234567891','+966503100015',nationality='EG',sync_state='synced')
ejar_unit(ec10,prop21,'أندلس-١١ب','apartment',155,floor_number=11,
          bedrooms=3,bathrooms=2,sync_state='synced')
ec10.write({'ejar_status':'ready'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 13 — System Users (30 accounts — password: demo)
# ══════════════════════════════════════════════════════════════════════════════
print("13/16  المستخدمون…")

def make_user(name, email, partner, groups, password='demo'):
    existing = env['res.users'].search([('login','=',email)], limit=1)
    if existing:
        existing.password = password
        return existing
    kw = {'name':name,'login':email,'email':email,'groups_id':[(6,0,groups)],
          'password':password,'lang':'ar_001','tz':'Asia/Riyadh'}
    if partner: kw['partner_id'] = partner.id
    return env['res.users'].create(kw)

g = lambda x: env.ref(x).id
g_manager    = g('sa_security.group_pms_manager')
g_accountant = g('sa_security.group_pms_accountant')
g_agent      = g('sa_security.group_pms_agent')
g_owner      = g('sa_security.group_pms_owner')
g_tech       = g('sa_security.group_pms_technician')
g_portal     = g('base.group_portal')
g_tenant     = g('sa_security.group_pms_tenant_portal')

# Internal staff
make_user('سارة المدير',              'manager@propza-demo.sa',    None,    [g_manager])
make_user('عمر المحاسب',              'accountant@propza-demo.sa', None,    [g_accountant])
make_user('لينا الموظفة',             'agent@propza-demo.sa',      None,    [g_agent])
make_user('مستخدم العرض التوضيحي',    'demo@demo.com',             None,    [g_manager])

# Owners
for o in [owner1,owner2,owner3,owner4,owner6,owner7,owner8,owner9,owner10,owner11,owner12]:
    make_user(o.name, o.email, o, [g_owner])

# Technicians
for t in [tech1, tech2, tech3, tech6, tech7]:
    make_user(t.name, t.email, t, [g_tech])

# Tenants (portal + PMS tenant group)
for tn in [tenant1,tenant2,tenant3,tenant4,tenant5,tenant6,tenant7,tenant8,
           tenant9,tenant10,tenant12,tenant13,tenant14,tenant15,tenant16,
           tenant17,tenant18,tenant19,tenant20,tenant22,tenant24,tenant25]:
    make_user(tn.name, tn.email, tn, [g_tenant])

# Brokers (basic portal)
for b in [broker1, broker2, broker3, broker4, broker5, broker6]:
    make_user(b.name, b.email, b, [g_portal])

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 14 — Tenant Profiles (sa.user.profile data)
# ══════════════════════════════════════════════════════════════════════════════
print("14/16  الملفات الشخصية…")

from datetime import datetime as _dt

profile_data = [
    (tenant1, 'male',   '1985-03-15', 'مهندس معماري متخصص في تصميم المباني السكنية.',
     r_riyadh,'الرياض','العليا',    '3214','1','4521','12331','REAA3214'),
    (tenant2, 'male',   '1990-07-22', 'مدير مبيعات في شركة تقنية.',
     r_jeddah,'جدة',   'النزهة',   '7821','2','1234','23521','JZNZ7821'),
    (tenant3, 'female', '1988-11-08', 'معلمة في مدرسة ابتدائية حكومية.',
     r_riyadh,'الرياض','النرجس',   '5540','4','3312','13312','RNRJ5540'),
    (tenant4, 'female', '1992-04-20', 'موظفة في قطاع الصحة. مقيمة منذ 2017.',
     r_riyadh,'الرياض','الملقا',   '2210','1','8871','13521','RMLQ2210'),
    (tenant5, 'male',   '1979-09-12', 'محاسب قانوني. خبرة 20 عاماً.',
     r_riyadh,'الرياض','الروضة',   '8831','3','2245','11411','RRWD8831'),
    (tenant6, 'female', '1995-01-30', 'مصممة جرافيك مستقلة. تعمل عن بُعد.',
     r_dammam,'الدمام','الشاطئ',   '4412','2','5561','31441','DSHT4412'),
    (tenant7, 'male',   '1983-06-05', 'طيار في إحدى شركات الطيران الخليجية.',
     r_riyadh,'الرياض','الورود',   '6623','1','7712','12711','RWRD6623'),
    (tenant8, 'female', '1991-12-17', 'صيدلانية في مستشفى حكومي.',
     r_jeddah,'جدة',   'الحمراء',  '3345','5','9901','23411','JHMR3345'),
    (tenant9, 'male',   '1987-08-24', 'مقاول بناء يدير مشاريع صغيرة ومتوسطة.',
     r_riyadh,'الرياض','الصحافة',  '9912','2','3341','12261','RSSH9912'),
    (tenant10,'female', '1998-05-11', 'طالبة دكتوراه في جامعة الملك عبدالعزيز.',
     r_jeddah,'جدة',   'الأندلس',  '1123','7','6612','23631','JAND1123'),
    (tenant12,'male',   '1986-09-14', 'مهندس برمجيات في شركة تقنية ناشئة بالرياض.',
     r_riyadh,'الرياض','العقيق',   '4412','5','9901','13441','RAQQ4412'),
    (tenant13,'female', '1993-02-28', 'أخصائية تغذية في مستشفى خاص بجدة.',
     r_jeddah,'جدة',   'الورود',   '7723','3','1122','23551','JWRD7723'),
    (tenant14,'male',   '1981-11-01', 'مدير إداري في شركة لوجستية بالرياض.',
     r_riyadh,'الرياض','النخيل',   '3314','1','4431','12221','RNKL3314'),
    (tenant15,'female', '1989-06-17', 'معالجة نفسية، مقيمة منذ ٢٠١٥.',
     r_jeddah,'جدة',   'الأندلس',  '8821','4','6612','23631','JAND8821'),
    (tenant16,'male',   '1977-03-05', 'طيار في طيران السعودية، يقيم في جدة.',
     r_jeddah,'جدة',   'الصفا',    '5563','6','3312','23411','JSFA5563'),
    (tenant17,'female', '1996-08-12', 'مصمّمة أزياء، تعمل على مشاريع خاصة.',
     r_dammam,'الدمام','الزهراء',  '2234','2','1123','31221','DZHM2234'),
    (tenant18,'male',   '1983-04-25', 'رجل أعمال في القطاع اللوجستي.',
     r_riyadh,'الرياض','العقيق',   '9923','1','7712','12311','RAQQ9923'),
    (tenant19,'female', '1991-10-08', 'محامية في مكتب استشارات قانونية.',
     r_riyadh,'الرياض','الياسمين', '6634','3','5561','12541','RYSS6634'),
    (tenant20,'male',   '1975-12-20', 'مدير عام في شركة تطوير عقاري.',
     r_riyadh,'الرياض','النزهة',   '4445','2','3341','12421','RNZH4445'),
]

for (tn,gender,dob,bio,region,city,district,bldg,unit,addl,postal,short_addr) in profile_data:
    tn.write({'gender':gender,'date_of_birth':dob,'bio':bio,
              'sa_region_id':region.id if region else False,
              'city':city,'sa_district':district,'sa_building_no':bldg,
              'sa_unit_no':unit,'sa_additional_no':addl,'sa_postal_code':postal,
              'sa_national_address':short_addr})

# Identity verifications
now = _dt.now()

def make_verif(partner, id_type, id_number, id_expiry, state, rejection_reason=False):
    rec = env['sa.user.verification'].create({
        'partner_id':partner.id,'id_type':id_type,'id_number':id_number,
        'id_expiry':str(id_expiry) if id_expiry else False,'state':state,
        'submission_date': now if state in ('submitted','verified','rejected') else False,
        'verified_date':   now if state == 'verified' else False,
        'rejection_reason': rejection_reason or False})
    if state == 'verified':
        partner.write({'sa_id_type':id_type,'sa_national_id':id_number,
                       'sa_id_expiry':id_expiry,'sa_id_verified':True})
    return rec

make_verif(tenant1,  'national_id','1098765432', ahead(1095), 'verified')
make_verif(tenant2,  'national_id','1034512678', ahead(730),  'verified')
make_verif(tenant3,  'national_id','1067891234', ahead(548),  'submitted')
make_verif(tenant4,  'iqama',      '2123456789', ahead(180),  'verified')
make_verif(tenant5,  'national_id','1055443322', ago(10),     'rejected',
           rejection_reason='الوثيقة منتهية الصلاحية')
env['sa.user.verification'].create({'partner_id':tenant6.id,'id_type':'national_id',
    'id_number':'1066778899','state':'draft'})
make_verif(tenant7,  'national_id','1077889900', ahead(1460), 'verified')
make_verif(tenant8,  'national_id','1088990011', ahead(365),  'submitted')
make_verif(tenant9,  'national_id','1099887766', ahead(912),  'verified')
env['sa.user.verification'].create({'partner_id':tenant10.id,'id_type':'national_id',
    'id_number':'1044332211','state':'draft'})

make_verif(tenant12, 'national_id','1011223344', ahead(912),  'verified')
make_verif(tenant13, 'national_id','1022334451', ahead(548),  'submitted')
make_verif(tenant14, 'national_id','1033445562', ahead(730),  'verified')
make_verif(tenant15, 'iqama',      '2234567891', ahead(365),  'verified')
make_verif(tenant16, 'national_id','1044556671', ahead(1095), 'verified')
make_verif(tenant17, 'national_id','1055667782', ahead(730),  'submitted')
make_verif(tenant18, 'national_id','1066779901', ahead(912),  'verified')
env['sa.user.verification'].create({'partner_id':tenant19.id,'id_type':'national_id',
    'id_number':'1077991122','state':'draft'})
make_verif(tenant20, 'national_id','1088001123', ahead(1095), 'verified')

# Documents
def make_doc(partner, doc_type, name, upload_days_ago, expiry_days=None, notes=None):
    env['sa.user.document'].create({
        'partner_id':partner.id,'doc_type':doc_type,'name':name,
        'upload_date':str(ago(upload_days_ago)),
        'expiry_date':str(ahead(expiry_days)) if expiry_days is not None else False,
        'notes':notes or False})

make_doc(tenant1,'national_id','هوية وطنية — خالد الراشدي',90,1095)
make_doc(tenant1,'other','خطاب راتب — وزارة الإسكان',30,180,'يُستخدم لإثبات الدخل')
make_doc(tenant2,'national_id','هوية وطنية — عمر الفاروق',180,730)
old_doc = env['sa.user.document'].create({'partner_id':tenant2.id,'doc_type':'lease_contract',
    'name':'عقد إيجار سابق — جدة 2022','upload_date':str(ago(500)),'expiry_date':str(ago(90))})
old_doc.action_archive()
make_doc(tenant3,'national_id','هوية وطنية — نورة الحمدان',15,548)
make_doc(tenant4,'national_id','إقامة — عائشة مالك',60,25,'يجب التجديد قبل نهاية الشهر')
make_doc(tenant5,'national_id','هوية وطنية منتهية — أحمد العمري',400,-10)
make_doc(tenant7,'national_id','هوية وطنية — محمد الشهري',200,1460)
make_doc(tenant7,'other','كشف حساب بنكي — بنك الراجحي',10,90,'آخر 3 أشهر')
make_doc(tenant8,'national_id','هوية وطنية — ريم القرني',45,365)
make_doc(tenant9,'national_id','هوية وطنية — فيصل الغامدي',120,912)
make_doc(tenant9,'lease_contract','عقد إيجار — فيلا الورود',30,335,'نسخة من العقد الحالي')

make_doc(tenant12,'national_id','هوية وطنية — وليد السبيعي',30,912)
make_doc(tenant12,'other','كشف راتب — شركة التقنية',5,90,'يستخدم لإثبات الملاءة المالية')
make_doc(tenant13,'national_id','هوية وطنية — منال الحازمي',15,548)
make_doc(tenant14,'national_id','هوية وطنية — طارق المالكي',60,730)
make_doc(tenant14,'lease_contract','عقد إيجار سابق — شقة حي النخيل',180,-90)
make_doc(tenant15,'national_id','إقامة — هند النومي',30,365,'تجديد الإقامة مطلوب قبل انتهاء السنة')
make_doc(tenant16,'national_id','هوية وطنية — يوسف القرشي',90,1095)
make_doc(tenant17,'national_id','هوية وطنية — أسماء العنزي',20,730)
make_doc(tenant18,'national_id','هوية وطنية — سلطان البقمي',50,912)
make_doc(tenant18,'other','شهادة تسجيل تجاري',30,180,'وثيقة تسجيل النشاط التجاري')
make_doc(tenant20,'national_id','هوية وطنية — عبدالرحمن الصالح',40,1095)
make_doc(tenant20,'other','خطاب ضمان بنكي — بنك الرياض',10,180,'للتأكيد على الملاءة المالية')

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 15 — CRM Leads, Showings & Reservations
# ══════════════════════════════════════════════════════════════════════════════
print("15/16  بيانات CRM…")

st_new     = env['sa.crm.stage'].search([('sequence','=',10)], limit=1)
st_contact = env['sa.crm.stage'].search([('sequence','=',20)], limit=1)
st_showing = env['sa.crm.stage'].search([('sequence','=',30)], limit=1)
st_negot   = env['sa.crm.stage'].search([('sequence','=',40)], limit=1)
st_won     = env['sa.crm.stage'].search([('is_won','=',True)], limit=1)
st_lost    = env['sa.crm.stage'].search([('sequence','=',60)], limit=1)

u_manager = env['res.users'].search([('login','=','manager@propza-demo.sa')], limit=1)
u_agent   = env['res.users'].search([('login','=','agent@propza-demo.sa')],   limit=1)

def lead(partner, lead_type, prop_type, stage, user, source,
         budget_min, budget_max, region=None, prop=None, commission=0,
         deadline_days=None, priority='0', state='open',
         lost_reason=None, description=None):
    vals = {'partner_id':partner.id,'lead_type':lead_type,'property_type':prop_type,
            'stage_id':stage.id,'user_id':user.id,'source':source,
            'budget_min':budget_min,'budget_max':budget_max,
            'preferred_region_id':region.id if region else False,
            'property_id':prop.id if prop else False,
            'expected_commission':commission,
            'date_deadline':str(ahead(deadline_days)) if deadline_days else False,
            'priority':priority,'state':state,'lost_reason':lost_reason or False,
            'description':description or False}
    if state == 'lost': vals['active'] = False
    return env['sa.crm.lead'].create(vals)

def showing(crm_lead, prop, scheduled_days, outcome, user, notes=None):
    env['sa.crm.showing'].create({
        'lead_id':crm_lead.id,'property_id':prop.id,
        'scheduled_date':str(ago(scheduled_days))+' 10:00:00',
        'user_id':user.id,'outcome':outcome,'notes':notes or False})

# Open leads
l1 = lead(tenant1,'rent','residential',st_negot,u_agent,'referral',
          40000,55000,region=r_riyadh,prop=prop4,commission=2750,
          deadline_days=14,priority='1',
          description='يفضل الطابق الثاني أو أعلى، قريب من المدارس')
showing(l1,prop4,5,'done',u_agent,'أعجبه الموقع، يفاوض على السعر')
showing(l1,prop5,10,'done',u_agent,'لم يعجبه المدخل')

l2 = lead(tenant2,'rent','commercial',st_showing,u_agent,'website',
          80000,130000,region=r_riyadh,prop=prop9,commission=6500,
          deadline_days=30,priority='1')
showing(l2,prop9,3,'done',u_agent,'عرض المكتب، اهتمام جيد')
showing(l2,prop10,1,'scheduled',u_agent,'جولة ثانية مقررة الأسبوع القادم')

l3 = lead(tenant3,'rent','residential',st_contact,u_manager,'phone',
          90000,120000,region=r_jeddah,commission=6000,deadline_days=45,priority='2',
          description='عائلة كبيرة، تحتاج 5 غرف على الأقل')

l4 = lead(tenant4,'rent','residential',st_new,u_agent,'social',
          30000,45000,region=r_dammam,deadline_days=60)

l5 = lead(tenant5,'rent','industrial',st_new,u_manager,'walkin',
          60000,90000,region=r_riyadh,
          description='مستودع للتخزين، مساحة لا تقل عن 500 م²')

l6 = lead(tenant7,'rent','commercial',st_contact,u_agent,'portal',
          35000,50000,region=r_riyadh,deadline_days=20,priority='1')

# Won leads
l7 = lead(tenant8,'rent','residential',st_won,u_agent,'referral',
          40000,55000,region=r_riyadh,prop=prop5,commission=2400,state='won')
showing(l7,prop5,30,'done',u_agent,'أعجبتها الشقة، وقّعت العقد')
showing(l7,prop4,35,'done',u_agent,'الخيار الأول لم يناسبها')

l8 = lead(tenant9,'buy','residential',st_won,u_manager,'website',
          1200000,1800000,region=r_riyadh,prop=prop1,
          commission=54000,state='won',priority='2')
showing(l8,prop1,45,'done',u_manager,'زار الفيلا مرتين، قرر الشراء')
showing(l8,prop2,50,'done',u_manager,'خيار احتياطي لم يُعجبه')

# Lost leads
lead(tenant6,'rent','residential',st_lost,u_agent,'phone',
     35000,50000,region=r_riyadh,state='lost',
     lost_reason='قررت الانتقال إلى جدة')

lead(tenant10,'rent','commercial',st_lost,u_agent,'walkin',
     70000,100000,region=r_riyadh,state='lost',
     lost_reason='وجد مكتباً عبر طرف ثالث')

# Additional open leads
l9 = lead(tenant20,'rent','residential',st_negot,u_manager,'referral',
          120000,160000,region=r_riyadh,prop=prop32,commission=8000,
          deadline_days=10,priority='2',
          description='يبحث عن بنتهاوس أو فيلا فاخرة. ميزانية مرنة للمكان المناسب.')
showing(l9,prop32,3,'done',u_manager,'أعجبه البنتهاوس، يتفاوض على السعر')

l10 = lead(tenant14,'rent','residential',st_showing,u_agent,'website',
           32000,42000,region=r_riyadh,prop=prop20,commission=2000,
           deadline_days=21,priority='1',
           description='شقة لأسرة مكونة من ٣ أفراد، يفضل حي النخيل أو ما يجاوره.')
showing(l10,prop20,7,'done',u_agent,'اهتمام كبير، يفكر في الأمر')
showing(l10,prop19,5,'done',u_agent,'أعجبته شقة الورود أكثر، ينتظر قرار الأسرة')

l11 = lead(tenant23,'rent','residential',st_contact,u_agent,'social',
           45000,60000,region=r_jeddah,deadline_days=30,
           description='شقة في جدة لسكن فردي عالي الجودة.')

l12 = lead(tenant25,'rent','commercial',st_new,u_manager,'phone',
           50000,80000,region=r_jeddah,
           description='محل تجاري في جدة، مساحة لا تقل عن ٨٠ م².')

l13 = lead(tenant24,'rent','industrial',st_showing,u_manager,'referral',
           50000,80000,region=r_dammam,prop=prop28,commission=4000,
           deadline_days=14,priority='1',
           description='مستودع للتخزين في المنطقة الشرقية، يفضل قرب الميناء.')
showing(l13,prop28,4,'done',u_manager,'المكان مناسب، يطلب مراجعة شروط الصيانة')

l14 = lead(tenant22,'rent','residential',st_negot,u_agent,'portal',
           100000,120000,region=r_jeddah,prop=prop16,commission=6000,
           deadline_days=7,priority='2',
           description='فيلا بالقرب من البحر، عائلة مكونة من ٦ أفراد.')
showing(l14,prop16,8,'done',u_agent,'أعجبته الفيلا، يتفاوض على قيمة الإيجار')
showing(l14,prop2, 12,'done',u_agent,'خيار احتياطي، يفضل فيلا الشاطئ')

# Won leads (additional)
l15 = lead(tenant13,'rent','residential',st_won,u_agent,'referral',
           38000,45000,region=r_jeddah,prop=prop22,commission=2200,state='won')
showing(l15,prop22,25,'done',u_agent,'زارت الشقة مرتين، وقّعت العقد')

l16 = lead(tenant26,'rent','commercial',st_won,u_manager,'website',
           65000,80000,region=r_jeddah,prop=prop25,commission=3600,state='won',priority='1')
showing(l16,prop25,20,'done',u_manager,'الشركة وافقت على المكتب، تم التوقيع')

# Lost leads (additional)
lead(tenant21,'rent','residential',st_lost,u_agent,'social',
     28000,38000,region=r_riyadh,state='lost',
     lost_reason='وجدت استوديو عبر جهة أخرى بسعر أفضل')

lead(tenant17,'rent','residential',st_lost,u_agent,'referral',
     30000,42000,region=r_dammam,state='lost',
     lost_reason='قررت التمديد في سكنها الحالي')

# Reservations
res1 = env['sa.crm.reservation'].create({
    'lead_id':l4.id,'property_id':prop8.id,'user_id':u_agent.id,
    'date_start':str(today),'date_end':str(ahead(7)),
    'deposit_amount':5000,'currency_id':SAR.id,
    'notes':'حجز أولي للشقة في الدمام أثناء التفاوض.'})

res2 = env['sa.crm.reservation'].create({
    'lead_id':l2.id,'property_id':prop10.id,'user_id':u_agent.id,
    'date_start':str(today),'date_end':str(ahead(10)),
    'deposit_amount':12000,'currency_id':SAR.id,
    'notes':'حجز تجاري فعال بعد الجولة الأولى.'})
res2.action_activate()

env['sa.crm.reservation'].create({
    'lead_id':l5.id,'property_id':prop12.id,'user_id':u_manager.id,
    'date_start':str(ago(40)),'date_end':str(ago(5)),
    'deposit_amount':8000,'currency_id':SAR.id,
    'notes':'حجز مستودع انتهى بعد رفض الطلب.','state':'expired'})

res4 = env['sa.crm.reservation'].create({
    'lead_id':l7.id,'property_id':prop8.id,'user_id':u_manager.id,
    'date_start':str(ago(10)),'date_end':str(ahead(5)),
    'deposit_amount':15000,'currency_id':SAR.id,
    'notes':'حجز تحوّل إلى صفقة بعد قبول الشقة.'})
res4.action_convert_to_deal()

res5 = env['sa.crm.reservation'].create({
    'lead_id':l14.id,'property_id':prop16.id,'user_id':u_agent.id,
    'date_start':str(today),'date_end':str(ahead(14)),
    'deposit_amount':20000,'currency_id':SAR.id,
    'notes':'حجز فيلا الشاطئ أثناء التفاوض على السعر النهائي.'})
res5.action_activate()

env['sa.crm.reservation'].create({
    'lead_id':l13.id,'property_id':prop28.id,'user_id':u_manager.id,
    'date_start':str(ago(3)),'date_end':str(ahead(4)),
    'deposit_amount':10000,'currency_id':SAR.id,
    'notes':'حجز مستودع الدمام ريثما تتم مراجعة بنود الصيانة.'})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 16 — Summary
# ══════════════════════════════════════════════════════════════════════════════
print("16/16  ملخص…")
print("")
print("══════════════════════════════════════════════════════════════════")
print("  ✓ تم تحميل البيانات التجريبية بنجاح!")
print("══════════════════════════════════════════════════════════════════")

def count(model, domain=None):
    return env[model].with_context(active_test=False).search_count(domain or [])

rows = [
    ("الملاك",                  f"{count('res.partner',[('is_property_owner','=',True)])}  (٦ أفراد + ٦ شركات)"),
    ("المستأجرون",              f"{count('res.partner',[('is_tenant','=',True)])}  (٢٥ فرداً + ٣ شركات)"),
    ("الوسطاء",                 f"{count('res.partner',[('is_broker','=',True)])}  (شركتان + ٤ أفراد)"),
    ("الفنيون",                 f"{count('res.partner',[('is_technician','=',True)])}"),
    ("العقارات",                f"{count('property.property')}  (فلل + شقق + مكاتب + مستودعات + محلات + بنتهاوس)"),
    ("عقود الإيجار",            f"{count('property.tenancy')}  (نشطة + مؤكدة + مسودات + منتهية)"),
    ("دفعات الإيجار",           f"{count('sa.rent.payment')}"),
    ("المعاينات",               f"{count('sa.property.inspection')}  (موقعة + مكتملة + مسودات)"),
    ("طلبات الصيانة",           f"{count('sa.maintenance.request')}  (متنوعة الحالات)"),
    ("أوامر العمل",             f"{count('sa.maintenance.work_order')}  (منجزة + مجدولة + قيد التنفيذ)"),
    ("عقود الصيانة",            f"{count('sa.maintenance.contract')}  (تكييف + كهربائي + سباكة)"),
    ("عمولات الوسطاء",          f"{count('sa.broker.commission')}  (مؤكدة ومدفوعة أو مستحقة)"),
    ("عقود إيجار ECRS",         f"{count('ejar.contract')}  (draft → building → ready → submitted → approved → rejected)"),
    ("أطراف عقود إيجار",        f"{count('ejar.contract.party')}"),
    ("وحدات عقود إيجار",        f"{count('ejar.contract.unit')}"),
    ("سجلات API إيجار",         f"{count('ejar.sync.log')}"),
    ("توثيق الهوية",            f"{count('sa.user.verification')}  (موثَّق + مقدَّم + مسودة/مرفوض)"),
    ("وثائق المستخدمين",        f"{count('sa.user.document')}"),
    ("طلبات CRM",               f"{count('sa.crm.lead')}  (مفتوحة + فاز + خسر)"),
    ("جولات ميدانية",           f"{count('sa.crm.showing')}"),
    ("حجوزات CRM",              f"{count('sa.crm.reservation')}  (مسودة، محجوزة، منتهية، تحويل)"),
    ("المستخدمون",              f"{count('res.users',[('share','=',False)])}  (كلمة المرور: demo)"),
]

for label, val in rows:
    print(f"  {label:<30} {val}")

print("")
PYEOF

echo ""
echo "=========================================="
echo "  ✓ Setup complete!"
echo "=========================================="
echo "  URL:      http://localhost:8069"
echo "  Database: $DB"
echo "  Admin:    ${ADMIN_EMAIL:-admin@propza.sa} / ${ADMIN_PASSWORD:-admin}"
echo "  Demo:     demo@demo.com / demo"
echo ""
echo "  Ejar API credentials: UAT placeholders"
echo "  Update via: Settings → Ejar (ECRS) API"
echo ""
