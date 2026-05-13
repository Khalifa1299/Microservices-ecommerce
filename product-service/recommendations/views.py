from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache
from products.models import Product
from products.serializers import ProductSerializer
from .services.recommendation_engine import RecommendationEngine
from .serializers import (
    TrackInteractionSerializer,
    RecommendationSerializer,
    ProductSimilaritySerializer
)
import logging

logger = logging.getLogger(__name__)


class RecommendationViewSet(viewsets.ViewSet):
    """ViewSet for product recommendations"""
    
    def get_permissions(self):
        """Allow some endpoints for unauthenticated users"""
        if self.action in ['similar_products', 'trending', 'users_also_viewed']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['get'])
    def personalized(self, request):
        """
        Get personalized recommendations for the authenticated user
        GET /api/recommendations/personalized/?limit=10&exclude=1,2,3
        """
        try:
            limit = int(request.query_params.get('limit', 10))
            exclude_ids = request.query_params.get('exclude', '')
            exclude_product_ids = [int(x) for x in exclude_ids.split(',') if x]
            
            engine = RecommendationEngine(user=request.user)
            products = engine.get_personalized_recommendations(
                limit=limit,
                exclude_product_ids=exclude_product_ids
            )
            
            serializer = ProductSerializer(products, many=True, context={'request': request})
            
            return Response({
                'products': serializer.data,
                'recommendation_type': 'personalized',
                'total_count': len(serializer.data)
            })
            
        except Exception as e:
            logger.error(f"Error getting personalized recommendations: {str(e)}")
            return Response(
                {'error': 'Failed to get recommendations'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def similar_products(self, request, pk=None):
        """
        Get products similar to a specific product
        GET /api/recommendations/{product_id}/similar_products/?limit=6
        """
        try:
            limit = int(request.query_params.get('limit', 6))
            
            # Try to get from cache first
            cache_key = f'similar_products_{pk}_{limit}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            engine = RecommendationEngine(
                user=request.user if request.user.is_authenticated else None
            )
            products = engine.get_similar_products(product_id=pk, limit=limit)
            
            serializer = ProductSerializer(products, many=True, context={'request': request})
            
            response_data = {
                'products': serializer.data,
                'recommendation_type': 'similar_products',
                'total_count': len(serializer.data)
            }
            
            # Cache for 1 hour
            cache.set(cache_key, response_data, 3600)
            
            return Response(response_data)
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error getting similar products: {str(e)}")
            return Response(
                {'error': 'Failed to get similar products'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def frequently_bought_together(self, request, pk=None):
        """
        Get products frequently bought together with a specific product
        GET /api/recommendations/{product_id}/frequently_bought_together/?limit=4
        """
        try:
            limit = int(request.query_params.get('limit', 4))
            
            cache_key = f'fbt_{pk}_{limit}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            engine = RecommendationEngine(
                user=request.user if request.user.is_authenticated else None
            )
            products = engine.get_frequently_bought_together(product_id=pk, limit=limit)
            
            serializer = ProductSerializer(products, many=True, context={'request': request})
            
            response_data = {
                'products': serializer.data,
                'recommendation_type': 'frequently_bought_together',
                'total_count': len(serializer.data)
            }
            
            # Cache for 2 hours
            cache.set(cache_key, response_data, 7200)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error getting frequently bought together: {str(e)}")
            return Response(
                {'error': 'Failed to get recommendations'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def users_also_viewed(self, request, pk=None):
        """
        Get products that users also viewed after viewing this product
        GET /api/recommendations/{product_id}/users_also_viewed/?limit=6
        """
        try:
            limit = int(request.query_params.get('limit', 6))
            
            cache_key = f'users_also_viewed_{pk}_{limit}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            engine = RecommendationEngine(
                user=request.user if request.user.is_authenticated else None
            )
            products = engine.get_users_also_viewed(product_id=pk, limit=limit)
            
            serializer = ProductSerializer(products, many=True, context={'request': request})
            
            response_data = {
                'products': serializer.data,
                'recommendation_type': 'users_also_viewed',
                'total_count': len(serializer.data)
            }
            
            # Cache for 30 minutes
            cache.set(cache_key, response_data, 1800)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error getting users also viewed: {str(e)}")
            return Response(
                {'error': 'Failed to get recommendations'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """
        Get trending products
        GET /api/recommendations/trending/?limit=10
        """
        try:
            limit = int(request.query_params.get('limit', 10))
            
            cache_key = f'trending_products_{limit}'
            cached_data = cache.get(cache_key)
            
            if cached_data:
                return Response(cached_data)
            
            engine = RecommendationEngine()
            products = engine._get_trending_products(limit=limit)
            
            serializer = ProductSerializer(products, many=True, context={'request': request})
            
            response_data = {
                'products': serializer.data,
                'recommendation_type': 'trending',
                'total_count': len(serializer.data)
            }
            
            # Cache for 15 minutes
            cache.set(cache_key, response_data, 900)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error getting trending products: {str(e)}")
            return Response(
                {'error': 'Failed to get trending products'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def track_interaction(self, request):
        """
        Track user interaction with a product
        POST /api/recommendations/track_interaction/
        Body: {
            "product_id": 1,
            "interaction_type": "view"
        }
        """
        serializer = TrackInteractionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product_id = serializer.validated_data['product_id']
            interaction_type = serializer.validated_data['interaction_type']
            
            # Verify product exists
            Product.objects.get(id=product_id)
            
            # Get session ID for anonymous users
            session_id = None
            if not request.user.is_authenticated:
                if not request.session.session_key:
                    request.session.create()
                session_id = request.session.session_key
            
            engine = RecommendationEngine(
                user=request.user if request.user.is_authenticated else None,
                session_id=session_id
            )
            engine.track_interaction(product_id, interaction_type)
            
            return Response(
                {'message': 'Interaction tracked successfully'},
                status=status.HTTP_201_CREATED
            )
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error tracking interaction: {str(e)}")
            return Response(
                {'error': 'Failed to track interaction'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
