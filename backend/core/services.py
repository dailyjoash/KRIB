import base64
import json
import logging
import os
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from django.core.files.base import ContentFile
from django.utils import timezone
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover - optional dependency in lightweight builds
    A4 = None
    ImageReader = None
    canvas = None

logger = logging.getLogger(__name__)


def _normalize_sms_phone_number(phone_number):
    value = re.sub(r"[^\d+]", "", str(phone_number or "").strip())
    if not value:
        return ""
    if value.startswith("+"):
        return value
    if value.startswith("0") and len(value) == 10:
        return f"+254{value[1:]}"
    if value.startswith("254") and len(value) == 12:
        return f"+{value}"
    return value


def current_period_string(today=None):
    today = today or timezone.localdate()
    return today.strftime("%Y-%m")


def current_billing_period(today=None):
    today = today or timezone.localdate()
    return date(today.year, today.month, 1)


def period_string_to_date(period):
    if not period:
        return current_billing_period()
    year, month = period.split("-")
    return date(int(year), int(month), 1)


def build_public_url(path):
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base or not path:
        return path
    return f"{base}{path}"


def save_payment_receipt(payment):
    if payment.receipt_file:
        return payment.receipt_file.path
    if canvas is None or A4 is None:
        logger.warning("Skipping receipt generation because reportlab is not installed.")
        return None

    tenant_name = getattr(payment.tenant, "username", "Tenant")
    property_name = getattr(payment.lease.unit.property, "name", "Property")
    unit_number = getattr(payment.lease.unit, "unit_number", "-")
    business_name = os.getenv("BUSINESS_NAME", os.getenv("MPESA_BUSINESS_NAME", "KRIB"))
    support_phone = os.getenv("SUPPORT_PHONE", "")
    support_email = os.getenv("SUPPORT_EMAIL", "")
    business_address = os.getenv("BUSINESS_ADDRESS", "")
    transaction_code = payment.transaction_code or payment.mpesa_receipt or payment.checkout_request_id or f"PAY-{payment.id}"
    payment_date = payment.transaction_date or payment.created_at or timezone.now()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4

    y = height - 72
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, y, business_name)
    y -= 22
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "KRIB Payment Receipt")
    y -= 18
    if business_address:
        pdf.drawString(72, y, business_address)
        y -= 16
    if support_email or support_phone:
        pdf.drawString(72, y, f"{support_email}  {support_phone}".strip())
        y -= 24

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Receipt Details")
    y -= 18
    pdf.setFont("Helvetica", 11)

    rows = [
        ("Tenant", tenant_name),
        ("Property", f"{property_name} / {unit_number}"),
        ("Billing Period", payment.period or current_period_string()),
        ("Payment Method", (payment.payment_method or "mpesa").upper()),
        ("Amount", f"KES {Decimal(payment.amount):,.2f}"),
        ("Transaction Code", transaction_code),
        ("Date", timezone.localtime(payment_date).strftime("%Y-%m-%d %H:%M:%S")),
    ]

    for label, value in rows:
        pdf.drawString(72, y, f"{label}: {value}")
        y -= 18

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"receipt-{payment.id}-{current_period_string()}.pdf"
    payment.receipt_file.save(filename, ContentFile(buffer.read()), save=False)
    payment.save(update_fields=["receipt_file"])
    return payment.receipt_file.path


def _decode_data_url_file(data_url):
    if not data_url or "," not in data_url:
        return None
    _header, encoded = data_url.split(",", 1)
    try:
        return base64.b64decode(encoded)
    except Exception as exc:  # pragma: no cover - defensive parsing
        raise ValueError("Invalid base64 file data.") from exc


def _draw_wrapped_text(pdf, text, x, y, max_width, *, font_name="Helvetica", font_size=11, line_height=16):
    text = str(text or "").strip()
    if not text:
        return y

    pdf.setFont(font_name, font_size)
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        pdf.drawString(x, y, current)
        y -= line_height
        current = word
    if current:
        pdf.drawString(x, y, current)
        y -= line_height
    return y


