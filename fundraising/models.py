from django.db import models
import uuid

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('LOCKED', 'Locked'),
        ('SOLD', 'Sold'),
    ]

    number = models.PositiveIntegerField(unique=True, help_text="Ticket number from 1 to 500")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    
    # Buyer Info (only filled when sold or pending payment)
    buyer_name = models.CharField(max_length=255, blank=True, null=True, help_text="Saint Name + Full Name")
    buyer_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Locking mechanism
    # We might want a session ID or similar, but for simplicity we rely on status.
    # locked_at can help cleanup stale locks.
    locked_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ticket #{self.number} - {self.status}"

    class Meta:
        ordering = ['number']

class UserMessage(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    message = models.TextField()
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.name} - {self.phone}"
