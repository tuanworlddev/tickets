from functools import lru_cache
from django.db import models
import uuid

SEAT_COLUMNS = ['E1', 'D1', 'C1', 'B1', 'A1', 'A2', 'B2', 'C2', 'D2', 'E2']
SEAT_ROWS = 12
GUEST_SEAT_SECTIONS = {'A1', 'A2'}
GUEST_SEAT_ROWS = set(range(1, 6))

DEFAULT_SEAT_PRICES = {
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


class SeatPrice(models.Model):
    SEAT_TYPE_CHOICES = [
        ('A', 'Hạng A'),
        ('B', 'Hạng B'),
        ('C', 'Hạng C'),
        ('D', 'Hạng D'),
        ('E', 'Hạng E'),
    ]

    seat_type = models.CharField(max_length=1, choices=SEAT_TYPE_CHOICES, unique=True, verbose_name="Hạng ghế")
    price = models.PositiveIntegerField(verbose_name="Giá vé")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

    class Meta:
        ordering = ['seat_type']
        verbose_name = "Bảng giá vé"
        verbose_name_plural = "Bảng giá vé"

    def __str__(self):
        return f"Hạng {self.seat_type} - {format_currency(self.price)}"

    @property
    def price_display(self):
        return format_currency(self.price)


@lru_cache(maxsize=1)
def get_seat_price_map():
    prices = DEFAULT_SEAT_PRICES.copy()
    try:
        prices.update(dict(SeatPrice.objects.values_list('seat_type', 'price')))
    except Exception:
        pass
    return prices


def get_seat_price(seat_type):
    return get_seat_price_map().get(seat_type, DEFAULT_SEAT_PRICES[seat_type])


def clear_seat_price_cache():
    get_seat_price_map.cache_clear()


def ensure_default_seat_prices():
    for seat_type, price in DEFAULT_SEAT_PRICES.items():
        SeatPrice.objects.get_or_create(seat_type=seat_type, defaults={'price': price})


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('AVAILABLE', 'Còn trống'),
        ('LOCKED', 'Đang giữ'),
        ('PENDING', 'Chờ xác nhận'),
        ('SOLD', 'Đã bán'),
    ]

    number = models.PositiveIntegerField(unique=True, verbose_name="Số ghế nội bộ", help_text="Seat number in the venue map")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', verbose_name="Trạng thái")
    
    # Buyer Info (only filled when sold or pending payment)
    buyer_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Họ tên người mua", help_text="Saint Name + Full Name")
    buyer_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Số điện thoại cũ")
    buyer_email = models.EmailField(blank=True, null=True, verbose_name="Email người mua")
    
    # Locking mechanism
    # We might want a session ID or similar, but for simplicity we rely on status.
    # locked_at can help cleanup stale locks.
    locked_at = models.DateTimeField(blank=True, null=True, verbose_name="Thời gian giữ ghế")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

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
        return get_seat_price(self.seat_type)

    @property
    def price_display(self):
        return format_currency(self.price)

    class Meta:
        ordering = ['number']
        verbose_name = "Ghế/Vé"
        verbose_name_plural = "Quản lý ghế & vé"


class PaymentOrder(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Chờ xác nhận'),
        ('CONFIRMED', 'Đã xác nhận'),
        ('CANCELLED', 'Đã hủy'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tickets = models.ManyToManyField(Ticket, related_name='payment_orders')
    buyer_name = models.CharField(max_length=255, verbose_name="Họ tên người mua")
    buyer_email = models.EmailField(verbose_name="Email người mua")
    amount = models.PositiveIntegerField(verbose_name="Số tiền")
    confirmation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name="Mã xác nhận")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="Trạng thái")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    confirmed_at = models.DateTimeField(blank=True, null=True, verbose_name="Thời gian xác nhận")

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
