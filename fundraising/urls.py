from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('lock/', views.lock_tickets, name='lock_tickets'),
    path('checkout/', views.checkout, name='checkout'),
    path('cancel-checkout/', views.cancel_checkout, name='cancel_checkout'),
    path('cancel-transaction/', views.cancel_transaction, name='cancel_transaction'),
    path('download-ticket/<int:ticket_id>/', views.download_ticket, name='download_ticket'),
    path('download-all-tickets/', views.download_all_tickets, name='download_all_tickets'),
    path('ticket-image/<int:ticket_id>/', views.serve_ticket_image, name='serve_ticket_image'),
    path('submit-message/', views.submit_message, name='submit_message'),
]
