from django.core.management.base import BaseCommand
from fundraising.models import Ticket

class Command(BaseCommand):
    help = 'Initialize 500 tickets'

    def handle(self, *args, **kwargs):
        tickets = []
        existing = Ticket.objects.values_list('number', flat=True)
        count = 0
        for i in range(1, 501):
            if i not in existing:
                tickets.append(Ticket(number=i))
                count += 1
        
        if tickets:
            Ticket.objects.bulk_create(tickets)
            self.stdout.write(self.style.SUCCESS(f'Successfully created {count} tickets'))
        else:
            self.stdout.write(self.style.SUCCESS('All tickets already exist'))
