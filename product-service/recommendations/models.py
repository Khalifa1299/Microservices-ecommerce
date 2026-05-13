from django.db import models
from products.models import Product
from django.utils import timezone

class UserProductInteraction(models.Model):
    """Track user interactions with products"""
    INTERACTION_TYPES = [
        ('view', 'View'),
        ('add_to_cart', 'Add to Cart'),
        ('purchase', 'Purchase'),
        ('wishlist', 'Add to Wishlist'),
        ('search', 'Search'),
    ]
    
    user_id = models.IntegerField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=255, blank=True, null=True)  # For anonymous users
    weight = models.FloatField(default=1.0)  # Different weights for different interactions
    
    class Meta:
        db_table = 'user_product_interactions'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user_id', '-timestamp']),
            models.Index(fields=['product', '-timestamp']),
            models.Index(fields=['session_id', '-timestamp']),
        ]
    
    def __str__(self):
        return f"User {self.user_id} - {self.interaction_type} - {self.product}"


class ProductSimilarity(models.Model):
    """Pre-computed product similarities"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='similar_products')
    similar_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='similar_to')
    similarity_score = models.FloatField()
    similarity_type = models.CharField(max_length=50)  # 'category', 'tags', 'collaborative', etc.
    
    class Meta:
        db_table = 'product_similarities'
        unique_together = ['product', 'similar_product', 'similarity_type']
        ordering = ['-similarity_score']
        indexes = [
            models.Index(fields=['product', '-similarity_score']),
        ]


class FrequentlyBoughtTogether(models.Model):
    """Track products frequently bought together"""
    product1 = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bought_with')
    product2 = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bought_with_reverse')
    frequency = models.IntegerField(default=1)
    confidence = models.FloatField(default=0.0)  # Confidence score for the association
    
    class Meta:
        db_table = 'frequently_bought_together'
        unique_together = ['product1', 'product2']
        ordering = ['-confidence', '-frequency']


class UserRecommendationCache(models.Model):
    """Cache personalized recommendations for users"""
    user_id = models.IntegerField()
    recommended_products = models.JSONField()  # List of product IDs with scores
    recommendation_type = models.CharField(max_length=50)  # 'personalized', 'trending', etc.
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        db_table = 'user_recommendation_cache'
        unique_together = ['user_id', 'recommendation_type']