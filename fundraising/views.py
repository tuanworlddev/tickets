import requests
import io
import zipfile
import os
from urllib.parse import quote
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from PIL import Image, ImageDraw, ImageFont
from .models import SEAT_COLUMNS, SEAT_ROWS, Ticket, UserMessage, format_currency

VIETQR_BANK_BIN = "970422"  # MB Bank
VIETQR_ACCOUNT_NO = "0975497557"
VIETQR_ACCOUNT_NAME = "NGUYEN THU HUONG"
VIETQR_ACCOUNT_DISPLAY_NAME = "Nguyễn Thu Hương"
VIETQR_TEMPLATE = "compact2"
EVENT_INFO = {
    'name': 'Hồn Việt',
    'type': 'Chương trình nghệ thuật',
    'subtitle': 'Hành trình từ cội nguồn đến tương lai',
    'time': '18:30',
    'date': 'Thứ Ba, 29.09.2026',
    'venue': 'Nhà hàng Hương Cau',
    'address': '244 đường 2/9, Hòa Cường, Đà Nẵng',
    'tiktok_url': 'https://www.tiktok.com/@gem_honviet?_r=1&_t=ZS-99fBNhrjWqd',
    'facebook_url': 'https://www.facebook.com/share/1YLfAA3WK3/?mibextid=wwXIfr',
}

def build_vietqr_url(amount, buyer_name):
    transfer_note = f"HON VIET {buyer_name}"
    return (
        f"https://img.vietqr.io/image/{VIETQR_BANK_BIN}-{VIETQR_ACCOUNT_NO}-{VIETQR_TEMPLATE}.png"
        f"?amount={amount}"
        f"&addInfo={quote(transfer_note)}"
        f"&accountName={quote(VIETQR_ACCOUNT_NAME)}"
    )

def release_expired_tickets():
    cleanup_threshold = timezone.now() - timedelta(minutes=3)
    expired = Ticket.objects.filter(status='LOCKED', locked_at__lt=cleanup_threshold)
    count = expired.count()
    if count > 0:
        expired.update(status='AVAILABLE', locked_at=None)
    return count

def index(request):
    release_expired_tickets()
    ticket_by_number = {
        ticket.number: ticket
        for ticket in Ticket.objects.filter(number__lte=SEAT_ROWS * len(SEAT_COLUMNS))
    }
    seat_rows = []
    left_sections = SEAT_COLUMNS[:5]
    right_sections = SEAT_COLUMNS[5:]
    for row_number in range(1, SEAT_ROWS + 1):
        left_seats = [
            ticket_by_number.get((row_number - 1) * len(SEAT_COLUMNS) + SEAT_COLUMNS.index(section) + 1)
            for section in left_sections
        ]
        right_seats = [
            ticket_by_number.get((row_number - 1) * len(SEAT_COLUMNS) + SEAT_COLUMNS.index(section) + 1)
            for section in right_sections
        ]
        seat_rows.append({
            'number': row_number,
            'left_seats': left_seats,
            'right_seats': right_seats,
        })

    return render(request, 'fundraising/index.html', {
        'seat_rows': seat_rows,
        'left_sections': left_sections,
        'right_sections': right_sections,
        'event': EVENT_INFO,
    })

def lock_tickets(request):
    if request.method == 'POST':
        ticket_numbers = request.POST.getlist('ticket_numbers')
        if not ticket_numbers:
            messages.error(request, 'Vui lòng chọn ít nhất một ghế.')
            return redirect('index')
        
        # Convert to integers
        try:
            ticket_numbers = [int(n) for n in ticket_numbers]
        except ValueError:
             messages.error(request, 'Mã ghế không hợp lệ.')
             return redirect('index')

        with transaction.atomic():
            # Check availability
            tickets = Ticket.objects.select_for_update().filter(number__in=ticket_numbers)
            if tickets.count() != len(ticket_numbers):
                messages.error(request, 'Không tìm thấy một số ghế đã chọn.')
                return redirect('index')
            
            unavailable = tickets.exclude(status='AVAILABLE')
            if unavailable.exists():
                msg = ", ".join([t.seat_label for t in unavailable])
                messages.error(request, f'Ghế {msg} không còn trống.')
                return redirect('index')
            
            # Lock them
            tickets.update(status='LOCKED', locked_at=timezone.now())
            
            # Store in session
            request.session['locked_tickets'] = ticket_numbers
            return redirect('checkout')
    
    return redirect('index')

