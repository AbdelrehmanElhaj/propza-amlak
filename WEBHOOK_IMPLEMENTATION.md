# Ejar Webhook Implementation — Complete Reference

## Overview
Secure webhook endpoints for real-time contract status callbacks from Ejar ECRS platform.

**Version**: 17.0.4.0.0  
**Features**: HMAC-SHA256 signatures, replay attack prevention, idempotent processing, audit logging

---

## Architecture

### 1. HTTP Controller (`controllers/ejar_webhook.py`)
**Endpoint**: `POST /ejar/webhook` (auth='none', csrf=False)

**Headers**:
- `X-Webhook-Signature` — HMAC-SHA256(secret, body).hexdigest()
- `X-Webhook-Timestamp` — Unix timestamp (seconds)
- `X-Correlation-ID` — Optional correlation ID

**Response**: 202 Accepted (async processing)

```bash
curl -X POST https://your-odoo.com/ejar/webhook \
  -H "X-Webhook-Signature: abc123..." \
  -H "X-Webhook-Timestamp: 1715900000" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": 1,
    "contract_id": 42,
    "event_type": "contract.approved",
    "ejar_contract_number": "EJAR-2024-001",
    "webhook_id": "hook-uuid-123",
    "idempotency_key": "idem-123"
  }'
```

---

### 2. Webhook Validator (`services/webhook_validator.py`)

**Validation steps**:
1. Timestamp window check (±300 seconds)
2. HMAC-SHA256 signature verification (constant-time)
3. JSON parsing
4. Idempotency key deduplication (24-hour window)

**Exceptions**:
- `EjarWebhookSignatureInvalid` — Signature mismatch
- `EjarWebhookReplayAttack` — Timestamp outside window
- `EjarWebhookTimestampMissing` — Missing timestamp header
- `EjarWebhookSignatureMissing` — Missing signature header
- `EjarWebhookInvalidJSON` — Malformed JSON
- `EjarWebhookConfigMissing` — Secret not configured

---

### 3. Webhook Processor (`services/webhook_processor.py`)

**Event handlers** (5 supported):

| Event | Handler | Action |
|-------|---------|--------|
| `contract.approved` | `_handle_contract_approved()` | Status → approved, store contract number |
| `contract.rejected` | `_handle_contract_rejected()` | Status → rejected, store rejection reason |
| `acknowledgement.completed` | `_handle_acknowledgement_completed()` | Mark parties as synced |
| `document.verification` | `_handle_document_verification()` | Log document verification result |
| `status.update` | `_handle_status_update()` | General status synchronization |

**Async processing**: Via `@job(channel=CHANNEL_POLLING)` with queue_job (fallback: sync)

---

### 4. ejar_contract Model Fields

New webhook tracking fields (readonly):

```python
webhook_uuid                 # UUID of webhook event
webhook_delivered_at         # ISO timestamp when received
webhook_event_type          # Type of last event
webhook_correlation_id      # Links to ejar.sync.log
webhook_last_error_at       # If delivery failed
webhook_last_error_msg      # Error details
```

---

### 5. Audit Trail Integration

**ejar.sync.log entries** (inbound direction):

```python
EjarSyncLog.log_call(
    action='webhook_contract.approved',
    direction='inbound',
    http_method='POST',
    endpoint='/ejar/webhook',
    http_status=202,
    correlation_id='...',
    idempotency_key='...',
    request_body=json.dumps(webhook_data),  # Sanitized
    status='success',
)
```

---

## Deployment Checklist

### 1. Generate Webhook Secret
```bash
openssl rand -hex 32
# Output: a1b2c3d4e5f6...
```

### 2. Configure Per Company
```sql
INSERT INTO ir_config_parameter (key, value) VALUES
  ('ejar.webhook.secret.company_1', 'a1b2c3d4e5f6...');
```

### 3. Provide URL to Ejar
```
https://your-odoo.com/ejar/webhook
```

### 4. Optional: Enable async processing
```ini
[queue_job]
channels = root:4,root.ejar:8,root.ejar.contracts:2,root.ejar.polling:10,root.ejar.documents:3
```

---

## Security Checklist

✅ HMAC-SHA256 signature validation (constant-time comparison)  
✅ Timestamp window ±300 seconds (replay attack prevention)  
✅ Idempotency key deduplication (24-hour retention)  
✅ Sensitive field sanitization before logging  
✅ Correlation ID tracing (inbound → audit log)  
✅ 202 Accepted response (non-blocking)  
✅ Async processing with fallback  
✅ Graceful error handling (logged, not exposed)  

---

## Testing

### Unit Tests
**File**: `tests/test_webhook_validator.py`
- ✓ Valid signature acceptance
- ✓ Invalid/missing signature rejection
- ✓ Timestamp window validation
- ✓ Replay attack detection
- ✓ JSON parsing errors
- ✓ Config missing detection
- ✓ Idempotency deduplication

### Integration Tests
**File**: `tests/test_webhook_processor.py`
- ✓ Contract approved event
- ✓ Contract rejected event
- ✓ Acknowledgement completed event
- ✓ Sync log creation
- ✓ Unknown event type handling
- ✓ Contract not found handling

