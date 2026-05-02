from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Stock, StockHistory


@receiver(post_save, sender=Stock)
def save_stock_history(sender, instance, created, **kwargs):
    """Save a history record every time a Stock item is saved."""
    StockHistory.objects.create(
        category=instance.category,
        item_name=instance.item_name,
        quantity=instance.quantity,
        receive_quantity=instance.receive_quantity,
        received_by=instance.received_by,
        issue_quantity=instance.issue_quantity,
        issued_by=instance.issued_by,
        issued_to=instance.issued_to,
        phone_number=instance.phone_number,
        created_by=instance.created_by,
        re_order=instance.re_order,
        last_updated=instance.last_updated,
        timestamp=instance.timestamp,
    )
