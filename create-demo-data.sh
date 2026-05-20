#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${ODOO_DB:-demodb}"
COMPOSE="$(bash "$SCRIPT_DIR/.compose")"

cd "$SCRIPT_DIR"

echo "=========================================="
echo "  تحميل البيانات التجريبية ← $DB"
echo "  Loading Demo Data → $DB"
echo "=========================================="
echo ""

# ── Guard ──────────────────────────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^odoo17$"; then
    echo "ERROR: الحاويات غير مشغّلة. Odoo containers are not running."
    exit 1
fi

DB_EXISTS=$(docker exec odoo17-db psql -U odoo17 -d postgres -lqt 2>/dev/null \
    | cut -d'|' -f1 | tr -d ' ' | grep -x "$DB" || true)
if [ "$DB_EXISTS" != "$DB" ]; then
    echo "ERROR: قاعدة البيانات '$DB' غير موجودة. Database not found. Run ./create-demodb.sh first."
    exit 1
fi

echo "جارٍ تحميل البيانات... (Seeding data — 1-2 minutes)"
echo ""

$COMPOSE run --rm -T web odoo shell -d "$DB" << 'PYEOF'
import datetime
today = datetime.date.today()
ago   = lambda d: today - datetime.timedelta(days=d)
ahead = lambda d: today + datetime.timedelta(days=d)
dt    = lambda d, h=9: datetime.datetime.combine(d, datetime.time(h, 0))

# ══════════════════════════════════════════════════════════════════════════
# 0 — Helpers
# ══════════════════════════════════════════════════════════════════════════
SAR     = env['res.currency'].search([('name','=','SAR')], limit=1)
company = env['res.company'].search([], limit=1)
SA      = env['res.country'].search([('code','=','SA')], limit=1)

def region(code):
    return env['sa.region'].search([('code','=',code)], limit=1)
def city_sa(name):
    return env['sa.city'].search([('name','ilike',name)], limit=1)

r_riyadh = region('RUH') or env['sa.region'].search([], limit=1)
r_jeddah = region('MKH') or r_riyadh   # Jeddah is in Makkah region
r_dammam = region('EAS') or r_riyadh   # Eastern Province

c_riyadh = city_sa('الرياض') or env['sa.city'].search([], limit=1)
c_jeddah = city_sa('جدة')    or c_riyadh
c_dammam = city_sa('الدمام') or c_riyadh

# ══════════════════════════════════════════════════════════════════════════
# 0b — ملف الوساطة وبيانات إيجار  (Ejar Brokerage Profile + Credentials)
# ══════════════════════════════════════════════════════════════════════════
print("إعداد ملف الوساطة وبيانات إيجار... (Setting up brokerage profile...)")

params = env['ir.config_parameter'].sudo()
params.set_param('ejar.api.key.company_%d' % company.id, 'PLACEHOLDER_API_KEY')
params.set_param('ejar.api.secret.company_%d' % company.id, 'PLACEHOLDER_API_SECRET')
params.set_param('ejar.api.environment.company_%d' % company.id, 'uat')

ejar_profile = env['ejar.brokerage.profile'].search([('company_id', '=', company.id)], limit=1)
if not ejar_profile:
    ejar_profile = env['ejar.brokerage.profile'].create({
        'company_id':             company.id,
        'office_name_ar':         'شركة بروبزا للوساطة العقارية',
        'office_name_en':         'Propza Real Estate Brokerage',
        'cr_number':              '1000000001',
        'unified_number':         '1000000001',
        'license_number':         'FB-LICENSE-001',
        'license_expiry':         str(ahead(365)),
        'vat_number':             '300000000000001',
        'national_address_code':  'RIYD0001',
        'building_number':        '1234',
        'street_ar':              'شارع الملك عبدالعزيز',
        'district_ar':            'حي العليا',
        'sa_region_id':           r_riyadh.id,
        'sa_city_id':             c_riyadh.id,
        'postal_code':            '12211',
        'is_verified':            False,
    })

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 1 — ملاك العقارات  (Property Owners)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الملاك... (Creating owners...)")

owner1 = env['res.partner'].create({
    'name':              'محمد بن عبدالله القحطاني',
    'company_type':      'person',
    'is_property_owner': True,
    'sa_id_type':        'national_id',
    'sa_national_id':    '1023456789',
    'sa_iban':           'SA0380000000608010167519',
    'phone':             '+966501234001',
    'email':             'm.qahtani@propza-demo.sa',
    'street':            'شارع الإمام سعود',
    'city':              'الرياض',
    'country_id':        SA.id,
})

owner2 = env['res.partner'].create({
    'name':              'فاطمة بنت سعد الزهراني',
    'company_type':      'person',
    'is_property_owner': True,
    'sa_id_type':        'national_id',
    'sa_national_id':    '1056789012',
    'sa_iban':           'SA4420000001234567891234',
    'phone':             '+966502234002',
    'email':             'f.zahrani@propza-demo.sa',
    'street':            'شارع التحلية',
    'city':              'جدة',
    'country_id':        SA.id,
})

owner3 = env['res.partner'].create({
    'name':              'سالم بن أحمد العتيبي',
    'company_type':      'person',
    'is_property_owner': True,
    'sa_id_type':        'national_id',
    'sa_national_id':    '1078901234',
    'sa_iban':           'SA6220000003456789012345',
    'phone':             '+966503234003',
    'email':             's.otaibi@propza-demo.sa',
    'city':              'الدمام',
    'country_id':        SA.id,
})

owner4 = env['res.partner'].create({
    'name':              'شركة الواحة للتطوير العقاري',
    'company_type':      'company',
    'is_property_owner': True,
    'sa_cr_number':      '1010345678',
    'sa_iban':           'SA1020000005678901234567',
    'phone':             '+966114001400',
    'email':             'info@alwaha-re.sa',
    'street':            'طريق الملك فهد',
    'city':              'الرياض',
    'country_id':        SA.id,
    'website':           'https://alwaha-re.sa',
})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 2 — المستأجرون  (Tenants)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء المستأجرين... (Creating tenants...)")

tenant1 = env['res.partner'].create({
    'name':           'خالد بن عبدالله الراشدي',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1098765432',
    'phone':          '+966503100001',
    'email':          'k.rashidi@propza-demo.sa',
    'country_id':     SA.id,
})

tenant2 = env['res.partner'].create({
    'name':           'عمر محمد الفاروق',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1034512678',
    'phone':          '+966503100002',
    'email':          'o.farouq@propza-demo.sa',
    'country_id':     SA.id,
})

tenant3 = env['res.partner'].create({
    'name':           'نورة سعد الحمدان',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1067891234',
    'phone':          '+966503100003',
    'email':          'n.hamdan@propza-demo.sa',
    'country_id':     SA.id,
})

tenant4 = env['res.partner'].create({
    'name':           'عائشة أحمد مالك',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'iqama',
    'sa_national_id': '2123456789',
    'sa_id_expiry':   str(ahead(180)),
    'phone':          '+966503100004',
    'email':          'a.malik@propza-demo.sa',
    'country_id':     SA.id,
})

tenant5 = env['res.partner'].create({
    'name':           'أحمد يوسف العمري',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1055443322',
    'phone':          '+966503100005',
    'email':          'a.omari@propza-demo.sa',
    'country_id':     SA.id,
})

tenant6 = env['res.partner'].create({
    'name':           'سارة عبدالرحمن الدوسري',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1066778899',
    'phone':          '+966503100006',
    'email':          's.dosari@propza-demo.sa',
    'country_id':     SA.id,
})

tenant7 = env['res.partner'].create({
    'name':           'محمد علي الشهري',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1077889900',
    'phone':          '+966503100007',
    'email':          'm.shehri@propza-demo.sa',
    'country_id':     SA.id,
})

tenant8 = env['res.partner'].create({
    'name':           'ريم عبدالعزيز القرني',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1088990011',
    'phone':          '+966503100008',
    'email':          'r.qarni@propza-demo.sa',
    'country_id':     SA.id,
})

tenant9 = env['res.partner'].create({
    'name':           'فيصل محمد الغامدي',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1099887766',
    'phone':          '+966503100009',
    'email':          'f.ghamdi@propza-demo.sa',
    'country_id':     SA.id,
})