### Manual Testing
```bash
# Test with valid signature
SECRET="your-generated-secret"
TIMESTAMP=$(date +%s)
BODY='{"company_id":1,"contract_id":42,"event_type":"contract.approved"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

curl -X POST http://localhost:8069/ejar/webhook \
  -H "X-Webhook-Signature: $SIG" \
  -H "X-Webhook-Timestamp: $TIMESTAMP" \
  -H "Content-Type: application/json" \
  -d "$BODY"
```

---

## Files Created/Modified

| File | Type | Purpose |
|------|------|---------|
| `controllers/__init__.py` | NEW | Package init |
| `controllers/ejar_webhook.py` | NEW | HTTP endpoint |
| `services/webhook_validator.py` | NEW | Validation logic |
| `services/webhook_processor.py` | NEW | Event handling |
| `services/exceptions.py` | MODIFY | Add webhook exceptions (+10 new) |
| `services/__init__.py` | MODIFY | Export webhook services |
| `models/ejar_contract.py` | MODIFY | Add webhook fields (6 new) |
| `__manifest__.py` | MODIFY | Version 4.0.0, webhook docs |
| `tests/test_webhook_validator.py` | NEW | Validator unit tests (9 test methods) |
| `tests/test_webhook_processor.py` | NEW | Processor integration tests (6 test methods) |

---

## Exception Classes

All webhook exceptions extend `EjarWebhookError` (base class):

**Permanent errors** (dead-letter immediately):
- `EjarWebhookSignatureInvalid` — Tampering suspected
- `EjarWebhookSignatureMissing` — Malformed request
- `EjarWebhookTimestampMissing` — Malformed request
- `EjarWebhookInvalidJSON` — Malformed request
- `EjarWebhookConfigMissing` — Config issue
- `EjarWebhookContractNotFound` — Data sync issue
- `EjarWebhookIdempotencyKeyMissing` — Malformed request

**Transient errors** (safe to retry):
- `EjarWebhookReplayAttack` — May recover (clock skew)
- `EjarWebhookUnknownEventType` — May be implemented later

---

## Performance Notes

- **202 Accepted**: Controller returns immediately; processing is async
- **Idempotency window**: 24 hours (configurable via `TIMESTAMP_WINDOW_SECONDS`)
- **Signature verification**: O(n) where n = payload size (< 65KB typical)
- **Duplicate detection**: Index on `idempotency_key` + `create_date` (fast)
- **Queue polling**: Separate channel (`root.ejar.polling`) prevents overload

---

## Troubleshooting

**Signature mismatch**:
1. Verify secret matches in `ir.config_parameter`
2. Check webhook body encoding (UTF-8)
3. Verify HMAC computation: `hexdigest()` not `digest()`

**Timestamp rejected**:
1. Sync server clocks (NTP)
2. Verify timestamp is in seconds (not milliseconds)
3. Check window ±300s applies

**Duplicate silently ignored**:
1. Expected behavior (idempotency)
2. Check `ejar.sync.log` with same `idempotency_key`

**Webhook not processed**:
1. Check `/ejar/webhook` controller loaded (controllers/ auto-discovered)
2. Check sync logs: `ejar.sync.log` records with action=`webhook_*`
3. If async: check queue_job worker running for `root.ejar.polling` channel

---

## Example: End-to-End Webhook Flow

1. **Ejar sends webhook**:
   ```json
   POST /ejar/webhook
   X-Webhook-Signature: abc123def456...
   X-Webhook-Timestamp: 1715900000
   {
     "company_id": 1,
     "contract_id": 42,
     "event_type": "contract.approved",
     "ejar_contract_number": "EJAR-2024-001",
     "webhook_id": "hook-uuid",
     "idempotency_key": "idem-key-123"
   }
   ```

2. **Controller receives** (route `/ejar/webhook`):
   - Extracts signature, timestamp, body bytes
   - Returns 202 Accepted immediately

3. **Validator checks**:
   - ✓ Timestamp within 300s window
   - ✓ HMAC-SHA256 signature matches
   - ✓ JSON parses successfully
   - ✓ Idempotency key not in last 24h

4. **Processor queues job** (async via queue_job):
   - `@job(channel=CHANNEL_POLLING)` decorator
   - Fallback: sync if queue_job unavailable

5. **Webhook processor executes**:
   - Creates `ejar.sync.log` entry (inbound)
   - Routes to `_handle_contract_approved()`
   - Updates contract: `ejar_status='approved'`
   - Posts chatter message
   - Updates webhook tracking fields

6. **Result**:
   - ✓ Contract status updated
   - ✓ Chatter message posted
   - ✓ Audit trail complete
   - ✓ Sync log entry created with correlation ID

---

## Next Steps (Optional)

- [ ] Implement webhook secret rotation
- [ ] Add webhook delivery retry queue (for failed callbacks)
- [ ] Implement webhook signature verification in separate consumer
- [ ] Add webhook event filtering per user preferences
- [ ] Create webhook event dashboard/monitoring UI
