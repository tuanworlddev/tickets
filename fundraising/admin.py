from django.contrib import admin
from .models import Ticket, UserMessage

from django.utils.html import format_html

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('number', 'status_badge', 'buyer_name', 'buyer_phone', 'locked_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('number', 'buyer_name', 'buyer_phone')
    ordering = ('number',)
    actions = ['mark_as_sold', 'mark_as_available', 'export_to_excel']
    
    fieldsets = (
        ('Thông tin vé', {
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

    def mark_as_sold(self, request, queryset):
        queryset.update(status='SOLD')
        self.message_user(request, f"Đã đánh dấu {queryset.count()} vé là ĐÃ BÁN.")
    mark_as_sold.short_description = "Đánh dấu là ĐÃ BÁN"

    def mark_as_available(self, request, queryset):
        queryset.update(status='AVAILABLE', buyer_name=None, buyer_phone=None, locked_at=None)
        self.message_user(request, f"Đã hủy và mở lại {queryset.count()} vé.")
    mark_as_available.short_description = "Hủy vé / Xóa thông tin người mua"

    def export_to_excel(self, request, queryset):
        import openpyxl
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="tickets.xlsx"'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tickets"
        
        columns = ['Số Vé', 'Trạng Thái', 'Tên Người Mua', 'SĐT', 'Thời gian Khóa', 'Cập nhật lần cuối']
        ws.append(columns)
        
        for ticket in queryset:
            start_time = ticket.locked_at.replace(tzinfo=None) if ticket.locked_at else ''
            updated_time = ticket.updated_at.replace(tzinfo=None) if ticket.updated_at else ''
            row = [
                ticket.number,
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
    list_display = ('name', 'phone', 'message', 'created_at')
    search_fields = ('name', 'phone', 'message')
    ordering = ('-created_at',)
