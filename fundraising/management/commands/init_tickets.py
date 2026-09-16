from django.core.management.base import BaseCommand
from fundraising.models import (
    GUEST_SEAT_ROWS,
    GUEST_SEAT_SECTIONS,
    SEAT_COLUMNS,
    SEAT_ROWS,
    Ticket,
    ensure_default_seat_prices,
)

class Command(BaseCommand):
    help = 'Initialize performance seats'

    def handle(self, *args, **kwargs):
        ensure_default_seat_prices()
        self.stdout.write(self.style.SUCCESS('Ensured default seat prices'))

        total_seats = SEAT_ROWS * len(SEAT_COLUMNS)
        removed_count, _ = Ticket.objects.filter(number__gt=total_seats).delete()

        tickets = []
        existing = Ticket.objects.values_list('number', flat=True)
        count = 0
        for i in range(1, total_seats + 1):
            if i not in existing:
                tickets.append(Ticket(number=i))
                count += 1
        
        if tickets:
            Ticket.objects.bulk_create(tickets)
            self.stdout.write(self.style.SUCCESS(f'Successfully created {count} seats'))
        else:
            self.stdout.write(self.style.SUCCESS('All seats already exist'))

        guest_numbers = []
        for row in GUEST_SEAT_ROWS:
            for section in GUEST_SEAT_SECTIONS:
                seat_number = (row - 1) * len(SEAT_COLUMNS) + SEAT_COLUMNS.index(section) + 1
                guest_numbers.append(seat_number)

        Ticket.objects.filter(number__in=guest_numbers).update(
            status='SOLD',
            buyer_name='Ghế khách mời',
            buyer_phone='',
            buyer_email='',
            locked_at=None,
        )
        self.stdout.write(self.style.SUCCESS(f'Marked {len(guest_numbers)} guest seats'))
        if removed_count:
            self.stdout.write(self.style.SUCCESS(f'Removed {removed_count} old lottery tickets'))
