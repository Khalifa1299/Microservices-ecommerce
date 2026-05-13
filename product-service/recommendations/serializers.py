from rest_framework import serializers
from products.serializers import ProductSerializer
from .models import UserProductInteraction, ProductSimilarity, FrequentlyBoughtTogether


class UserProductInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProductInteraction
        fields = ['id', 'product', 'interaction_type', 'timestamp', 'weight']
        read_only_fields = ['id', 'timestamp', 'weight']


class ProductSimilaritySerializer(serializers.ModelSerializer):
    similar_product = ProductSerializer(read_only=True)
    
    class Meta:
        model = ProductSimilarity
        fields = ['similar_product', 'similarity_score', 'similarity_type']


class RecommendationSerializer(serializers.Serializer):
    """Serializer for recommendation responses"""
    products = ProductSerializer(many=True, read_only=True)
    recommendation_type = serializers.CharField()
    total_count = serializers.IntegerField()


class TrackInteractionSerializer(serializers.Serializer):
    """Serializer for tracking user interactions"""
    product_id = serializers.IntegerField()
    interaction_type = serializers.ChoiceField(
        choices=['view', 'add_to_cart', 'purchase', 'wishlist', 'search']
    )