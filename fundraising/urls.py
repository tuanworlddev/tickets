from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('lock/', views.lock_tickets, name='lock_tickets'),
    path('checkout/', views.checkout, name='checkout'),
    path('confirm-payment/', views.confirm_payment, name='confirm_payment'),
    path('payment-pending/<uuid:order_id>/', views.payment_pending, name='payment_pending'),
    path('owner-confirm-payment/<uuid:token>/', views.owner_confirm_payment, name='owner_confirm_payment'),
    path('tickets/', views.ticket_success, name='ticket_success'),
    path('cancel-checkout/', views.cancel_checkout, name='cancel_checkout'),
    path('cancel-transaction/', views.cancel_transaction, name='cancel_transaction'),
    path('download-ticket/<int:ticket_id>/', views.download_ticket, name='download_ticket'),
    path('download-all-tickets/', views.download_all_tickets, name='download_all_tickets'),
    path('ticket-image/<int:ticket_id>/', views.serve_ticket_image, name='serve_ticket_image'),
    path('submit-message/', views.submit_message, name='submit_message'),
]