def checkout(request):
    locked_ids = request.session.get('locked_tickets', [])
    if not locked_ids:
        messages.error(request, 'Bạn chưa chọn ghế.')
        return redirect('index')
    
    tickets = Ticket.objects.filter(number__in=locked_ids).order_by('number')
    
    # Check if any ticket is missing
    if tickets.count() != len(locked_ids):
         messages.error(request, 'Thông tin ghế không chính xác.')
         return redirect('index')

    # Verify all tickets are still LOCKED (and thus belong to this session mostly)
    # If a ticket is SOLD or AVAILABLE, it means it expired or was taken.
    if tickets.exclude(status='LOCKED').exists():
         messages.error(request, 'Ghế đã hết hạn giữ chỗ hoặc đã được bán.')
         return redirect('index')

    # Get the earliest lock time to determine expiration
    first_ticket = tickets.first()
    expiration_timestamp = 0
    if first_ticket and first_ticket.locked_at:
        expire_at = first_ticket.locked_at + timedelta(minutes=3)
        remaining = (expire_at - timezone.now()).total_seconds()
        
        # Double check expiration logic here as well
        if remaining <= 0:
             release_expired_tickets() # Ensure DB is updated
             messages.error(request, 'Thời gian giữ ghế đã hết.')
             return redirect('index')
        
        expiration_timestamp = expire_at.timestamp()
    
    # Calculate total
    total_amount = sum(ticket.price for ticket in tickets)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        
        if not name or not phone:
             messages.error(request, 'Vui lòng điền đầy đủ thông tin.')
             return render(request, 'fundraising/checkout.html', {
                 'tickets': tickets,
                 'total_amount': total_amount,
                 'total_amount_display': format_currency(total_amount),
                 'expiration_timestamp': expiration_timestamp,
                 'event': EVENT_INFO,
             })

        request.session['pending_buyer'] = {
            'name': name.strip(),
            'phone': phone.strip(),
        }

        qr_url = build_vietqr_url(total_amount, name)
        try:
            api_url = "https://api.vietqr.io/v2/generate"
            payload = {
                "accountNo": VIETQR_ACCOUNT_NO,
                "accountName": VIETQR_ACCOUNT_NAME,
                "acqId": int(VIETQR_BANK_BIN),
                "amount": total_amount,
                "addInfo": f"HON VIET {name}",
                "format": "text",
                "template": VIETQR_TEMPLATE
            }

            if settings.VIETQR_CLIENT_ID and settings.VIETQR_API_KEY:
                headers = {
                    "x-client-id": settings.VIETQR_CLIENT_ID,
                    "x-api-key": settings.VIETQR_API_KEY,
                    "Content-Type": "application/json"
                }

                response = requests.post(api_url, json=payload, headers=headers, timeout=10)
                data = response.json()

                if data.get("code") == "00":
                    qr_url = data.get("data", {}).get("qrDataURL") or qr_url
        except Exception as e:
            print(f"Error generating QR: {e}")

        return render(request, 'fundraising/payment.html', {
            'tickets': tickets,
            'qr_url': qr_url,
            'amount': total_amount,
            'amount_display': format_currency(total_amount),
            'bank_name': 'MB Bank',
            'account_no': VIETQR_ACCOUNT_NO,
            'account_name': VIETQR_ACCOUNT_DISPLAY_NAME,
            'event': EVENT_INFO,
            'expiration_timestamp': expiration_timestamp,
        })

    return render(request, 'fundraising/checkout.html', {
        'tickets': tickets, 
        'total_amount': total_amount,
        'total_amount_display': format_currency(total_amount),
        'expiration_timestamp': expiration_timestamp,
        'event': EVENT_INFO,
    })

