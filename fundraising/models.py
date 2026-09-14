from django.db import models
import uuid

SEAT_COLUMNS = ['E1', 'D1', 'C1', 'B1', 'A1', 'A2', 'B2', 'C2', 'D2', 'E2']
SEAT_ROWS = 12
GUEST_SEAT_SECTIONS = {'A1', 'A2'}
GUEST_SEAT_ROWS = set(range(1, 6))

SEAT_PRICES = {
    'A': 99000,
    'B': 89000,
    'C': 79000,
    'D': 79000,
    'E': 79000,
}


def seat_number_for(section, row):
    return (row - 1) * len(SEAT_COLUMNS) + SEAT_COLUMNS.index(section) + 1


def format_currency(amount):
    return f"{amount:,}".replace(",", ".") + "đ"

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('LOCKED', 'Locked'),
        ('PENDING', 'Pending confirmation'),
        ('SOLD', 'Sold'),
    ]

    number = models.PositiveIntegerField(unique=True, help_text="Seat number in the venue map")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    
    # Buyer Info (only filled when sold or pending payment)
    buyer_name = models.CharField(max_length=255, blank=True, null=True, help_text="Saint Name + Full Name")
    buyer_phone = models.CharField(max_length=20, blank=True, null=True)
    buyer_email = models.EmailField(blank=True, null=True)
    
    # Locking mechanism
    # We might want a session ID or similar, but for simplicity we rely on status.
    # locked_at can help cleanup stale locks.
    locked_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.seat_label} - {self.status}"

    @property
    def seat_row(self):
        return ((self.number - 1) // len(SEAT_COLUMNS)) + 1

    @property
    def seat_section(self):
        return SEAT_COLUMNS[(self.number - 1) % len(SEAT_COLUMNS)]

    @property
    def seat_label(self):
        return f"{self.seat_section}-{self.seat_row:02d}"

    @property
    def seat_type(self):
        return self.seat_section[0]

    @property
    def is_guest_seat(self):
        return self.seat_section in GUEST_SEAT_SECTIONS and self.seat_row in GUEST_SEAT_ROWS

    @property
    def price(self):
        return SEAT_PRICES[self.seat_type]

    @property
    def price_display(self):
        return format_currency(self.price)

    class Meta:
        ordering = ['number']


class PaymentOrder(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending confirmation'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tickets = models.ManyToManyField(Ticket, related_name='payment_orders')
    buyer_name = models.CharField(max_length=255)
    buyer_email = models.EmailField()
    amount = models.PositiveIntegerField()
    confirmation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Đơn thanh toán"
        verbose_name_plural = "Đơn thanh toán"

    def __str__(self):
        return f"{self.buyer_name} - {format_currency(self.amount)} - {self.status}"

    @property
    def seat_labels(self):
        return ", ".join(ticket.seat_label for ticket in self.tickets.all().order_by('number'))


class UserMessage(models.Model):
    name = models.CharField(max_length=255, verbose_name="Họ và tên")
    phone = models.CharField(max_length=255, blank=True, verbose_name="Thông tin liên hệ")
    message = models.TextField(verbose_name="Nội dung góp ý")
    is_public = models.BooleanField(default=True, verbose_name="Công khai")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian gửi")

    class Meta:
        verbose_name = "Góp ý của khách"
        verbose_name_plural = "Danh sách góp ý của khách"
        ordering = ['-created_at']

    def __str__(self):
        return f"Góp ý từ {self.name} ({self.phone or 'Không có thông tin liên hệ'})"
