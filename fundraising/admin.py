from django.contrib import admin
from .models import Ticket, UserMessage

from django.utils.html import format_html

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('seat_label_display', 'seat_type_display', 'price_display_admin', 'status_badge', 'buyer_name', 'buyer_phone', 'locked_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('number', 'buyer_name', 'buyer_phone')
    ordering = ('number',)
    readonly_fields = ('updated_at',)
    actions = ['mark_as_sold', 'mark_as_available', 'export_to_excel']
    
    fieldsets = (
        ('Thông tin ghế', {
            'fields': ('number', 'status')
        }),
        ('Thông tin người mua', {
            'fields': ('buyer_name', 'buyer_phone')
        }),
        ('Thời gian', {
            'fields': ('locked_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'AVAILABLE': 'green',
            'LOCKED': 'orange',
            'SOLD': 'red',
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
        queryset.update(status='AVAILABLE', buyer_name=None, buyer_phone=None, locked_at=None)
        self.message_user(request, f"Đã hủy và mở lại {queryset.count()} ghế.")
    mark_as_available.short_description = "Hủy ghế / Xóa thông tin người mua"

    def export_to_excel(self, request, queryset):
        import openpyxl
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="seats.xlsx"'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tickets"
        
        columns = ['Ghế', 'Loại ghế', 'Giá vé', 'Trạng Thái', 'Tên Người Mua', 'SĐT', 'Thời gian Khóa', 'Cập nhật lần cuối']
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
                ticket.buyer_phone,
                start_time,
                updated_time,
            ]
            ws.append(row)
            
        wb.save(response)
        return response
    export_to_excel.short_description = "Xuất ra Excel"

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

        columns = ['Họ và tên', 'Số điện thoại', 'Nội dung góp ý', 'Thời gian gửi']
        ws.append(columns)

        for item in queryset:
            created_time = item.created_at.replace(tzinfo=None) if item.created_at else ''
            ws.append([item.name, item.phone, item.message, created_time])

        wb.save(response)
        return response
    export_feedback_to_excel.short_description = "Xuất danh sách góp ý ra Excel"
