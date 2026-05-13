from django.db import models

class DailySales(models.Model):
    date = models.DateField(unique=True)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.IntegerField(default=0)
    total_items_sold = models.IntegerField(default=0)
    active_orders = models.IntegerField(default=0)
    low_stock_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name_plural = 'Daily Sales'

    def __str__(self):
        return f"Sales for {self.date}"

    @property
    def profit(self):
        return self.total_revenue - self.total_cost

class ProductDailyAnalytics(models.Model):
    product_id = models.PositiveIntegerField()
    date = models.DateField()
    views = models.IntegerField(default=0)
    sales_count = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    
    class Meta:
        unique_together = ['product_id', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"Product {self.product_id} - {self.date}"