tenant10 = env['res.partner'].create({
    'name':           'لمى عبدالله الزهراني',
    'company_type':   'person',
    'is_tenant':      True,
    'sa_id_type':     'national_id',
    'sa_national_id': '1044332211',
    'phone':          '+966503100010',
    'email':          'l.zahrani@propza-demo.sa',
    'country_id':     SA.id,
})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 3 — الوسطاء العقاريون  (Brokers)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الوسطاء... (Creating brokers...)")

broker1 = env['res.partner'].create({
    'name':           'شركة الوافر للوساطة العقارية',
    'company_type':   'company',
    'is_broker':      True,
    'broker_license': 'BRK-2024-00123',
    'sa_cr_number':   '4030234567',
    'phone':          '+966122345678',
    'email':          'info@alwafer-broker.sa',
    'city':           'الرياض',
    'country_id':     SA.id,
})

broker2 = env['res.partner'].create({
    'name':           'طارق بن محمد الغامدي',
    'company_type':   'person',
    'is_broker':      True,
    'broker_license': 'BRK-2024-00456',
    'sa_id_type':     'national_id',
    'sa_national_id': '1045678901',
    'phone':          '+966504200002',
    'email':          't.ghamdi@broker.sa',
    'country_id':     SA.id,
})

broker3 = env['res.partner'].create({
    'name':           'هند بنت سليمان العمودي',
    'company_type':   'person',
    'is_broker':      True,
    'broker_license': 'BRK-2024-00789',
    'sa_id_type':     'national_id',
    'sa_national_id': '1099001122',
    'phone':          '+966504200003',
    'email':          'h.amodi@broker.sa',
    'country_id':     SA.id,
})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 4 — الفنيون والمقاولون  (Technicians & Contractors)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء الفنيين... (Creating technicians...)")

plumbing_skill   = env['sa.maintenance.skill'].search([('code','=','PLM')], limit=1)
electrical_skill = env['sa.maintenance.skill'].search([('code','=','ELC')], limit=1)
ac_skill         = env['sa.maintenance.skill'].search([('code','=','ACA')], limit=1)
painting_skill   = env['sa.maintenance.skill'].search([('code','=','PNT')], limit=1)
carpentry_skill  = env['sa.maintenance.skill'].search([('code','=','CRP')], limit=1)

tech1 = env['res.partner'].create({
    'name':              'حسن البحار للسباكة والصرف الصحي',
    'company_type':      'company',
    'is_technician':     True,
    'sa_cr_number':      '1010556677',
    'sa_hourly_rate':    80.0,
    'sa_call_out_fee':   50.0,
    'sa_response_hours': 4,
    'sa_skill_ids':      [(6, 0, plumbing_skill.ids)] if plumbing_skill else [],
    'phone':             '+966112345601',
    'email':             'info@hassan-plumbing.sa',
    'city':              'الرياض',
    'country_id':        SA.id,
})

tech2 = env['res.partner'].create({
    'name':              'شركة أحمد للتقنية الكهربائية والتكييف',
    'company_type':      'company',
    'is_technician':     True,
    'sa_cr_number':      '1010667788',
    'sa_hourly_rate':    100.0,
    'sa_call_out_fee':   75.0,
    'sa_response_hours': 2,
    'sa_skill_ids':      [(6, 0, (electrical_skill + ac_skill).ids)],
    'phone':             '+966114502000',
    'email':             'support@ahmad-tech.sa',
    'city':              'الرياض',
    'country_id':        SA.id,
})

tech3 = env['res.partner'].create({
    'name':              'عبدالله الحربي للدهانات والأعمال الخشبية',
    'company_type':      'person',
    'is_technician':     True,
    'sa_id_type':        'national_id',
    'sa_national_id':    '1033221100',
    'sa_hourly_rate':    65.0,
    'sa_call_out_fee':   30.0,
    'sa_response_hours': 6,
    'sa_skill_ids':      [(6, 0, (painting_skill + carpentry_skill).ids)],
    'phone':             '+966505400003',
    'email':             'a.harbi@handyman.sa',
    'country_id':        SA.id,
})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 5 — العقارات  (Properties — 12 units)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء العقارات... (Creating properties...)")

def prop(vals):
    return env['property.property'].create(vals)

# ── فلل (Villas) ───────────────────────────────────────────────────────────
prop1 = prop({
    'name':                'فيلا الروضة ١٢',
    'flat_name':           'حي الروضة – شارع الإمام سعود',
    'description':         'فيلا فاخرة من طابقين بحديقة خاصة ومسبح. تقع في حي الروضة الراقي.',
    'property_type':       'residential',
    'sa_property_subtype': 'villa',
    'owner_partner_id':    owner1.id,
    'rent_amount':         80000.0,
    'deposit_amount':      80000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي الروضة',
    'sa_street':           'شارع الإمام سعود',
    'sa_building_no':      '12',
    'sa_postal_code':      '12241',
    'sa_area_sqm':         450.0,
    'sa_rooms':            5,
    'sa_bathrooms':        4,
    'sa_parking':          2,
    'sa_pool':             True,
    'sa_garden':           True,
    'sa_furnished':        'unfurnished',
    'sa_condition':        'excellent',
    'sa_year_built':       2018,
    'sa_deed_number':      'و-٢٠١٨-رض-٠٠١٢٣٤',
})

prop2 = prop({
    'name':                'فيلا النزهة ٨',
    'flat_name':           'حي النزهة – جدة',
    'description':         'فيلا واسعة مع إطلالة على الحديقة، مناسبة للعائلات الكبيرة.',
    'property_type':       'residential',
    'sa_property_subtype': 'villa',
    'owner_partner_id':    owner2.id,
    'rent_amount':         95000.0,
    'deposit_amount':      95000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_jeddah.id,
    'sa_city_id':          c_jeddah.id,
    'sa_district':         'حي النزهة',
    'sa_street':           'شارع الأمير سلطان',
    'sa_building_no':      '8',
    'sa_area_sqm':         520.0,
    'sa_rooms':            6,
    'sa_bathrooms':        5,
    'sa_parking':          3,
    'sa_pool':             True,
    'sa_furnished':        'semi',
    'sa_condition':        'excellent',
    'sa_year_built':       2020,
})

prop3 = prop({
    'name':                'فيلا النرجس ٣',
    'flat_name':           'حي النرجس – الرياض',
    'description':         'فيلا حديثة في حي النرجس الهادئ، مجهزة بالكامل وجاهزة للسكن.',
    'property_type':       'residential',
    'sa_property_subtype': 'villa',
    'owner_partner_id':    owner4.id,
    'rent_amount':         110000.0,
    'deposit_amount':      110000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي النرجس',
    'sa_building_no':      '3',
    'sa_area_sqm':         600.0,
    'sa_rooms':            6,
    'sa_bathrooms':        5,
    'sa_parking':          3,
    'sa_pool':             True,
    'sa_garden':           True,
    'sa_furnished':        'fully',
    'sa_condition':        'excellent',
    'sa_year_built':       2022,
    'sa_deed_number':      'و-٢٠٢٢-رض-٠٠٤٥٦٧',
})

# ── شقق – الرياض (Riyadh Apartments) ──────────────────────────────────────
prop4 = prop({
    'name':                'شقة العليا – ٣ب',
    'flat_name':           'برج العليا، الدور ٣ – حي العليا',
    'description':         'شقة ثلاث غرف في برج راقٍ بحي العليا، قريبة من الخدمات.',
    'property_type':       'residential',
    'sa_property_subtype': 'apartment',
    'owner_partner_id':    owner1.id,
    'rent_amount':         45000.0,
    'deposit_amount':      22500.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي العليا',
    'sa_street':           'طريق الملك فهد',
    'sa_floor_number':     3,
    'sa_total_floors':     10,
    'sa_area_sqm':         140.0,
    'sa_rooms':            3,
    'sa_bathrooms':        2,
    'sa_elevator':         True,
    'sa_furnished':        'semi',
    'sa_condition':        'good',
    'sa_year_built':       2015,
})

prop5 = prop({
    'name':                'شقة الملقا – ٧أ',
    'flat_name':           'برج الملقا، الدور ٧ – حي الملقا',
    'description':         'شقة فسيحة في حي الملقا، قريبة من المدارس والمجمعات التجارية.',
    'property_type':       'residential',
    'sa_property_subtype': 'apartment',
    'owner_partner_id':    owner1.id,
    'rent_amount':         48000.0,
    'deposit_amount':      24000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي الملقا',
    'sa_floor_number':     7,
    'sa_total_floors':     15,
    'sa_area_sqm':         160.0,
    'sa_rooms':            3,
    'sa_bathrooms':        2,
    'sa_elevator':         True,
    'sa_furnished':        'unfurnished',
    'sa_condition':        'good',
})

