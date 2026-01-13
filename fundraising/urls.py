from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('lock/', views.lock_tickets, name='lock_tickets'),
    path('checkout/', views.checkout, name='checkout'),
    path('cancel-checkout/', views.cancel_checkout, name='cancel_checkout'),
    path('cancel-transaction/', views.cancel_transaction, name='cancel_transaction'),
]
