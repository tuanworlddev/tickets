import requests
import io
import zipfile
import os
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from PIL import Image, ImageDraw, ImageFont
from .models import Ticket

def release_expired_tickets():
    cleanup_threshold = timezone.now() - timedelta(minutes=3)
    expired = Ticket.objects.filter(status='LOCKED', locked_at__lt=cleanup_threshold)
    count = expired.count()
    if count > 0:
        expired.update(status='AVAILABLE', locked_at=None)
    return count

def index(request):
    release_expired_tickets()
    tickets_list = Ticket.objects.all().order_by('number')
    paginator = Paginator(tickets_list, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'fundraising/index.html', {'page_obj': page_obj})

def lock_tickets(request):
    if request.method == 'POST':
        ticket_numbers = request.POST.getlist('ticket_numbers')
        if not ticket_numbers:
            messages.error(request, 'Please select at least one ticket.')
            return redirect('index')
        
        # Convert to integers
        try:
            ticket_numbers = [int(n) for n in ticket_numbers]
        except ValueError:
             messages.error(request, 'Invalid ticket numbers.')
             return redirect('index')

        with transaction.atomic():
            # Check availability
            tickets = Ticket.objects.filter(number__in=ticket_numbers)
            if tickets.count() != len(ticket_numbers):
                messages.error(request, 'Some tickets not found.')
                return redirect('index')
            
            unavailable = tickets.exclude(status='AVAILABLE')
            if unavailable.exists():
                msg = ", ".join([str(t.number) for t in unavailable])
                messages.error(request, f'Tickets {msg} are no longer available.')
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
        messages.error(request, 'No tickets selected.')
        return redirect('index')
    
    tickets = Ticket.objects.filter(number__in=locked_ids)
    
    # Check if any ticket is missing
    if tickets.count() != len(locked_ids):
         messages.error(request, 'Ticket information incorrect.')
         return redirect('index')

    # Verify all tickets are still LOCKED (and thus belong to this session mostly)
    # If a ticket is SOLD or AVAILABLE, it means it expired or was taken.
    if tickets.exclude(status='LOCKED').exists():
         messages.error(request, 'Reservation expired or tickets sold.')
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
             messages.error(request, 'Ticket reservation expired.')
             return redirect('index')
        
        expiration_timestamp = expire_at.timestamp()
    
    # Calculate total
    total_amount = tickets.count() * 10000
    
    if request.method == 'POST':
        # Process Payment confirmation
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        
        if not name or not phone:
             messages.error(request, 'Please fill in all fields.')
             return render(request, 'fundraising/checkout.html', {'tickets': tickets, 'total_amount': total_amount})

        # Update tickets
        with transaction.atomic():
            tickets.update(
                status='SOLD',
                buyer_name=name,
                buyer_phone=phone
            )
            # Store sold tickets in session for cancellation possibility
            request.session['last_sold_tickets'] = locked_ids
            # Clear locked session
            del request.session['locked_tickets']
            
            # Call VietQR API
            qr_url = None
            try:
                api_url = "https://api.vietqr.io/v2/generate"
                payload = {
                    "accountNo": 6816617815,
                    "accountName": "HUYNH BAO TRONG",
                    "acqId": 970407,
                    "amount": total_amount,
                    "addInfo": f"Thanh Toan Tien Ve So {name}",
                    "format": "text",
                    "template": "compact2"
                }
                
                headers = {
                    "x-client-id": settings.VIETQR_CLIENT_ID,
                    "x-api-key": settings.VIETQR_API_KEY,
                    "Content-Type": "application/json"
                }
                
                response = requests.post(api_url, json=payload, headers=headers)
                data = response.json()
                
                if data.get("code") == "00":
                    qr_url = data.get("data", {}).get("qrDataURL")
            except Exception as e:
                print(f"Error generating QR: {e}")

            return render(request, 'fundraising/success.html', {'tickets': tickets, 'qr_url': qr_url, 'amount': total_amount})

    return render(request, 'fundraising/checkout.html', {
        'tickets': tickets, 
        'total_amount': total_amount,
        'expiration_timestamp': expiration_timestamp
    })

def cancel_checkout(request):
    """Called when user clicks Back on checkout page"""
    locked_ids = request.session.get('locked_tickets', [])
    if locked_ids:
        Ticket.objects.filter(number__in=locked_ids, status='LOCKED').update(status='AVAILABLE', locked_at=None)
        del request.session['locked_tickets']
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

def generate_ticket_image(ticket_number):
    """
    Generate a ticket image with the ticket number overlaid on the bottom-right corner.
    Returns a PIL Image object.
    """
    # Path to the base ticket template
    template_path = os.path.join(
        settings.BASE_DIR,
        'fundraising',
        'static',
        'fundraising',
        'images',
        'veso.jpg'
    )

    # Open the base image
    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ✅ Format ticket number (001, 002, ..., 100)
    formatted_number = f"{int(ticket_number):03d}"
    text = f"{formatted_number}"

    # Load font
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        try:
            font = ImageFont.truetype("Arial.ttf", 48)
        except:
            font = ImageFont.load_default()

    # Calculate text size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Position: bottom-right corner
    padding = 15
    img_width, img_height = img.size
    x = img_width - text_width - padding - 118
    y = img_height - text_height - padding - 43

    # ✅ Draw text (black, no background)
    draw.text(
        (x, y),
        text,
        font=font,
        fill=(0, 0, 0)  # black text
    )

    return img

def download_ticket(request, ticket_id):
    """
    Download a single ticket image with the ticket number overlaid.
    """
    # Get the ticket
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    # Verify ticket is sold (optional security check)
    if ticket.status != 'SOLD':
        messages.error(request, 'Vé này chưa được mua.')
        return redirect('index')
    
    # Generate the ticket image
    img = generate_ticket_image(ticket.number)
    
    # Save to bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=95)
    buffer.seek(0)
    
    # Create HTTP response
    response = HttpResponse(buffer, content_type='image/jpeg')
    response['Content-Disposition'] = f'attachment; filename="ve_so_{ticket.number}.jpg"'
    
    return response

def serve_ticket_image(request, ticket_id):
    """
    Serve the ticket image inline (for <img> tags).
    """
    ticket = get_object_or_404(Ticket, id=ticket_id)
    img = generate_ticket_image(ticket.number)
    
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
            img = generate_ticket_image(ticket.number)
            
            # Save image to bytes buffer
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=95)
            img_buffer.seek(0)
            
            # Add to ZIP
            zip_file.writestr(f've_so_{ticket.number}.jpg', img_buffer.getvalue())
    
    zip_buffer.seek(0)
    
    # Create HTTP response
    response = HttpResponse(zip_buffer, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="ve_so_tat_ca.zip"'
    
    return response