def build_lease_agreement_pdf(lease, *, signature_data_url=""):
    if canvas is None or A4 is None:
        logger.warning("Skipping lease agreement generation because reportlab is not installed.")
        return None

    signature_reader = None
    if signature_data_url:
        if ImageReader is None:
            logger.warning("Skipping lease agreement signature embedding because reportlab image tools are unavailable.")
        else:
            signature_bytes = _decode_data_url_file(signature_data_url)
            if not signature_bytes:
                raise ValueError("Invalid tenant signature data.")
            signature_reader = ImageReader(BytesIO(signature_bytes))

    property_obj = lease.unit.property
    tenant = lease.tenant
    landlord = property_obj.landlord
    landlord_settings = getattr(landlord, "landlord_settings", None)
    business_name = getattr(landlord_settings, "business_name", "") or os.getenv("BUSINESS_NAME", "KRIB")
    tenant_profile = getattr(tenant, "tenant_profile", None)
    tenant_phone = getattr(tenant_profile, "phone", "") or getattr(getattr(tenant, "profile", None), "phone_number", "")
    tenant_name = tenant.get_full_name() or tenant.username
    landlord_name = landlord.get_full_name() or landlord.username
    created_at = timezone.localtime()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 72

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, y, business_name)
    y -= 22
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "KRIB Tenant Agreement / Lease Document")
    y -= 24

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Lease Summary")
    y -= 18
    pdf.setFont("Helvetica", 11)

    summary_rows = [
        ("Tenant", tenant_name),
        ("Tenant Email", tenant.email or "-"),
        ("Tenant Phone", tenant_phone or "-"),
        ("Landlord", landlord_name),
        ("Property", property_obj.name),
        ("Location", property_obj.location),
        ("Unit", lease.unit.unit_number),
        ("Unit Type", lease.unit.get_unit_type_display()),
        ("Monthly Rent", f"KES {Decimal(lease.rent_amount):,.2f}"),
        ("Deposit", f"KES {Decimal(lease.unit.deposit):,.2f}"),
        ("Start Date", lease.start_date.strftime("%d %b %Y")),
        ("End Date", lease.end_date.strftime("%d %b %Y") if lease.end_date else "Open ended"),
        ("Due Day", f"Day {lease.due_day} of each month"),
        ("Generated On", created_at.strftime("%d %b %Y %H:%M")),
    ]
    for label, value in summary_rows:
        pdf.drawString(72, y, f"{label}: {value}")
        y -= 18

    y -= 6
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Agreement Notes")
    y -= 20
    y = _draw_wrapped_text(
        pdf,
        f"This lease confirms that {tenant_name} will occupy unit {lease.unit.unit_number} at {property_obj.name}, "
        f"{property_obj.location}, and pay KES {Decimal(lease.rent_amount):,.2f} per month.",
        72,
        y,
        width - 144,
    )
    y = _draw_wrapped_text(
        pdf,
        f"The tenant acknowledges the agreed deposit of KES {Decimal(lease.unit.deposit):,.2f} and the monthly due day of {lease.due_day}.",
        72,
        y,
        width - 144,
    )
    y = _draw_wrapped_text(
        pdf,
        "This document was prepared electronically in KRIB and shared with the tenant, landlord, and manager as the active lease record.",
        72,
        y,
        width - 144,
    )

    y -= 8
    if y < 170:
        pdf.showPage()
        y = height - 72

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(72, y, "Tenant Signature")
    y -= 18

    if signature_reader is not None:
        pdf.drawImage(signature_reader, 72, y - 68, width=170, height=68, mask="auto", preserveAspectRatio=True)
        pdf.line(72, y - 72, 242, y - 72)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, y - 88, f"Captured electronically on {created_at.strftime('%d %b %Y %H:%M')}")
        y -= 106
    else:
        pdf.line(72, y - 12, 242, y - 12)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(72, y - 28, "No signature image was embedded.")
        y -= 44

    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, y, "Landlord approval is recorded in KRIB when this lease is created.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"lease-agreement-{lease.id}-{lease.unit.unit_number}.pdf"
    return filename, ContentFile(buffer.read(), name=filename)


