from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    # Review endpoints
    path('reviews/', views.ReviewListView.as_view(), name='review-list'),
    path('reviews/<int:pk>/', views.ReviewDetailView.as_view(), name='review-detail'),
    path('reviews/create/', views.ReviewCreateView.as_view(), name='review-create'),
    path('reviews/<int:pk>/update/', views.ReviewUpdateView.as_view(), name='review-update'),
    path('reviews/<int:pk>/delete/', views.ReviewDeleteView.as_view(), name='review-delete'),
    
    # Product reviews
    path('products/<int:product_id>/reviews/', views.ProductReviewListView.as_view(), name='product-reviews'),
    path('products/<int:product_id>/reviews/create/', views.ProductReviewCreateView.as_view(), name='product-review-create'),
]
