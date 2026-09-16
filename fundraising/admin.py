from django.contrib import admin
from .models import (
    PaymentOrder,
    SeatPrice,
    Ticket,
    UserMessage,
    clear_seat_price_cache,
    format_currency,
)

from django.utils.html import format_html

admin.site.site_header = "Hồn Việt - Quản lý vé"
admin.site.site_title = "Hồn Việt Admin"
admin.site.index_title = "Bảng điều khiển"


class SeatTypeListFilter(admin.SimpleListFilter):
    title = 'Hạng ghế'
    parameter_name = 'seat_type'

    def lookups(self, request, model_admin):
        return (
            ('A', 'Hạng A'),
            ('B', 'Hạng B'),
            ('C', 'Hạng C'),
            ('D', 'Hạng D'),
            ('E', 'Hạng E'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        numbers = [
            number for number in queryset.model.objects.values_list('number', flat=True)
            if queryset.model(number=number).seat_type == value
        ]
        return queryset.filter(number__in=numbers)


@admin.register(SeatPrice)
class SeatPriceAdmin(admin.ModelAdmin):
    list_display = ('seat_type_display', 'price', 'price_display_admin', 'updated_at')
    list_editable = ('price',)
    readonly_fields = ('price_display_admin', 'updated_at')
    ordering = ('seat_type',)
    list_per_page = 10

    fieldsets = (
        ('Bảng giá', {
            'fields': ('seat_type', 'price', 'price_display_admin')
        }),
        ('Theo dõi', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        clear_seat_price_cache()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        clear_seat_price_cache()

    def seat_type_display(self, obj):
        return f"Hạng {obj.seat_type}"
    seat_type_display.short_description = 'Hạng ghế'
    seat_type_display.admin_order_field = 'seat_type'

    def price_display_admin(self, obj):
        return obj.price_display
    price_display_admin.short_description = 'Hiển thị'


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('seat_label_display', 'seat_type_display', 'price_display_admin', 'status_badge', 'buyer_name', 'buyer_email', 'locked_at', 'updated_at')
    list_filter = ('status', SeatTypeListFilter)
    search_fields = ('number', 'buyer_name', 'buyer_email')
    ordering = ('number',)
    readonly_fields = ('updated_at',)
    actions = ['mark_as_sold', 'mark_as_available', 'clear_locked_seats', 'export_to_excel']
    list_per_page = 50
    
    fieldsets = (
        ('Thông tin ghế', {
            'fields': ('number', 'status')
        }),
        ('Thông tin người mua', {
            'fields': ('buyer_name', 'buyer_email')
        }),
        ('Thời gian', {
            'fields': ('locked_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'AVAILABLE': '#198754',
            'LOCKED': '#fd7e14',
            'PENDING': '#0d6efd',
            'SOLD': '#dc3545',
        }
        color = colors.get(obj.status, 'gray')
        label = obj.get_status_display()
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 10px; font-weight: bold;">{}</span>',
            color, label
        )
    status_badge.short_description = 'Trạng thái'
    status_badge.admin_order_field = 'status'

    def seat_label_display(self, obj):
        return obj.seat_label
    seat_label_display.short_description = 'Ghế'
    seat_label_display.admin_order_field = 'number'

    def seat_type_display(self, obj):
        return obj.seat_type
    seat_type_display.short_description = 'Loại ghế'

    def price_display_admin(self, obj):
        return obj.price_display
    price_display_admin.short_description = 'Giá vé'

    def mark_as_sold(self, request, queryset):
        queryset.update(status='SOLD')
        self.message_user(request, f"Đã đánh dấu {queryset.count()} ghế là ĐÃ BÁN.")
    mark_as_sold.short_description = "Đánh dấu là ĐÃ BÁN"

    def mark_as_available(self, request, queryset):
        queryset.update(status='AVAILABLE', buyer_name=None, buyer_phone=None, buyer_email=None, locked_at=None)
        self.message_user(request, f"Đã hủy và mở lại {queryset.count()} ghế.")
    mark_as_available.short_description = "Hủy ghế / Xóa thông tin người mua"

    def clear_locked_seats(self, request, queryset):
        count = queryset.filter(status='LOCKED').update(status='AVAILABLE', locked_at=None)
        self.message_user(request, f"Đã mở lại {count} ghế đang khóa.")
    clear_locked_seats.short_description = "Mở lại các ghế đang khóa"

    def export_to_excel(self, request, queryset):
        import openpyxl
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="seats.xlsx"'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tickets"
        
        columns = ['Ghế', 'Loại ghế', 'Giá vé', 'Trạng Thái', 'Tên Người Mua', 'Email', 'Thời gian Khóa', 'Cập nhật lần cuối']
        ws.append(columns)
        
        for ticket in queryset:
            start_time = ticket.locked_at.replace(tzinfo=None) if ticket.locked_at else ''
            updated_time = ticket.updated_at.replace(tzinfo=None) if ticket.updated_at else ''
            row = [
                ticket.seat_label,
                ticket.seat_type,
                ticket.price,
                ticket.get_status_display(),
                ticket.buyer_name,
                ticket.buyer_email,
                start_time,
                updated_time,
            ]
            ws.append(row)
            
        wb.save(response)
        return response
    export_to_excel.short_description = "Xuất ra Excel"


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('buyer_name', 'buyer_email', 'amount_display', 'status', 'seat_labels_display', 'created_at', 'confirmed_at')
    list_filter = ('status', 'created_at', 'confirmed_at')
    search_fields = ('buyer_name', 'buyer_email')
    readonly_fields = ('id', 'confirmation_token', 'created_at', 'confirmed_at', 'seat_labels_display')
    filter_horizontal = ('tickets',)
    ordering = ('-created_at',)

    def amount_display(self, obj):
        return format_currency(obj.amount)
    amount_display.short_description = 'Số tiền'

    def seat_labels_display(self, obj):
        return obj.seat_labels
    seat_labels_display.short_description = 'Ghế'


@admin.register(UserMessage)
class UserMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'short_message', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'phone', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('name', 'phone', 'message', 'created_at')
    actions = ['export_feedback_to_excel']

    def short_message(self, obj):
        if len(obj.message) > 80:
            return obj.message[:80] + '...'
        return obj.message
    short_message.short_description = 'Nội dung góp ý'

    def export_feedback_to_excel(self, request, queryset):
        import openpyxl
        from django.http import HttpResponse

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="gop_y_khach_hang.xlsx"'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Góp ý khách hàng"

        columns = ['Họ và tên', 'Thông tin liên hệ', 'Nội dung góp ý', 'Thời gian gửi']
        ws.append(columns)

        for item in queryset:
            created_time = item.created_at.replace(tzinfo=None) if item.created_at else ''
            ws.append([item.name, item.phone, item.message, created_time])

        wb.save(response)
        return response
    export_feedback_to_excel.short_description = "Xuất danh sách góp ý ra Excel"
