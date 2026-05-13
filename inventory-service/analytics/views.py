from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count
from .models import DailySales, ProductDailyAnalytics

class AnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['get'])
    def dashboard_summary(self, request):
        today = timezone.now().date()
        
        # Get today's sales
        daily_sales, _ = DailySales.objects.get_or_create(date=today)
        
       
        return Response({
            'today_revenue': daily_sales.total_revenue,
            'today_orders': daily_sales.total_orders,
            'active_orders': daily_sales.active_orders,
            'low_stock_items': daily_sales.low_stock_count
        })

    @action(detail=False, methods=['get'])
    def sales_chart(self, request):
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now().date() - timedelta(days=days)
        
        sales_data = DailySales.objects.filter(date__gte=start_date).order_by('date')
        
        return Response([{
            'date': s.date,
            'revenue': s.total_revenue,
            'cost': s.total_cost,
            'profit': s.profit
        } for s in sales_data])