# ── شقق – جدة والدمام (Jeddah & Dammam Apartments) ───────────────────────
prop6 = prop({
    'name':                'شقة الحمراء – ١٥',
    'flat_name':           'عمارة الحمراء، الدور ٢ – جدة',
    'description':         'شقة مطلة على الشارع في حي الحمراء الراقي بجدة.',
    'property_type':       'residential',
    'sa_property_subtype': 'apartment',
    'owner_partner_id':    owner2.id,
    'rent_amount':         42000.0,
    'deposit_amount':      21000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_jeddah.id,
    'sa_city_id':          c_jeddah.id,
    'sa_district':         'حي الحمراء',
    'sa_floor_number':     2,
    'sa_area_sqm':         130.0,
    'sa_rooms':            3,
    'sa_bathrooms':        2,
    'sa_furnished':        'semi',
    'sa_condition':        'good',
})

prop7 = prop({
    'name':                'شقة المرجان – ٢٢',
    'flat_name':           'برج المرجان، الدور ٤ – الدمام',
    'description':         'شقة حديثة في حي المرجان بالدمام، قريبة من الخدمات.',
    'property_type':       'residential',
    'sa_property_subtype': 'apartment',
    'owner_partner_id':    owner3.id,
    'rent_amount':         38000.0,
    'deposit_amount':      19000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_dammam.id,
    'sa_city_id':          c_dammam.id,
    'sa_district':         'حي المرجان',
    'sa_floor_number':     4,
    'sa_area_sqm':         120.0,
    'sa_rooms':            3,
    'sa_bathrooms':        2,
    'sa_elevator':         True,
    'sa_furnished':        'unfurnished',
    'sa_condition':        'good',
    'sa_year_built':       2019,
})

prop8 = prop({
    'name':                'شقة الدانة – ١٠د',
    'flat_name':           'عمارة الدانة، الدور ١ – الدمام',
    'description':         'شقة بسعر مناسب في حي الدانة، مناسبة للأفراد والعائلات الصغيرة.',
    'property_type':       'residential',
    'sa_property_subtype': 'apartment',
    'owner_partner_id':    owner3.id,
    'rent_amount':         35000.0,
    'deposit_amount':      17500.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_dammam.id,
    'sa_city_id':          c_dammam.id,
    'sa_district':         'حي الدانة',
    'sa_floor_number':     1,
    'sa_area_sqm':         110.0,
    'sa_rooms':            2,
    'sa_bathrooms':        2,
    'sa_furnished':        'unfurnished',
    'sa_condition':        'good',
})

# ── مكاتب (Offices) ────────────────────────────────────────────────────────
prop9 = prop({
    'name':                'مكتب بيزنس باي – ٢٠١',
    'flat_name':           'برج بيزنس باي، الدور ٢٠ – حي العليا',
    'description':         'مكتب تنفيذي بإطلالة بانورامية على الرياض. مجهز بالكامل، مناسب للشركات.',
    'property_type':       'commercial',
    'sa_property_subtype': 'office',
    'owner_partner_id':    owner4.id,
    'rent_amount':         120000.0,
    'deposit_amount':      60000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي العليا',
    'sa_street':           'طريق الملك فهد',
    'sa_floor_number':     20,
    'sa_total_floors':     30,
    'sa_area_sqm':         280.0,
    'sa_elevator':         True,
    'sa_furnished':        'fully',
    'sa_condition':        'excellent',
    'sa_year_built':       2022,
})

prop10 = prop({
    'name':                'مكتب طريق الملك فهد – أ',
    'flat_name':           'مجمع الملك فهد التجاري، الدور ٥',
    'description':         'مكتب نصف مجهز في موقع استراتيجي على طريق الملك فهد.',
    'property_type':       'commercial',
    'sa_property_subtype': 'office',
    'owner_partner_id':    owner4.id,
    'rent_amount':         85000.0,
    'deposit_amount':      42500.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي الورود',
    'sa_floor_number':     5,
    'sa_area_sqm':         200.0,
    'sa_elevator':         True,
    'sa_furnished':        'semi',
    'sa_condition':        'good',
})

# ── محل تجاري ومستودع  (Shop & Warehouse) ─────────────────────────────────
prop11 = prop({
    'name':                'محل الشميسي التجاري – ٥',
    'flat_name':           'مجمع الشميسي التجاري، المحل ٥',
    'description':         'محل تجاري في مجمع الشميسي، يُصلح للبيع بالتجزئة والمطاعم.',
    'property_type':       'commercial',
    'sa_property_subtype': 'shop',
    'owner_partner_id':    owner3.id,
    'rent_amount':         55000.0,
    'deposit_amount':      55000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'حي الشميسي',
    'sa_area_sqm':         90.0,
    'sa_condition':        'good',
    'sa_year_built':       2014,
})

prop12 = prop({
    'name':                'مستودع الرياض الصناعي – ٥',
    'flat_name':           'المدينة الصناعية الثانية، مستودع ٥',
    'description':         'مستودع واسع في المدينة الصناعية الثانية بالرياض، مناسب للتخزين والتوزيع.',
    'property_type':       'commercial',
    'sa_property_subtype': 'warehouse',
    'owner_partner_id':    owner4.id,
    'rent_amount':         60000.0,
    'deposit_amount':      60000.0,
    'currency_id':         SAR.id,
    'sa_region_id':        r_riyadh.id,
    'sa_city_id':          c_riyadh.id,
    'sa_district':         'المدينة الصناعية الثانية',
    'sa_area_sqm':         800.0,
    'sa_condition':        'good',
    'sa_year_built':       2016,
})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 6 — عقود الإيجار  (Tenancies — 9 contracts)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود الإيجار... (Creating tenancies...)")

def tenancy(vals, confirm=True, start=True):
    t = env['property.tenancy'].create(vals)
    if confirm: t.action_confirm()
    if start:   t.action_start()
    return t