def confirm_payment(request):
    if request.method != 'POST':
        return redirect('checkout')

    locked_ids = request.session.get('locked_tickets', [])
    buyer = request.session.get('pending_buyer')

    if not locked_ids or not buyer:
        messages.error(request, 'Không tìm thấy giao dịch đang chờ thanh toán.')
        return redirect('index')

    with transaction.atomic():
        tickets = Ticket.objects.select_for_update().filter(number__in=locked_ids).order_by('number')
        if tickets.count() != len(locked_ids) or tickets.exclude(status='LOCKED').exists():
            messages.error(request, 'Ghế đã hết hạn giữ chỗ hoặc đã được bán.')
            return redirect('index')

        first_ticket = tickets.first()
        if first_ticket and first_ticket.locked_at and first_ticket.locked_at + timedelta(minutes=3) <= timezone.now():
            release_expired_tickets()
            messages.error(request, 'Thời gian giữ ghế đã hết.')
            return redirect('index')

        tickets.update(
            status='SOLD',
            buyer_name=buyer['name'],
            buyer_phone=buyer['phone'],
            locked_at=None,
        )

    request.session['last_sold_tickets'] = locked_ids
    request.session.pop('locked_tickets', None)
    request.session.pop('pending_buyer', None)
    return redirect('ticket_success')

def ticket_success(request):
    sold_ids = request.session.get('last_sold_tickets', [])
    if not sold_ids:
        messages.error(request, 'Không tìm thấy vé để hiển thị.')
        return redirect('index')

    tickets = Ticket.objects.filter(number__in=sold_ids, status='SOLD').order_by('number')
    if tickets.count() != len(sold_ids):
        messages.error(request, 'Không tìm thấy đầy đủ vé đã xác nhận.')
        return redirect('index')

    return render(request, 'fundraising/success.html', {
        'tickets': tickets,
        'event': EVENT_INFO,
    })

def cancel_checkout(request):
    """Called when user clicks Back on checkout page"""
    locked_ids = request.session.get('locked_tickets', [])
    if locked_ids:
        Ticket.objects.filter(number__in=locked_ids, status='LOCKED').update(status='AVAILABLE', locked_at=None)
        request.session.pop('locked_tickets', None)
        request.session.pop('pending_buyer', None)
    return redirect('index')

def cancel_transaction(request):
    """Called when user clicks Cancel on success page"""
    sold_ids = request.session.get('last_sold_tickets', [])
    if sold_ids:
        # Revert SOLD tickets to AVAILABLE
        Ticket.objects.filter(number__in=sold_ids, status='SOLD').update(status='AVAILABLE', buyer_name=None, buyer_phone=None)
        if 'last_sold_tickets' in request.session:
            del request.session['last_sold_tickets']
        messages.info(request, 'Đã hủy giao dịch.')
    return redirect('index')

