from . import messaging_gateway    # أولاً — يرثه unifonic وultramsg
from . import unifonic_service     # يرث messaging_gateway
from . import ultramsg_service     # يرث messaging_gateway
from . import notification_helper
from . import sa_crm_notifications
from . import sa_rent_payment
from . import property_tenancy
from . import sa_maintenance_request
from . import sa_maintenance_work_order
from . import res_config_settings