# ع١ — خالد في فيلا الروضة: قيد التشغيل منذ ٦ أشهر، ربع سنوي
t1 = tenancy({
    'property_id':         prop1.id,
    'partner_id':          tenant1.id,
    'start_date':          str(ago(180)),
    'end_date':            str(ahead(185)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         80000.0,
    'deposit_amount':      80000.0,
    'currency_id':         SAR.id,
    'payment_method':        'sadad',
    'sa_contract_type':      'residential',
    'sa_payment_schedule':   'quarterly',
    'ejar_payment_schedule': 'quarterly',
    'sa_broker_id':          broker1.id,
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1098765432',
    'sublease_allowed':      False,
    'auto_renew':            True,
    'renewal_period_months': 12,
    'renewal_rent_increase_pct': 0.0,
})

# ع٢ — عمر في شقة العليا: قيد التشغيل منذ ٣ أشهر، ربع سنوي
t2 = tenancy({
    'property_id':         prop4.id,
    'partner_id':          tenant2.id,
    'start_date':          str(ago(90)),
    'end_date':            str(ahead(275)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         45000.0,
    'deposit_amount':      22500.0,
    'currency_id':         SAR.id,
    'payment_method':        'bank_transfer',
    'sa_contract_type':      'residential',
    'sa_payment_schedule':   'quarterly',
    'ejar_payment_schedule': 'quarterly',
    'sa_broker_id':          broker2.id,
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1034512678',
    'sublease_allowed':      False,
})

# ع٣ — نورة في شقة الملقا: قيد التشغيل، دفعة متأخرة، شهري
t3 = tenancy({
    'property_id':         prop5.id,
    'partner_id':          tenant3.id,
    'start_date':          str(ago(120)),
    'end_date':            str(ahead(245)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         48000.0,
    'deposit_amount':      24000.0,
    'currency_id':         SAR.id,
    'payment_method':        'mada',
    'sa_contract_type':      'residential',
    'sa_payment_schedule':   'monthly',
    'ejar_payment_schedule': 'monthly',
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1067891234',
    'sublease_allowed':      False,
})

# ع٤ — عائشة في شقة الحمراء: تنتهي خلال ٢٨ يومًا، سنوي
t4 = tenancy({
    'property_id':         prop6.id,
    'partner_id':          tenant4.id,
    'start_date':          str(ago(337)),
    'end_date':            str(ahead(28)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         42000.0,
    'deposit_amount':      21000.0,
    'currency_id':         SAR.id,
    'payment_method':        'bank_transfer',
    'sa_contract_type':      'residential',
    'sa_payment_schedule':   'annual',
    'ejar_payment_schedule': 'annual',
    'sa_broker_id':          broker3.id,
    'tenant_id_type':        'iqama',
    'tenant_national_id':    '2123456789',
    'sublease_allowed':      False,
    'auto_renew':            True,
    'renewal_period_months': 12,
    'renewal_rent_increase_pct': 0.0,
})

# ع٥ — أحمد في مكتب بيزنس باي: تجاري، ١٢ شهرًا، ربع سنوي
t5 = tenancy({
    'property_id':         prop9.id,
    'partner_id':          tenant5.id,
    'start_date':          str(ago(365)),
    'end_date':            str(today),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         120000.0,
    'deposit_amount':      60000.0,
    'currency_id':         SAR.id,
    'payment_method':        'bank_transfer',
    'sa_contract_type':      'commercial',
    'sa_payment_schedule':   'quarterly',
    'ejar_payment_schedule': 'quarterly',
    'sa_broker_id':          broker1.id,
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1055443322',
    'sublease_allowed':      False,
    'auto_renew':            True,
    'renewal_period_months': 12,
    'renewal_rent_increase_pct': 0.0,
})

# ع٦ — سارة في شقة المرجان: منذ شهرين، شهري
t6 = tenancy({
    'property_id':         prop7.id,
    'partner_id':          tenant6.id,
    'start_date':          str(ago(60)),
    'end_date':            str(ahead(305)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         38000.0,
    'deposit_amount':      19000.0,
    'currency_id':         SAR.id,
    'payment_method':        'sadad',
    'sa_contract_type':      'residential',
    'sa_payment_schedule':   'monthly',
    'ejar_payment_schedule': 'monthly',
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1066778899',
    'sublease_allowed':      False,
})

# ع٧ — محمد في المحل التجاري: تجاري، ٨ أشهر، نصف سنوي
t7 = tenancy({
    'property_id':         prop11.id,
    'partner_id':          tenant7.id,
    'start_date':          str(ago(240)),
    'end_date':            str(ahead(125)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         55000.0,
    'deposit_amount':      55000.0,
    'currency_id':         SAR.id,
    'payment_method':        'cheque',
    'sa_contract_type':      'commercial',
    'sa_payment_schedule':   'semi_annual',
    'ejar_payment_schedule': 'semi_annual',
    'sa_broker_id':          broker3.id,
    'tenant_id_type':        'national_id',
    'tenant_national_id':    '1077889900',
    'sublease_allowed':      False,
})

# ع٨ — ريم في شقة الدانة: مؤكد لم يبدأ بعد
t8 = tenancy({
    'property_id':         prop8.id,
    'partner_id':          tenant8.id,
    'start_date':          str(ahead(15)),
    'end_date':            str(ahead(380)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         35000.0,
    'deposit_amount':      17500.0,
    'currency_id':         SAR.id,
    'payment_method':      'bank_transfer',
    'sa_contract_type':    'residential',
    'sa_payment_schedule': 'quarterly',
    'tenant_id_type':      'national_id',
    'tenant_national_id':  '1088990011',
}, confirm=True, start=False)   # مؤكد فقط

# ع٩ — فيلا النرجس: مسودة لمستأجر مقبل
t9 = tenancy({
    'property_id':         prop3.id,
    'partner_id':          tenant1.id,
    'start_date':          str(ahead(45)),
    'end_date':            str(ahead(410)),
    'duration':            12,
    'interval_type':       'months',
    'rent_amount':         110000.0,
    'deposit_amount':      110000.0,
    'currency_id':         SAR.id,
    'payment_method':      'bank_transfer',
    'sa_contract_type':    'residential',
    'sa_payment_schedule': 'semi_annual',
}, confirm=False, start=False)  # مسودة

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 7 — دفعات الإيجار  (Rent Payments — 37 records)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء دفعات الإيجار... (Creating rent payments...)")

def pay(ten, due, amount, state='pending', paid_on=None, method=None,
        ptype='rent', label=''):
    v = {
        'tenancy_id':   ten.id,
        'due_date':     str(due),
        'amount':       amount,
        'payment_type': ptype,
        'state':        state,
        'period_label': label,
    }
    if paid_on:
        v['payment_date'] = str(paid_on)
        v['amount_paid']  = amount
    if method:
        v['payment_method'] = method
    return env['sa.rent.payment'].create(v)

def deposit(ten, on, amount, method='bank_transfer'):
    pay(ten, on, amount, 'paid', on, method, 'deposit', 'وديعة تأمين')

# ع١ — خالد، ربع سنوي ٢٠،٠٠٠
deposit(t1, ago(180), 80000.0, 'sadad')
pay(t1, ago(180), 20000.0, 'paid', ago(178), 'sadad', label='الربع الأول – يناير ٢٠٢٦')
pay(t1, ago(90),  20000.0, 'paid', ago(88),  'sadad', label='الربع الثاني – أبريل ٢٠٢٦')
pay(t1, ahead(0), 20000.0, 'pending', label='الربع الثالث – يوليو ٢٠٢٦')
pay(t1, ahead(90),20000.0, 'pending', label='الربع الرابع – أكتوبر ٢٠٢٦')

# ع٢ — عمر، ربع سنوي ١١،٢٥٠
deposit(t2, ago(90), 22500.0, 'bank_transfer')
pay(t2, ago(90),   11250.0, 'paid',    ago(88), 'bank_transfer', label='الربع الأول')
pay(t2, ahead(0),  11250.0, 'pending', label='الربع الثاني')
pay(t2, ahead(90), 11250.0, 'pending', label='الربع الثالث')
pay(t2, ahead(180),11250.0, 'pending', label='الربع الرابع')

# ع٣ — نورة، شهري ٤،٠٠٠ – الشهر الرابع متأخر
deposit(t3, ago(120), 24000.0, 'mada')
monthly = round(48000.0 / 12, 2)
months_n = [
    (ago(120), 'paid',    ago(118), 'الشهر الأول'),
    (ago(90),  'paid',    ago(88),  'الشهر الثاني'),
    (ago(60),  'paid',    ago(58),  'الشهر الثالث'),
    (ago(30),  'overdue', None,     'الشهر الرابع'),
    (today,    'pending', None,     'الشهر الخامس'),
]
for due, st, pd, lbl in months_n:
    pay(t3, due, monthly, st, pd, 'mada' if pd else None, label=lbl)

# ع٤ — عائشة، سنوي، كامل مدفوع
deposit(t4, ago(337), 21000.0, 'bank_transfer')
pay(t4, ago(337), 42000.0, 'paid', ago(335), 'bank_transfer', label='الإيجار السنوي ٢٠٢٥–٢٠٢٦')

# ع٥ — أحمد، ربع سنوي ٣٠،٠٠٠ – أربعة أرباع مدفوعة
deposit(t5, ago(365), 60000.0, 'bank_transfer')
quarters5 = [
    (ago(365), 'الربع الأول'),
    (ago(275), 'الربع الثاني'),
    (ago(185), 'الربع الثالث'),
    (ago(95),  'الربع الرابع'),
]
for due, lbl in quarters5:
    pay(t5, due, 30000.0, 'paid', due + datetime.timedelta(2), 'bank_transfer', label=lbl)

# ع٦ — سارة، شهري ٣،١٦٧
deposit(t6, ago(60), 19000.0, 'sadad')
monthly6 = round(38000.0 / 12, 2)
months_s = [
    (ago(60), 'paid', ago(58), 'الشهر الأول'),
    (ago(30), 'paid', ago(28), 'الشهر الثاني'),
    (today,   'pending', None, 'الشهر الثالث'),
]
for due, st, pd, lbl in months_s:
    pay(t6, due, monthly6, st, pd, 'sadad' if pd else None, label=lbl)

# ع٧ — محمد، نصف سنوي ٢٧،٥٠٠
deposit(t7, ago(240), 55000.0, 'cheque')
pay(t7, ago(240), 27500.0, 'paid',    ago(238), 'cheque', label='النصف الأول')
pay(t7, ahead(125-240+365),27500.0, 'pending', label='النصف الثاني')

# ع٨ — ريم، وديعة فقط (لم تبدأ بعد)
deposit(t8, today, 17500.0, 'bank_transfer')

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 8 — معاينات العقارات  (Inspections — 5 records)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء المعاينات... (Creating inspections...)")

def inspection(vals, complete=False, sign=False):
    ins = env['sa.property.inspection'].create(vals)
    if complete or sign: ins.action_complete()
    if sign:             ins.action_sign()
    return ins

insp1 = inspection({
    'property_id':      prop1.id,
    'tenancy_id':       t1.id,
    'inspection_type':  'move_in',
    'inspection_date':  str(ago(180)),
    'general_condition':'excellent',
    'general_notes':    'العقار في حالة ممتازة. جميع المرافق تعمل بكفاءة. الحديقة والمسبح نظيفان.',
    'line_ids': [
        (0,0,{'room':'living_room','item':'أجهزة التكييف المركزي',  'condition':'good',  'notes':'٣ وحدات، جميعها تعمل بكفاءة'}),
        (0,0,{'room':'kitchen',    'item':'خزائن المطبخ والرخام',   'condition':'good',  'notes':'لا يوجد تلف'}),
        (0,0,{'room':'bathroom',   'item':'تجهيزات السباكة',        'condition':'good',  'notes':'لا يوجد تسرب'}),
        (0,0,{'room':'exterior',   'item':'الحديقة والمسبح',        'condition':'good',  'notes':'صيانة جيدة'}),
        (0,0,{'room':'master',     'item':'الأرضيات والجدران',      'condition':'good'}),
    ],
}, complete=True, sign=True)

insp2 = inspection({
    'property_id':      prop6.id,
    'tenancy_id':       t4.id,
    'inspection_type':  'move_in',
    'inspection_date':  str(ago(337)),
    'general_condition':'good',
    'general_notes':    'الشقة في حالة جيدة مع بعض التآكل الطفيف على الجدران.',
    'line_ids': [
        (0,0,{'room':'living_room','item':'الجدران والدهان',  'condition':'minor_wear','damage_cost':800.0, 'notes':'بعض الخدوش الطفيفة'}),
        (0,0,{'room':'bedroom',    'item':'خزائن غرفة النوم', 'condition':'good'}),
        (0,0,{'room':'kitchen',    'item':'الأجهزة المنزلية', 'condition':'good',  'notes':'تعمل بشكل طبيعي'}),
        (0,0,{'room':'bathroom',   'item':'البلاط والتجهيزات','condition':'good'}),
    ],
}, complete=True, sign=True)

insp3 = inspection({
    'property_id':      prop6.id,
    'tenancy_id':       t4.id,
    'inspection_type':  'interim',
    'inspection_date':  str(today),
    'general_condition':'fair',
    'general_notes':    'معاينة مرحلية قبيل انتهاء العقد. المستأجرة تستعد للمغادرة. الجدران تحتاج إعادة طلاء.',
    'line_ids': [
        (0,0,{'room':'living_room','item':'الجدران والدهان', 'condition':'damaged',    'damage_cost':1500.0,'notes':'يلزم إعادة طلاء كاملة'}),
        (0,0,{'room':'bathroom',   'item':'البلاط',          'condition':'minor_wear', 'damage_cost':400.0}),
        (0,0,{'room':'kitchen',    'item':'الرخام والأحواض', 'condition':'good'}),
    ],
})

insp4 = inspection({
    'property_id':      prop4.id,
    'tenancy_id':       t2.id,
    'inspection_type':  'move_in',
    'inspection_date':  str(ago(90)),
    'general_condition':'good',
    'general_notes':    'الشقة نظيفة وجاهزة للسكن. تم استلامها بحالة جيدة.',
    'line_ids': [
        (0,0,{'room':'living_room','item':'الأرضيات والسجادة', 'condition':'good'}),
        (0,0,{'room':'kitchen',    'item':'المطبخ والأجهزة',   'condition':'good',  'notes':'جهاز الغسيل جديد'}),
        (0,0,{'room':'bathroom',   'item':'الحمام الرئيسي',    'condition':'good'}),
    ],
}, complete=True)

insp5 = inspection({
    'property_id':      prop9.id,
    'tenancy_id':       t5.id,
    'inspection_type':  'move_in',
    'inspection_date':  str(ago(365)),
    'general_condition':'excellent',
    'general_notes':    'المكتب مجهز بالكامل وجاهز للعمل. التقنيات والشبكات تعمل بكفاءة عالية.',
    'line_ids': [
        (0,0,{'room':'living_room','item':'تجهيزات المكتب والأثاث',   'condition':'good'}),
        (0,0,{'room':'other',      'item':'أجهزة التكييف المركزي',    'condition':'good'}),
        (0,0,{'room':'other',      'item':'شبكة الإنترنت والاتصالات', 'condition':'good',  'notes':'١ جيجابت فايبر'}),
        (0,0,{'room':'bathroom',   'item':'دورات المياه',             'condition':'good'}),
    ],
}, complete=True, sign=True)

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 9 — طلبات الصيانة وأوامر العمل  (Maintenance — 8 requests, 4 WOs)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء طلبات الصيانة... (Creating maintenance...)")

# ص١ — عطل تكييف: قيد التنفيذ
req1 = env['sa.maintenance.request'].create({
    'property_id':        prop1.id,
    'tenancy_id':         t1.id,
    'description':        'وحدة التكييف المركزي في غرفة النوم الرئيسية لا تبرد. ترتفع درجة الحرارة عن ٢٨ درجة مئوية رغم ضبط الثيرموستات على ١٨.',
    'request_date':       str(ago(5)),
    'category':           'ac',
    'priority':           '2',
    'supplier_partner_id':tech2.id,
    'scheduled_date':     str(dt(ahead(1), 10)),
    'estimated_duration': 3.0,
    'labor_cost':         300.0,
    'materials_cost':     150.0,
    'cost_bearer':        'owner',
    'notes':              'يُرجَّح وجود تسرب في غاز التبريد. تم التبليغ من قِبل المستأجر منذ أسبوع.',
})
req1.action_approve()
req1.action_schedule()
req1.action_start()

# ص٢ — تسرب مياه: معتمد
req2 = env['sa.maintenance.request'].create({
    'property_id':        prop4.id,
    'tenancy_id':         t2.id,
    'description':        'تسرب مياه أسفل حوض المطبخ. المياه تتقطر داخل الخزانة. المستأجر وضع وعاءً مؤقتًا.',
    'request_date':       str(ago(2)),
    'category':           'plumbing',
    'priority':           '3',
    'supplier_partner_id':tech1.id,
    'scheduled_date':     str(dt(today, 9)),
    'estimated_duration': 2.0,
    'labor_cost':         200.0,
    'materials_cost':     80.0,
    'cost_bearer':        'owner',
})
req2.action_approve()

# ص٣ — أعطال كهربائية: منجزة
req3 = env['sa.maintenance.request'].create({
    'property_id':        prop9.id,
    'tenancy_id':         t5.id,
    'description':        'وميض في ثلاثة مصابيح سقف بمنطقة الاستقبال. يُشتبه في حدوث ارتفاع في التيار الكهربائي.',
    'request_date':       str(ago(7)),
    'category':           'electrical',
    'priority':           '2',
    'supplier_partner_id':tech2.id,
    'scheduled_date':     str(dt(ago(1), 14)),
    'actual_duration':    2.5,
    'labor_cost':         350.0,
    'materials_cost':     220.0,
    'cost_bearer':        'tenant',
    'notes':              'تم استبدال المصابيح الثلاثة. المشكلة حُلّت.',
})
req3.action_approve()
req3.action_schedule()
req3.action_start()
req3.action_done()

# ص٤ — قفل الباب: جديد
req4 = env['sa.maintenance.request'].create({
    'property_id':        prop5.id,
    'tenancy_id':         t3.id,
    'description':        'قفل الباب الأمامي معطل. المفتاح يدور لكن الباب لا ينفتح. المستأجرة تدخل من الباب الخلفي حاليًا.',
    'request_date':       str(today),
    'category':           'carpentry',
    'priority':           '3',
    'estimated_duration': 1.0,
    'labor_cost':         150.0,
    'materials_cost':     200.0,
    'cost_bearer':        'owner',
})
# يبقى جديدًا

# ص٥ — إعادة طلاء: معتمد
req5 = env['sa.maintenance.request'].create({
    'property_id':        prop6.id,
    'tenancy_id':         t4.id,
    'description':        'إعادة طلاء جدران غرفة المعيشة قبيل انتهاء العقد. لوحظ التلف خلال المعاينة المرحلية.',
    'request_date':       str(ago(1)),
    'category':           'painting',
    'priority':           '1',
    'supplier_partner_id':tech3.id,
    'scheduled_date':     str(dt(ahead(7), 8)),
    'estimated_duration': 8.0,
    'labor_cost':         600.0,
    'materials_cost':     400.0,
    'cost_bearer':        'tenant',
})
req5.action_approve()

# ص٦ — تلف أرضيات حمام: جديد
req6 = env['sa.maintenance.request'].create({
    'property_id':        prop7.id,
    'tenancy_id':         t6.id,
    'description':        'تلف وتشقق في بلاط حمام غرفة النوم الرئيسية. يخشى المستأجر من ضرر أكبر عند الإهمال.',
    'request_date':       str(ago(1)),
    'category':           'other',
    'priority':           '1',
    'estimated_duration': 4.0,
    'labor_cost':         400.0,
    'materials_cost':     500.0,
    'cost_bearer':        'owner',
})
# يبقى جديدًا

# ص٧ — تلف خزان المياه: مجدول
req7 = env['sa.maintenance.request'].create({
    'property_id':        prop2.id,
    'description':        'الخزان العلوي للمياه يُصدر أصواتًا غريبة وضغط الماء ضعيف في الطابق الثاني.',
    'request_date':       str(ago(3)),
    'category':           'plumbing',
    'priority':           '2',
    'supplier_partner_id':tech1.id,
    'scheduled_date':     str(dt(ahead(2), 11)),
    'estimated_duration': 3.0,
    'labor_cost':         250.0,
    'materials_cost':     300.0,
    'cost_bearer':        'owner',
})
req7.action_approve()
req7.action_schedule()

# ص٨ — صيانة حديقة ومسبح: منجزة
req8 = env['sa.maintenance.request'].create({
    'property_id':        prop1.id,
    'tenancy_id':         t1.id,
    'description':        'الصيانة الدورية للحديقة والمسبح. تنظيف المسبح وقص العشب وتشذيب الأشجار.',
    'request_date':       str(ago(14)),
    'category':           'other',
    'priority':           '0',
    'supplier_partner_id':tech3.id,
    'scheduled_date':     str(dt(ago(13), 8)),
    'actual_duration':    6.0,
    'labor_cost':         400.0,
    'materials_cost':     150.0,
    'cost_bearer':        'owner',
    'notes':              'تمت الصيانة بنجاح. المسبح جاهز للاستخدام.',
})
req8.action_approve()
req8.action_schedule()
req8.action_start()
req8.action_done()

# أوامر العمل (Work Orders)
wo1 = env['sa.maintenance.work_order'].create({
    'request_id':       req1.id,
    'technician_id':    tech2.id,
    'description':      'فحص وحدات التكييف واختبار ضغط غاز التبريد وإصلاح أي تسرب.',
    'scheduled_date':   str(dt(ahead(1), 10)),
    'duration_planned': 3.0,
    'labor_cost':       300.0,
    'materials_cost':   150.0,
})
wo1.action_schedule()

wo2 = env['sa.maintenance.work_order'].create({
    'request_id':       req3.id,
    'technician_id':    tech2.id,
    'description':      'استبدال ثلاثة مصابيح سقف معيبة في منطقة الاستقبال.',
    'scheduled_date':   str(dt(ago(1), 14)),
    'duration_planned': 2.5,
    'duration_actual':  2.5,
    'labor_cost':       350.0,
    'materials_cost':   220.0,
})
wo2.action_schedule()
wo2.action_start()
wo2.action_done()

wo3 = env['sa.maintenance.work_order'].create({
    'request_id':       req7.id,
    'technician_id':    tech1.id,
    'description':      'فحص خزان المياه العلوي وإصلاح أي مشكلة في الضغط أو الصمامات.',
    'scheduled_date':   str(dt(ahead(2), 11)),
    'duration_planned': 3.0,
    'labor_cost':       250.0,
    'materials_cost':   300.0,
})
wo3.action_schedule()

wo4 = env['sa.maintenance.work_order'].create({
    'request_id':       req8.id,
    'technician_id':    tech3.id,
    'description':      'تنظيف المسبح وإضافة الكيماويات، قص العشب وتشذيب الأشجار في الحديقة.',
    'scheduled_date':   str(dt(ago(14), 8)),
    'duration_planned': 6.0,
    'duration_actual':  6.0,
    'labor_cost':       400.0,
    'materials_cost':   150.0,
})
wo4.action_schedule()
wo4.action_start()
wo4.action_done()

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 10 — عقود الصيانة الدورية  (Maintenance Contracts — 2)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود الصيانة... (Creating maintenance contracts...)")

mc1 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':      tech2.id,
    'property_ids':             [(6, 0, [prop1.id, prop9.id])],
    'category':                 'ac',
    'frequency':                'quarterly',
    'start_date':               str(ago(90)),
    'end_date':                 str(ahead(275)),
    'service_description':      'صيانة دورية ربع سنوية لأجهزة التكييف: تنظيف الفلاتر، فحص غاز التبريد، معايرة الثيرموستات لفيلا الروضة ومكتب بيزنس باي.',
    'estimated_cost_per_visit': 750.0,
})
mc1.action_activate()

mc2 = env['sa.maintenance.contract'].create({
    'supplier_partner_id':      tech1.id,
    'property_ids':             [(6, 0, [prop4.id, prop5.id, prop7.id])],
    'category':                 'plumbing',
    'frequency':                'annual',
    'start_date':               str(ago(30)),
    'end_date':                 str(ahead(335)),
    'service_description':      'فحص وصيانة سنوية لشبكات السباكة والصرف الصحي لشقق الرياض والدمام.',
    'estimated_cost_per_visit': 500.0,
})
mc2.action_activate()

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 11 — عمولات الوسطاء  (Broker Commissions — 4)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عمولات الوسطاء... (Creating broker commissions...)")

comm1 = env['sa.broker.commission'].create({
    'broker_partner_id': broker1.id,
    'tenancy_id':        t1.id,
    'commission_type':   'percentage',
    'commission_rate':   5.0,
    'payment_schedule':  'on_signup',
    'date_signed':       str(ago(180)),
    'notes':             'عمولة شركة الوافر على تأجير فيلا الروضة ١٢ للمستأجر خالد الراشدي.',
    'line_ids': [(0, 0, {
        'description': 'عمولة توقيع عقد فيلا الروضة ١٢',
        'due_date':    str(ago(180)),
        'amount':      4000.0,
        'state':       'paid',
    })],
})
comm1.action_confirm()

comm2 = env['sa.broker.commission'].create({
    'broker_partner_id': broker2.id,
    'tenancy_id':        t2.id,
    'commission_type':   'percentage',
    'commission_rate':   5.0,
    'payment_schedule':  'on_signup',
    'date_signed':       str(ago(90)),
    'notes':             'عمولة طارق الغامدي على تأجير شقة العليا ٣ب للمستأجر عمر الفاروق.',
    'line_ids': [(0, 0, {
        'description': 'عمولة توقيع عقد شقة العليا ٣ب',
        'due_date':    str(ago(90)),
        'amount':      2250.0,
        'state':       'paid',
    })],
})
comm2.action_confirm()

comm3 = env['sa.broker.commission'].create({
    'broker_partner_id': broker3.id,
    'tenancy_id':        t4.id,
    'commission_type':   'percentage',
    'commission_rate':   5.0,
    'payment_schedule':  'on_signup',
    'date_signed':       str(ago(337)),
    'notes':             'عمولة هند العمودي على تأجير شقة الحمراء ١٥ للمستأجرة عائشة مالك.',
    'line_ids': [(0, 0, {
        'description': 'عمولة توقيع عقد شقة الحمراء ١٥',
        'due_date':    str(ago(337)),
        'amount':      2100.0,
        'state':       'paid',
    })],
})
comm3.action_confirm()

comm4 = env['sa.broker.commission'].create({
    'broker_partner_id': broker1.id,
    'tenancy_id':        t5.id,
    'commission_type':   'percentage',
    'commission_rate':   5.0,
    'payment_schedule':  'split',
    'date_signed':       str(ago(365)),
    'notes':             'عمولة شركة الوافر على تأجير مكتب بيزنس باي ٢٠١ للمستأجر أحمد العمري. تُسدَّد على قسطين.',
    'line_ids': [
        (0, 0, {
            'description': 'القسط الأول – عند توقيع العقد',
            'due_date':    str(ago(365)),
            'amount':      3000.0,
            'state':       'paid',
        }),
        (0, 0, {
            'description': 'القسط الثاني – بعد ٦ أشهر',
            'due_date':    str(ago(185)),
            'amount':      3000.0,
            'state':       'paid',
        }),
    ],
})
comm4.action_confirm()

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 12 — عقود إيجار (نظام ECRS)  (Ejar ECRS Contracts — 3 sample records)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء عقود إيجار ECRS... (Creating Ejar ECRS contracts...)")

SAR_curr = env['res.currency'].search([('name', '=', 'SAR')], limit=1)

# ع.إيجار-١ — فيلا الروضة: حالة building (جارٍ الإعداد)
ec1 = env['ejar.contract'].create({
    'brokerage_profile_id': ejar_profile.id,
    'tenancy_id':           t1.id,
    'contract_type':        'residential',
    'contract_sub_type':    'main',
    'use_type':             'residential_families',
    'start_date':           t1.start_date,
    'end_date':             t1.end_date,
    'rent_amount':          80000.0,
    'currency_id':          SAR_curr.id,
    'payment_schedule':     'quarterly',
    'payment_option':       'bank_transfer',
    'sublease_allowed':     False,
    'ejar_fees_paid_by':    'brokerage_office',
    'brokerage_fee':        2000.0,
    'brokerage_fee_paid_by':'lessor',
})
ec1.action_start_building()

# ع.إيجار-٢ — شقة العليا: حالة submitted (بانتظار الموافقة من إيجار)
ec2 = env['ejar.contract'].create({
    'brokerage_profile_id': ejar_profile.id,
    'tenancy_id':           t2.id,
    'contract_type':        'residential',
    'contract_sub_type':    'main',
    'use_type':             'residential_families',
    'start_date':           t2.start_date,
    'end_date':             t2.end_date,
    'rent_amount':          45000.0,
    'currency_id':          SAR_curr.id,
    'payment_schedule':     'quarterly',
    'payment_option':       'bank_transfer',
    'sublease_allowed':     False,
    'ejar_fees_paid_by':    'brokerage_office',
    'ejar_contract_id':     'DEMO-EJAR-CONTRACT-002',
    'ejar_contract_number': '1234567890',
})
ec2.action_start_building()
# Manually push to submitted state for demo
ec2.write({'ejar_status': 'submitted', 'ejar_last_sync': today})

# ع.إيجار-٣ — مكتب بيزنس باي: حالة approved (موافق عليه)
ec3 = env['ejar.contract'].create({
    'brokerage_profile_id': ejar_profile.id,
    'tenancy_id':           t5.id,
    'contract_type':        'commercial',
    'contract_sub_type':    'main',
    'use_type':             'commercial',
    'start_date':           t5.start_date,
    'end_date':             t5.end_date,
    'rent_amount':          120000.0,
    'currency_id':          SAR_curr.id,
    'payment_schedule':     'quarterly',
    'payment_option':       'bank_transfer',
    'sublease_allowed':     False,
    'ejar_fees_paid_by':    'brokerage_office',
    'ejar_contract_id':     'DEMO-EJAR-CONTRACT-003',
    'ejar_contract_number': '9876543210',
    'brokerage_fee':        3000.0,
    'brokerage_fee_paid_by':'lessor',
})
ec3.action_start_building()
# Manually push to approved state for demo
ec3.write({'ejar_status': 'approved', 'ejar_last_sync': today})

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 13 — مستخدمو النظام  (System Users — 21 accounts, password: demo)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء حسابات المستخدمين... (Creating user accounts...)")

def make_user(name, email, partner, groups, password='demo'):
    existing = env['res.users'].search([('login','=',email)], limit=1)
    if existing:
        existing.password = password
        return existing
    kw = {
        'name':      name,
        'login':     email,
        'email':     email,
        'groups_id': [(6, 0, groups)],
        'password':  password,
        'lang':      'ar_001',
        'tz':        'Asia/Riyadh',
    }
    if partner:
        kw['partner_id'] = partner.id
    return env['res.users'].create(kw)

g_manager    = env.ref('sa_security.group_pms_manager').id
g_accountant = env.ref('sa_security.group_pms_accountant').id
g_agent      = env.ref('sa_security.group_pms_agent').id
g_owner      = env.ref('sa_security.group_pms_owner').id
g_tech       = env.ref('sa_security.group_pms_technician').id
g_portal        = env.ref('base.group_portal').id
g_tenant_portal = env.ref('sa_security.group_pms_tenant_portal').id

# موظفون داخليون (Internal staff)
make_user('سارة المدير — مدير العقارات',  'manager@propza-demo.sa',    None, [g_manager])
make_user('عمر المحاسب — محاسب العقارات', 'accountant@propza-demo.sa', None, [g_accountant])
make_user('لينا الموظفة — خدمة العملاء',  'agent@propza-demo.sa',      None, [g_agent])

# الملاك (Owners)
make_user(owner1.name, owner1.email, owner1, [g_owner])
make_user(owner2.name, owner2.email, owner2, [g_owner])
make_user(owner3.name, owner3.email, owner3, [g_owner])
make_user(owner4.name, owner4.email, owner4, [g_owner])

# الفنيون (Technicians)
make_user(tech1.name, tech1.email, tech1, [g_tech])
make_user(tech2.name, tech2.email, tech2, [g_tech])
make_user(tech3.name, tech3.email, tech3, [g_tech])

# المستأجرون — group_pms_tenant_portal (يشمل base.group_portal + صلاحيات العقارات)
for t in [tenant1, tenant2, tenant3, tenant4, tenant5, tenant6, tenant7, tenant8, tenant9, tenant10]:
    make_user(t.name, t.email, t, [g_tenant_portal])

# الوسطاء — بوابة عادية (Broker portal)
make_user(broker1.name, broker1.email, broker1, [g_portal])
make_user(broker2.name, broker2.email, broker2, [g_portal])
make_user(broker3.name, broker3.email, broker3, [g_portal])

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# 14 — بيانات الملفات الشخصية للمستأجرين  (Tenant Profile Data)
# ══════════════════════════════════════════════════════════════════════════
print("إنشاء بيانات الملفات الشخصية... (Creating tenant profile data...)")

from datetime import datetime as _dt

# ── بيانات شخصية وعناوين ────────────────────────────────────────────────
profile_data = [
    (tenant1,  'male',   '1985-03-15', 'مهندس معماري متخصص في تصميم المباني السكنية.',
     r_riyadh, 'الرياض', 'العليا',    '3214', '1', '4521', '12331', 'REAA3214'),
    (tenant2,  'male',   '1990-07-22', 'مدير مبيعات في شركة تقنية. انتقل إلى جدة عام 2018.',
     r_jeddah, 'جدة',    'النزهة',    '7821', '2', '1234', '23521', 'JZNZ7821'),
    (tenant3,  'female', '1988-11-08', 'معلمة في مدرسة ابتدائية حكومية. تهتم بالتعليم والتطوير.',
     r_riyadh, 'الرياض', 'النرجس',   '5540', '4', '3312', '13312', 'RNRJ5540'),
    (tenant4,  'female', '1992-04-20', 'موظفة في قطاع الصحة. مقيمة في المملكة منذ 2017.',
     r_riyadh, 'الرياض', 'الملقا',   '2210', '1', '8871', '13521', 'RMLQ2210'),
    (tenant5,  'male',   '1979-09-12', 'محاسب قانوني لدى شركة استثمار. خبرة 20 عاماً.',
     r_riyadh, 'الرياض', 'الروضة',   '8831', '3', '2245', '11411', 'RRWD8831'),
    (tenant6,  'female', '1995-01-30', 'مصممة جرافيك مستقلة. تعمل عن بُعد.',
     r_dammam, 'الدمام', 'الشاطئ',   '4412', '2', '5561', '31441', 'DSHT4412'),
    (tenant7,  'male',   '1983-06-05', 'طيار في إحدى شركات الطيران الخليجية.',
     r_riyadh, 'الرياض', 'الورود',   '6623', '1', '7712', '12711', 'RWRD6623'),
    (tenant8,  'female', '1991-12-17', 'صيدلانية في مستشفى حكومي. حاصلة على بكالوريوس صيدلة.',
     r_jeddah, 'جدة',    'الحمراء',  '3345', '5', '9901', '23411', 'JHMR3345'),
    (tenant9,  'male',   '1987-08-24', 'مقاول بناء يدير مشاريع إنشائية صغيرة ومتوسطة.',
     r_riyadh, 'الرياض', 'الصحافة',  '9912', '2', '3341', '12261', 'RSSH9912'),
    (tenant10, 'female', '1998-05-11', 'طالبة دكتوراه في جامعة الملك عبدالعزيز. تسكن وحدها.',
     r_jeddah, 'جدة',    'الأندلس',  '1123', '7', '6612', '23631', 'JAND1123'),
]

for (t, gender, dob, bio, region, city, district,
     bldg, unit, addl, postal, short_addr) in profile_data:
    t.write({
        'gender':             gender,
        'date_of_birth':      dob,
        'bio':                bio,
        'sa_region_id':       region.id if region else False,
        'city':               city,
        'sa_district':        district,
        'sa_building_no':     bldg,
        'sa_unit_no':         unit,
        'sa_additional_no':   addl,
        'sa_postal_code':     postal,
        'sa_national_address': short_addr,
    })

# ── توثيق الهوية  (sa.user.verification) ────────────────────────────────
now = _dt.now()

def make_verif(partner, id_type, id_number, id_expiry, state, days_ago=3, rejection_reason=False):
    rec = env['sa.user.verification'].create({
        'partner_id':   partner.id,
        'id_type':      id_type,
        'id_number':    id_number,
        'id_expiry':    str(id_expiry) if id_expiry else False,
        'state':        state,
        'submission_date': now if state in ('submitted', 'verified', 'rejected') else False,
        'verified_date':   now if state == 'verified' else False,
        'rejection_reason': rejection_reason or False,
    })
    if state == 'verified':
        partner.write({
            'sa_id_type':     id_type,
            'sa_national_id': id_number,
            'sa_id_expiry':   id_expiry,
            'sa_id_verified': True,
        })
    return rec

make_verif(tenant1,  'national_id', '1098765432', ahead(1095), 'verified')
make_verif(tenant2,  'national_id', '1034512678', ahead(730),  'verified')
make_verif(tenant3,  'national_id', '1067891234', ahead(548),  'submitted')
make_verif(tenant4,  'iqama',       '2123456789', ahead(180),  'verified')
make_verif(tenant5,  'national_id', '1055443322', ago(10),     'rejected',
           rejection_reason='الوثيقة منتهية الصلاحية')
# tenant6: draft — لم يتقدم بعد
env['sa.user.verification'].create({
    'partner_id': tenant6.id,
    'id_type':    'national_id',
    'id_number':  '1066778899',
    'state':      'draft',
})
make_verif(tenant7,  'national_id', '1077889900', ahead(1460), 'verified')
make_verif(tenant8,  'national_id', '1088990011', ahead(365),  'submitted')
make_verif(tenant9,  'national_id', '1099887766', ahead(912),  'verified')
# tenant10: draft — جديد لم يتقدم بعد
env['sa.user.verification'].create({
    'partner_id': tenant10.id,
    'id_type':    'national_id',
    'id_number':  '1044332211',
    'state':      'draft',
})

# ── وثائق المستخدمين  (sa.user.document) ────────────────────────────────
def make_doc(partner, doc_type, name, upload_days_ago, expiry_days=None, notes=None):
    env['sa.user.document'].create({
        'partner_id':  partner.id,
        'doc_type':    doc_type,
        'name':        name,
        'upload_date': str(ago(upload_days_ago)),
        'expiry_date': str(ahead(expiry_days)) if expiry_days is not None else False,
        'notes':       notes or False,
    })

# tenant1 — خالد: هوية + خطاب راتب
make_doc(tenant1, 'national_id', 'هوية وطنية — خالد الراشدي', 90,  expiry_days=1095)
make_doc(tenant1, 'other',       'خطاب راتب — وزارة الإسكان',  30,  expiry_days=180,
         notes='يُستخدم لإثبات الدخل الشهري')

# tenant2 — عمر: هوية + عقد إيجار سابق (مؤرشف)
make_doc(tenant2, 'national_id',    'هوية وطنية — عمر الفاروق',        180, expiry_days=730)
doc2_old = env['sa.user.document'].create({
    'partner_id':  tenant2.id,
    'doc_type':    'lease_contract',
    'name':        'عقد إيجار سابق — شقة جدة 2022',
    'upload_date': str(ago(500)),
    'expiry_date': str(ago(90)),
})
doc2_old.action_archive()

# tenant3 — نورة: هوية فقط (بانتظار التوثيق)
make_doc(tenant3, 'national_id', 'هوية وطنية — نورة الحمدان', 15, expiry_days=548)

# tenant4 — عائشة: إقامة (تنتهي قريباً)
make_doc(tenant4, 'national_id', 'إقامة — عائشة مالك', 60, expiry_days=25,
         notes='يجب التجديد قبل نهاية الشهر')

# tenant5 — أحمد: هوية منتهية الصلاحية
make_doc(tenant5, 'national_id', 'هوية وطنية — أحمد العمري (منتهية)', 400, expiry_days=-10)

# tenant7 — محمد: هوية + كشف حساب بنكي
make_doc(tenant7, 'national_id', 'هوية وطنية — محمد الشهري', 200, expiry_days=1460)
make_doc(tenant7, 'other',       'كشف حساب بنكي — بنك الراجحي', 10, expiry_days=90,
         notes='آخر 3 أشهر')

# tenant8 — ريم: هوية
make_doc(tenant8, 'national_id', 'هوية وطنية — ريم القرني', 45, expiry_days=365)

# tenant9 — فيصل: هوية + عقد إيجار حالي
make_doc(tenant9, 'national_id',    'هوية وطنية — فيصل الغامدي', 120, expiry_days=912)
make_doc(tenant9, 'lease_contract', 'عقد إيجار — فيلا الورود', 30, expiry_days=335,
         notes='نسخة من عقد إيجار العقار الحالي')

env.cr.commit()

# ══════════════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════════════
print("")
print("══════════════════════════════════════════════════════════════")
print("  ✓ تم تحميل البيانات التجريبية بنجاح! Demo data loaded!")
print("══════════════════════════════════════════════════════════════")
print(f"  ملف الوساطة      / Brokerage Profile: 1  (بروبزا للوساطة، بيانات UAT)")
print(f"  الملاك           / Owners:      4  ({owner1.name[:20]}…، {owner4.name[:20]}…)")
print(f"  المستأجرون       / Tenants:    10  (٦ موثَّق، ٢ قيد المراجعة، ٢ مسودة)")
print(f"  الوسطاء          / Brokers:     3")
print(f"  الفنيون          / Technicians: 3")
print(f"  العقارات         / Properties: 12  (فلل + شقق + مكاتب + مستودع + محل)")
print(f"  عقود الإيجار     / Tenancies:   9  (٦ نشطة، ١ مؤكد، ١ مسودة، ١ منتهية)")
print(f"  الدفعات          / Payments:   {env['sa.rent.payment'].search_count([])}")
print(f"  المعاينات        / Inspections: 5  (٣ موقعة، ١ مكتملة، ١ مسودة)")
print(f"  طلبات الصيانة   / Maint Reqs:  8  (متنوعة الحالات)")
print(f"  أوامر العمل     / Work Orders: 4  (١ مجدول، ٢ منجز، ١ قيد التنفيذ)")
print(f"  عقود الصيانة    / Maint Conts: 2  (تكييف + سباكة، نشطة)")
print(f"  عمولات الوسطاء  / Commissions: 4  (جميعها مؤكدة ومدفوعة)")
print(f"  عقود إيجار ECRS / Ejar Contracts: {env['ejar.contract'].search_count([])}  (building، submitted، approved)")
print(f"  توثيق الهوية    / Verifications: {env['sa.user.verification'].search_count([])}  (٦ موثَّق، ٢ مقدَّم، ٢ مسودة/مرفوض)")
print(f"  وثائق المستخدمين / Documents:  {env['sa.user.document'].search_count([])}  (هويات، عقود، خطابات راتب)")
print(f"  المستخدمون       / Users:      23  (كلمة المرور: demo)")
print("")
PYEOF

echo ""
echo "  ✓ اكتمل التحميل! Login: demo@demo.com / demo"
echo ""
