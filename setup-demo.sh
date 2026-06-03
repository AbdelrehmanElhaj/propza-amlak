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

if db_exists "$DB" && [ "$UPGRADE" = false ]; then
    echo "Database '$DB' already exists. Use -f to recreate or -u to upgrade."
    if [ "$WITH_DEMO" = true ]; then
        echo ""; echo "Seeding demo data into existing DB..."
    else
        exit 0
    fi
else
    ACTION_FLAG="-i"
    [ "$UPGRADE" = true ] && ACTION_FLAG="-u"

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

    # ── Company / locale configuration ───────────────────────────────────────
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
fi

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
# 1 — Owners (5)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 2 — Tenants (11)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 3 — Brokers (3)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 4 — Technicians (5)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 5 — Properties (14)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 6 — Tenancies (11)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 8 — Inspections (5)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 9 — Maintenance Requests & Work Orders (10 + 5)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 10 — Maintenance Contracts (2)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 11 — Broker Commissions (4)
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 12 — Ejar ECRS Contracts (6 — covers all lifecycle states)
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
           'national_id','1010345678','+966114001400',
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

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════════
# 13 — System Users (23 accounts — password: demo)
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
for o in [owner1, owner2, owner3, owner4]:
    make_user(o.name, o.email, o, [g_owner])

# Technicians
for t in [tech1, tech2, tech3]:
    make_user(t.name, t.email, t, [g_tech])

# Tenants (portal + PMS tenant group)
for tn in [tenant1,tenant2,tenant3,tenant4,tenant5,
           tenant6,tenant7,tenant8,tenant9,tenant10]:
    make_user(tn.name, tn.email, tn, [g_tenant])

# Brokers (basic portal)
for b in [broker1, broker2, broker3]:
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
    ("الملاك",                  f"{count('res.partner',[('is_property_owner','=',True)])}  (٣ أفراد + ٢ شركات)"),
    ("المستأجرون",              f"{count('res.partner',[('is_tenant','=',True)])}  (١٠ أفراد + ١ شركة)"),
    ("الوسطاء",                 f"{count('res.partner',[('is_broker','=',True)])}  (شركة + فردان)"),
    ("الفنيون",                 f"{count('res.partner',[('is_technician','=',True)])}"),
    ("العقارات",                f"{count('property.property')}  (فلل + شقق + مكاتب + مستودع + محلات)"),
    ("عقود الإيجار",            f"{count('property.tenancy')}  (٨ نشطة، ١ مؤكد، ١ مسودة، ١ منتهي)"),
    ("دفعات الإيجار",           f"{count('sa.rent.payment')}"),
    ("المعاينات",               f"{count('sa.property.inspection')}  (٣ موقعة، ١ مكتملة، ١ مسودة)"),
    ("طلبات الصيانة",           f"{count('sa.maintenance.request')}  (متنوعة الحالات)"),
    ("أوامر العمل",             f"{count('sa.maintenance.work_order')}  (٢ منجزة، ٢ مجدولة، ١ قيد التنفيذ)"),
    ("عقود الصيانة",            f"{count('sa.maintenance.contract')}  (تكييف + سباكة)"),
    ("عمولات الوسطاء",          f"{count('sa.broker.commission')}  (جميعها مؤكدة ومدفوعة)"),
    ("عقود إيجار ECRS",         f"{count('ejar.contract')}  (draft → building → ready → submitted → approved → rejected)"),
    ("أطراف عقود إيجار",        f"{count('ejar.contract.party')}"),
    ("وحدات عقود إيجار",        f"{count('ejar.contract.unit')}"),
    ("سجلات API إيجار",         f"{count('ejar.sync.log')}"),
    ("توثيق الهوية",            f"{count('sa.user.verification')}  (٤ موثَّق، ٢ مقدَّم، ٢ مسودة/مرفوض)"),
    ("وثائق المستخدمين",        f"{count('sa.user.document')}"),
    ("طلبات CRM",               f"{count('sa.crm.lead')}  (٦ مفتوحة، ٢ فاز، ٢ خسر)"),
    ("جولات ميدانية",           f"{count('sa.crm.showing')}"),
    ("حجوزات CRM",              f"{count('sa.crm.reservation')}  (مسودة، محجوزة، منتهية، تحويل)"),
    ("المستخدمون",              "23  (كلمة المرور: demo)"),
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