def generate_ticket_image(ticket):
    """
    Generate a performance ticket image with the seat label overlaid on the official Tickets template.
    Returns a PIL Image object.
    """
    # 1. Resolve template image path (try Tickets.png, fallback to Tickets.jpg)
    template_path = os.path.join(
        settings.BASE_DIR,
        'fundraising',
        'static',
        'fundraising',
        'images',
        'Tickets.png'
    )
    if not os.path.exists(template_path):
        template_path = os.path.join(
            settings.BASE_DIR,
            'fundraising',
            'static',
            'fundraising',
            'images',
            'Tickets.jpg'
        )

    if os.path.exists(template_path):
        img = Image.open(template_path).convert("RGB")
    else:
        img = Image.new("RGB", (1063, 2126), "#f1e2c2")

    w, h = img.size
    draw = ImageDraw.Draw(img)

    # 2. Resolve font (clean, uniform bold sans-serif matching ticket typography)
    font_dir = os.path.join(settings.BASE_DIR, 'fundraising', 'static', 'fundraising', 'fonts')
    roboto_bold_path = os.path.join(font_dir, 'Roboto-Bold.ttf')

    try:
        font_seat = ImageFont.truetype(roboto_bold_path, 140)
    except Exception:
        font_seat = ImageFont.load_default()

    # 3. Render seat code only, mathematically centered in the designated space
    code = ticket.seat_label
    bbox = draw.textbbox((0, 0), code, font=font_seat)
    cx = w // 2
    cy = 1247  # Center between "HÀNH TRÌNH TỪ CỘI NGUỒN ĐẾN TƯƠNG LAI" and "18h30"

    tx = cx - (bbox[0] + bbox[2]) // 2
    ty = cy - (bbox[1] + bbox[3]) // 2

    # Draw seat code with deep warm bronze color matching the poster text
    draw.text((tx, ty), code, font=font_seat, fill='#4a2d17')

    return img

def download_ticket(request, ticket_id):
    """
    Download a single ticket image with the ticket number overlaid.
    """
    # Get the ticket
    ticket = get_object_or_404(Ticket, id=ticket_id)
    allowed_tickets = {str(number) for number in request.session.get('last_sold_tickets', [])}
    
    # Verify ticket is sold and belongs to the confirmed session.
    if ticket.status != 'SOLD' or str(ticket.number) not in allowed_tickets:
        messages.error(request, 'Vé này chưa được xác nhận thanh toán.')
        return redirect('index')
    
    # Generate the ticket image
    img = generate_ticket_image(ticket)
    
    # Save to bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)
    
    # Create HTTP response
    response = HttpResponse(buffer, content_type='image/jpeg')
    response['Content-Disposition'] = f'attachment; filename="ve_hon_viet_{ticket.seat_label}.jpg"'

    return response

def serve_ticket_image(request, ticket_id):
    """
    Serve the ticket image inline (for <img> tags).
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    allowed_tickets = {str(number) for number in request.session.get('last_sold_tickets', [])}
    if ticket.status != 'SOLD' or str(ticket.number) not in allowed_tickets:
        messages.error(request, 'Vé này chưa được xác nhận thanh toán.')
        return redirect('index')

    img = generate_ticket_image(ticket)

    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)

    return HttpResponse(buffer, content_type='image/jpeg')


def download_all_tickets(request):
    """
    Download all purchased tickets as a ZIP file.
    """
    # Get tickets from session
    sold_ids = request.session.get('last_sold_tickets', [])

    if not sold_ids:
        messages.error(request, 'Không tìm thấy vé để tải.')
        return redirect('index')

    # Get tickets from database
    tickets = Ticket.objects.filter(number__in=sold_ids, status='SOLD')

    if not tickets.exists():
        messages.error(request, 'Không tìm thấy vé để tải.')
        return redirect('index')

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for ticket in tickets:
            # Generate ticket image
            img = generate_ticket_image(ticket)

            # Save image to bytes buffer
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=95)
            img_buffer.seek(0)

            # Add to ZIP
            zip_file.writestr(f've_hon_viet_{ticket.seat_label}.jpg', img_buffer.getvalue())

    zip_buffer.seek(0)

    # Create HTTP response
    response = HttpResponse(zip_buffer, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="ve_hon_viet_tat_ca.zip"'

    return response

def submit_message(request):
    if request.method == 'POST':
        name = request.POST.get('name', 'Khách vãng lai').strip() or 'Khách vãng lai'
        phone = request.POST.get('phone', '').strip()
        message = request.POST.get('message', '').strip()

        if message:
            UserMessage.objects.create(
                name=name,
                phone=phone,
                message=message
            )
            return JsonResponse({'status': 'success', 'message': 'Cảm ơn bạn đã gửi góp ý!'})
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập nội dung góp ý.'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'}, status=405)
