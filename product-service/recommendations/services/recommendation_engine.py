from django.db.models import Count, Q, F, Sum, Avg
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
import numpy as np 
from typing import List, Dict, Tuple
from products.models import Product
from recommendations.models import (
    UserProductInteraction, 
    ProductSimilarity, 
    FrequentlyBoughtTogether, 
    UserRecommendationCache,
)


class RecommendationEngine:

    # interation Weights
    INTERACTION_WEIGHTS = {
        'view': 1.0,
        'add_to_cart': 3.0,
        'purchase': 5.0,
        'wishlist': 2.0,
        'search':0.5,
    }

    def __init__(self, user=None, session_id=None):
        self.user = user
        self.session_id = session_id
    
    def getPersonalizedRecommendations(self, limit=10, exclude_product_ids=None):
        if not self.user:
            return self._get_trending_products(limit)
        
        # Check cache first
        cached = self._get_cached_recommendations('personalized')
        if cached:
            return self._filter_and_limit_products(cached, limit, exclude_product_ids)
        
        # combine multiple strategies
        recommendations = []

        # 1. Starting with collaborative filtering  ( 40% Weight )
        collab_recs = self._get_collaborative_filtering_recommendations(limit*2)
        recommendations.extend([(prod, score*0.4) for prod, score in collab_recs])

        # 2. Then add content-based recommendations ( 30% Weight )
        content_recs = self._get_content_based_recommendations(limit*2)
        recommendations.extend([(prod, score*0.3) for prod, score in content_recs])

        # 3. Category-based recommendations ( 20% Weight )
        category_recs = self._get_category_based_recommendations(limit*2)
        recommendations.extend([(prod, score*0.2) for prod, score in category_recs])

        # 4. Finally, trending products ( 10% Weight )
        trending_recs = self._get_trending_products(limit*2)
        recommendations.extend([(prod, score*0.1) for prod, score in trending_recs])

        
        # Aggregate scores
        aggregated_scores = defaultdict(float)
        for prod, score in recommendations:
            aggregated_scores[prod] += score
        
        # Sort by aggregated score and get top recommendations
        sorted_recommendations = sorted(aggregated_scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        products = [prod for prod, score in sorted_recommendations]

        # cache the results 
        self._cache_recommendations(products, 'personalized')

        return self._filter_and_limit_products(products, limit, exclude_product_ids)
    
    def get_similar_products(self, product_id, limit=6):
        try: 
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return []
        
        # check pre-computed similarities
        similar = ProductSimilarity.objects.filter(
            product=product
        ).select_related('similar_product').order_by('-similarity_score')[:limit]

        if similar.count() >= limit:
            return [sim.similar_product for sim in similar]
        
        # Fallback : compute on-the-fly using basic attributes
        return self.compute_similar_products(product, limit)
    
    def get_frequently_bought_together(self, product_id, limit=4):
        bought_together = FrequentlyBoughtTogether.objects.filter(
            product1_id=product_id
        ).select_related('product2').order_by('-confidence', 'frequency')[:limit]
        
        return [item.product2 for item in bought_together]
    
    def get_users_also_viewed(self, product_id, limit=6):
        # get user who viewed this product
        user_ids = UserProductInteraction.objects.filter(
            product_id=product_id,
            interaction_type='view',
            time_stamp__gte=timezone.now() - timedelta(days=30)
        ).values_list('user_id', flat=True).distinct()

        # get other products viewed by these users
        also_viewed = UserProductInteraction.objects.filter(
            user_id__in=user_ids,
            interaction_type='view',
            time_stamp__gte=timezone.now() - timedelta(days=30),
        ).exclude(product_id=product_id
        ).values('product_id').annotate(
            view_count=Count('id')
        ).order_by('-view_count')[:limit]
        
        product_ids = [item['product_id'] for item in also_viewed]
        return Product.objects.filter(id__in=product_ids)
    
    def track_interaction(self, product_id, interaction_type):
        weight = self.INTERACTION_WEIGHTS.get(interaction_type, 1.0)

        UserProductInteraction.objects.create(
            user=self.user,
            session_id=self.session_id,
            product_id=product_id,
            interaction_type=interaction_type,
            time_stamp=timezone.now(), 
            weight=weight,
        )
    
    # private methods for different recommendation strategies
    def _get_collaborative_filtering_recommendations(self, limit):
        # Implementation of collaborative filtering logic
        
        # get user's interactions
        user_interactions = UserProductInteraction.objects.filter(
            user=self.user, 
            time_stamp__gte=timezone.now() - timedelta(days=90)
        ).values_list('product_id', flat=True).distinct()

        if not user_interactions:
            return []
        
        # find similar users : user who interacted with same products
        similar_users = UserProductInteraction.objects.filter(
            product_id__in=user_interactions).exclude(user=self.user
        ).values('user').annotate(
            common_products=Count('product') ).order_by('-common_products')[:50]
        
        similar_user_ids = [item['user'] for item in similar_users]

        # get products interacted by similar users but not by current user
        recommended_products = UserProductInteraction.objects.filter(
            user_id__in=similar_user_ids
        ).exclude(
            product_id__in=user_interactions
        ).values('product_id').annotate(
            score=Sum('weight')
        ).order_by('-score')[:limit]

        product_ids = [item['product_id'] for item in recommended_products]
        products = Product.objects.filter(id__in=product_ids, is_active=True)

        return [(prod, 1.0) for prod in products]
    
    def _get_content_based_recommendations(self, limit):
        # Implementation of content-based filtering logic
        # For simplicity, using product tags and description similarity
        
        favorite_products = UserProductInteraction.objects.filter(
            user=self.user, 
            interaction_type__in=['wishlist', 'add_to_cart', 'purchase'],
            time_stamp__gte=timezone.now() - timedelta(days=90)
        ).values('product').annotate(
            total_weight=Sum('weight')
        ).order_by('-total_weight')[:10]

        if not favorite_products:
            return []
        
        favorite_products_ids = [item['product'] for item in favorite_products]
        # get similar products based on tags and description
        similar_products = ProductSimilarity.objects.filter(
            product_id__in=favorite_products_ids,).exclude(product_id__in=favorite_products_ids
        ).values('similar_product').annotate(
            avg_score=Avg('similarity_score')).order_by('-avg_score')[:limit]
        
        product_ids = [item['similar_product'] for item in similar_products]
        products = Product.objects.filter(id__in=product_ids, is_active=True)

        return [(prod, 1.0) for prod in products]
    
    def _get_category_based_recommendations(self, limit):
        # Recommend products from user's favorite categories
        favorite_categories = UserProductInteraction.objects.filter(
            user=self.user,
            time_stamp__gte=timezone.now() - timedelta(days=90)
        ).values('product__category').annotate(
            total_weight=Sum('weight'), 
            interaction_count=Count('id'),
        ).order_by('-total_weight')[:5]

        if not favorite_categories:
            return []
        
        category_ids = [item['product__category'] for item in favorite_categories]

        # Get user's already interacted products
        interacted_products = UserProductInteraction.objects.filter(
            user=self.user
        ).values_list('product_id', flat=True).distinct()
        
        # Get top products from these categories
        recommended_products = Product.objects.filter(
            category_id__in=category_ids,
            is_active=True
        ).exclude(
            id__in=interacted_products).annotate(
                total_views = Count('interactions', filter= Q(interactions__interaction_type='view'))
                ).order_by('-total_views')[:limit]

        return [(prod, 1.0) for prod in recommended_products]
    

    def _trending_in_user_interests(self, limit):
        """Get trending products in categories user is interested in"""
        # Get user's interested categories
        user_categories = UserProductInteraction.objects.filter(
            user=self.user,
            timestamp__gte=timezone.now() - timedelta(days=30)
        ).values_list('product__category_id', flat=True).distinct()
        
        if not user_categories:
            return []
        
        # Get trending products from last 7 days in these categories
        trending = Product.objects.filter(
            category_id__in=user_categories,
            is_active=True
        ).annotate(
            recent_interactions=Count(
                'interactions',
                filter=Q(interactions__timestamp__gte=timezone.now() - timedelta(days=7))
            )
        ).filter(recent_interactions__gt=0).order_by('-recent_interactions')[:limit]
        
        return [(prod, 1.0) for prod in trending]
    
    def _get_trending_products(self, limit):
        """Get overall trending products (for non-authenticated users)"""
        trending = Product.objects.filter(
            is_active=True
        ).annotate(
            recent_interactions=Count(
                'interactions',
                filter=Q(interactions__timestamp__gte=timezone.now() - timedelta(days=7))
            )
        ).filter(recent_interactions__gt=0).order_by('-recent_interactions')[:limit]
        
        return list(trending)
    
    def _compute_similar_products(self, product, limit):
        """Compute similar products on-the-fly"""
        # Similar by category and tags
        similar = Product.objects.filter(
            category=product.category,
            is_active=True
        ).exclude(id=product.id)
        
        # Add tag-based similarity if you have tags
        # similar = similar.filter(tags__in=product.tags.all()).distinct()
        
        return list(similar[:limit])
    
    def _get_cached_recommendations(self, recommendation_type):
        """Get cached recommendations if available and not expired"""
        if not self.user:
            return None
        
        try:
            cache = UserRecommendationCache.objects.get(
                user=self.user,
                recommendation_type=recommendation_type,
                expires_at__gt=timezone.now()
            )
            product_ids = [item['id'] for item in cache.recommended_products]
            return Product.objects.filter(id__in=product_ids, is_active=True)
        except UserRecommendationCache.DoesNotExist:
            return None
    
    def _cache_recommendations(self, products, recommendation_type, ttl_hours=24):
        """Cache recommendations for faster retrieval"""
        if not self.user:
            return
        
        product_data = [{'id': p.id, 'score': 1.0} for p in products]
        expires_at = timezone.now() + timedelta(hours=ttl_hours)
        
        UserRecommendationCache.objects.update_or_create(
            user=self.user,
            recommendation_type=recommendation_type,
            defaults={
                'recommended_products': product_data,
                'expires_at': expires_at
            }
        )
    
    def _filter_and_limit_products(self, products, limit, exclude_product_ids):
        """Filter out excluded products and limit results"""
        if exclude_product_ids:
            products = [p for p in products if p.id not in exclude_product_ids]
        return products[:limit]