def send_sms(phone_number, message, *, include_detail=False):
    username = os.getenv("AFRICASTALKING_USERNAME", "")
    api_key = os.getenv("AFRICASTALKING_API_KEY", "")
    sender_id = os.getenv("AFRICASTALKING_SENDER_ID", "")
    normalized_phone = _normalize_sms_phone_number(phone_number)
    if not username or not api_key or not normalized_phone:
        logger.info("Skipping SMS send because Africa's Talking is not configured.")
        result = {"ok": False, "detail": "Africa's Talking is not configured or the phone number is invalid."}
        return result if include_detail else False

    payload_dict = {
        "username": username,
        "to": normalized_phone,
        "message": message,
    }
    if sender_id:
        payload_dict["from"] = sender_id

    payload = urllib_parse.urlencode(payload_dict).encode()
    req = urllib_request.Request(
        os.getenv("AFRICASTALKING_SMS_URL", "https://api.africastalking.com/version1/messaging"),
        data=payload,
        method="POST",
        headers={
            "apiKey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            raw_body = resp.read().decode()
            logger.info("Africa's Talking SMS response: %s", raw_body)
            parsed = json.loads(raw_body or "{}")
            recipients = ((parsed.get("SMSMessageData") or {}).get("Recipients")) or []
            first_recipient = recipients[0] if recipients else {}
            status_text = first_recipient.get("status") or (parsed.get("SMSMessageData") or {}).get("Message") or "SMS sent."
            ok = first_recipient.get("status") == "Success" or "Sent to" in ((parsed.get("SMSMessageData") or {}).get("Message") or "")
            result = {"ok": ok, "detail": status_text, "body": parsed}
            return result if include_detail else ok
    except HTTPError as exc:  # pragma: no cover - network path
        body = ""
        try:
            body = exc.read().decode()
        except Exception:
            body = ""
        logger.warning("SMS delivery failed: %s %s", exc, body)
        detail = body or str(exc)
        result = {"ok": False, "detail": detail}
        return result if include_detail else False
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("SMS delivery failed: %s", exc)
        result = {"ok": False, "detail": str(exc)}
        return result if include_detail else False


def _paypal_api_base():
    explicit = os.getenv("PAYPAL_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    mode = os.getenv("PAYPAL_MODE", "sandbox").lower()
    if mode == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def _paypal_currency():
    return os.getenv("PAYPAL_CURRENCY", "KES").strip().upper() or "KES"


def _paypal_error_result(exc, fallback):
    body = {}
    try:
        payload = exc.read().decode()
        body = json.loads(payload) if payload else {}
    except Exception:  # pragma: no cover - defensive parsing
        body = {}

    details = body.get("details") or []
    first_detail = details[0] if details else {}
    issue = first_detail.get("issue", "")
    description = first_detail.get("description") or body.get("message") or fallback

    if issue == "CURRENCY_NOT_SUPPORTED":
        description = (
            f"PayPal checkout does not support {_paypal_currency()} for this account. "
            "Use M-Pesa or change PayPal currency to a supported code."
        )

    return {
        "error": True,
        "status": getattr(exc, "code", 502),
        "issue": issue,
        "detail": description,
        "body": body,
    }


def paypal_access_token():
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    secret = os.getenv("PAYPAL_SECRET", "").strip()
    if not client_id or not secret:
        return None

    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get("access_token")
    except HTTPError as exc:
        error = _paypal_error_result(exc, "PayPal authentication failed.")
        logger.warning("PayPal access token failed: %s", error["body"] or error["detail"])
        return None
    except URLError as exc:
        logger.warning("PayPal access token failed: %s", exc)
        return None


def paypal_create_order(amount, reference):
    token = paypal_access_token()
    if not token:
        return None

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference,
                "amount": {
                    "currency_code": _paypal_currency(),
                    "value": f"{Decimal(amount):.2f}",
                },
            }
        ],
        "application_context": {
            "brand_name": os.getenv("BUSINESS_NAME", "KRIB"),
            "user_action": "PAY_NOW",
        },
    }
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v2/checkout/orders",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        error = _paypal_error_result(exc, "PayPal order creation failed.")
        logger.warning("PayPal create order failed: %s", error["body"] or error["detail"])
        return error
    except URLError as exc:
        logger.warning("PayPal create order failed: %s", exc)
        return {"error": True, "status": 502, "detail": "PayPal is unreachable right now. Please try again."}


def paypal_capture_order(order_id):
    token = paypal_access_token()
    if not token:
        return None
    req = urllib_request.Request(
        f"{_paypal_api_base()}/v2/checkout/orders/{order_id}/capture",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        error = _paypal_error_result(exc, "PayPal capture failed.")
        logger.warning("PayPal capture failed: %s", error["body"] or error["detail"])
        return error
    except URLError as exc:
        logger.warning("PayPal capture failed: %s", exc)
        return {"error": True, "status": 502, "detail": "PayPal is unreachable right now. Please try again."}
