from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Product endpoints
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category-detail'),
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/images/', views.ProductImageView.as_view(), name='product-images'),
    path('products/<int:pk>/variants/', views.ProductVariantView.as_view(), name='product-variants'),
    
    # Discount endpoints
    path('discounts/', views.DiscountListView.as_view(), name='discount-list'),
    path('discounts/<int:pk>/', views.DiscountDetailView.as_view(), name='discount-detail'),
    
    # Main search endpoint using Algolia
    path('search/', views.unified_search, name='algolia-search'),
    
    # Keep fallback endpoints
    path('search/fallback/', views.algolia_search_products, name='fallback-search'),
]
