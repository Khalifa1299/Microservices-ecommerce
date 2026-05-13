from django.db import transaction
from django.utils import timezone
from django.db.models import F, Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.core.paginator import Paginator
import logging
from django.conf import settings
from algoliasearch_django import raw_search
from django.core.cache import cache

ALGOLIA_AVAILABLE = bool(settings.ALGOLIA.get('APPLICATION_ID') and settings.ALGOLIA.get('API_KEY'))

# Add this line to create the logger instance
logger = logging.getLogger(__name__)

from .models import Category, Product, ProductAnalytics, ProductImage, ProductMerchandising, ProductVariant, Discount
from .serializers import (
    CategorySerializer, ProductSerializer, ProductImageSerializer,
    ProductVariantSerializer, DiscountSerializer,
)


# --- CONSTANTS ---
MIN_SEARCH_QUERY_LENGTH = 3
SHORT_QUERY_LENGTH = 2
DEFAULT_INDEX_NAME = 'products'

# Category Views
class CategoryListView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

# Product Views
class ProductListView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_active', 'brand']
    search_fields = ['name', 'description', 'brand'
    ]
    ordering_fields = ['created_at', 'base_price', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).select_related('category').prefetch_related('variants', 'images')
        
        # Track popular searches
        search_query = self.request.query_params.get('search')
        if search_query:
            self.track_search_query(search_query)
        
        return queryset

    def track_search_query(self, query):
        """Track search queries for analytics"""
        try:
            from django.core.cache import cache
            cache_key = f"search_query:{query.lower()}"
            current_count = cache.get(cache_key, 0)
            cache.set(cache_key, current_count + 1, 86400)  # Store for 24 hours
            
            # Also log popular searches
            if current_count > 10:  # If searched more than 10 times
                logger.info(f"Popular search query: {query} (searched {current_count + 1} times)")
        except Exception as e:
            logger.error(f"Error tracking search query: {str(e)}")

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'pk'

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related('category').prefetch_related('variants', 'images')

    def retrieve(self, request, *args, **kwargs):
        """Override to track product views and serve from cache when possible"""
        pk = kwargs['pk']
        cache_key = f'detail:{pk}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        instance = self.get_object()
        self.track_product_view(instance, request)
        self.update_search_weight(instance)
        serializer = self.get_serializer(instance)
        data = serializer.data
        cache.set(cache_key, data, 300)  # 5 min TTL
        return Response(data)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        cache.delete(f'detail:{kwargs["pk"]}')
        return response

    def destroy(self, request, *args, **kwargs):
        cache.delete(f'detail:{kwargs["pk"]}')
        return super().destroy(request, *args, **kwargs)

    def track_product_view(self, product, request):
        """Track product views for analytics"""
        try:
            with transaction.atomic():
                # Create or update analytics record
                analytics, created = ProductAnalytics.objects.get_or_create(
                    product=product,
                    defaults={
                        'total_views': 1,
                        'last_viewed_at': timezone.now(),
                        'total_sales_count': 0,
                        'conversion_rate': 0.0
                    }
                )
                
                if not created:
                    analytics.total_views = F('total_views') + 1
                    analytics.last_viewed_at = timezone.now()
                    analytics.save(update_fields=['total_views', 'last_viewed_at'])

                # Track unique daily views
                from django.core.cache import cache
                user_ip = self.get_client_ip(request)
                cache_key = f"product_view:{product.id}:{user_ip}:{timezone.now().date()}"
                
                if not cache.get(cache_key):
                    cache.set(cache_key, True, 86400)  # 24 hours
                    analytics.unique_daily_views = F('unique_daily_views') + 1
                    analytics.save(update_fields=['unique_daily_views'])

        except Exception as e:
            logger.error(f"Error tracking product view: {str(e)}")

    def update_search_weight(self, product):
        """Update search weight based on popularity metrics"""
        try:
            analytics = getattr(product, 'analytics', None)
            if analytics:
                # Calculate search weight based on views, sales, etc.
                view_score = min(analytics.total_views / 100, 5)  # Max 5 points from views
                sales_score = min(analytics.total_sales_count / 10, 3)  # Max 3 points from sales
                recency_score = self.calculate_recency_score(analytics.last_viewed_at)
                
                total_weight = 1 + view_score + sales_score + recency_score
                
                # Update or create merchandising record
                merchandising, created = ProductMerchandising.objects.get_or_create(
                    product=product,
                    defaults={'search_weight': total_weight}
                )
                
                if not created:
                    merchandising.search_weight = total_weight
                    merchandising.popularity_score = (view_score + sales_score) * 10
                    merchandising.save(update_fields=['search_weight', 'popularity_score'])

        except Exception as e:
            logger.error(f"Error updating search weight: {str(e)}")

    def calculate_recency_score(self, last_viewed_at):
        """Calculate recency score based on last view time"""
        if not last_viewed_at:
            return 0
        
        days_since_last_view = (timezone.now() - last_viewed_at).days
        if days_since_last_view <= 1:
            return 2
        elif days_since_last_view <= 7:
            return 1
        elif days_since_last_view <= 30:
            return 0.5
        else:
            return 0

    def get_client_ip(self, request):
        """Get client IP for tracking unique views"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def update_merchandising(self, request, pk=None):
        """Manual merchandising updates"""
        try:
            product = self.get_object()
            data = request.data
            
            merchandising, created = ProductMerchandising.objects.get_or_create(
                product=product,
                defaults={
                    'search_weight': data.get('search_weight', 1),
                    'featured_on_homepage': data.get('featured_on_homepage', False),
                    'popularity_score': data.get('popularity_score', 0)
                }
            )
            
            if not created:
                for field in ['search_weight', 'featured_on_homepage', 'popularity_score']:
                    if field in data:
                        setattr(merchandising, field, data[field])
                merchandising.save()
            
            return Response({
                'message': 'Merchandising updated successfully',
                'data': {
                    'search_weight': merchandising.search_weight,
                    'featured_on_homepage': merchandising.featured_on_homepage,
                    'popularity_score': merchandising.popularity_score
                }
            })
        
        except Exception as e:
            return Response(
                {'error': f'Error updating merchandising: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get product analytics data"""
        try:
            product = self.get_object()
            analytics = getattr(product, 'analytics', None)
            merchandising = getattr(product, 'merchandising', None)
            
            if not analytics:
                return Response({'message': 'No analytics data available'})
            
            data = {
                'total_views': analytics.total_views,
                'unique_daily_views': analytics.unique_daily_views,
                'total_sales_count': analytics.total_sales_count,
                'conversion_rate': analytics.conversion_rate,
                'last_viewed_at': analytics.last_viewed_at,
                'search_weight': merchandising.search_weight if merchandising else 1,
                'popularity_score': merchandising.popularity_score if merchandising else 0,
                'featured_on_homepage': merchandising.featured_on_homepage if merchandising else False
            }
            
            return Response(data)
        
        except Exception as e:
            return Response(
                {'error': f'Error retrieving analytics: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

class ProductImageView(generics.ListCreateAPIView):
    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        return ProductImage.objects.filter(product__id=self.kwargs['pk'], product__is_active=True)

    def perform_create(self, serializer):
        product = generics.get_object_or_404(Product, id=self.kwargs['pk'], is_active=True)
        serializer.save(product=product)

class DiscountListView(generics.ListCreateAPIView):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'start_date', 'end_date']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'start_date', 'end_date']
    ordering = ['-created_at']
class DiscountDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    
# Add analytics tracking to other views
class ProductVariantView(generics.ListCreateAPIView):
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        return ProductVariant.objects.filter(
            product__id=self.kwargs['pk'], 
            product__is_active=True, 
            is_active=True
        )

    def create(self, request, *args, **kwargs):
        """Create variant and track merchandising data"""
        try:
            with transaction.atomic():
                # Create variant
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                variant = serializer.save(product_id=self.kwargs['pk'])

                # Create inventory
                warehouse = Warehouse.objects.filter(is_active=True).first()
                if not warehouse:
                    warehouse = Warehouse.objects.create(
                        name="Orabi Store",
                        location="162 Rashid st next to Ahmed Orabi Metro Station",
                        is_active=True
                    )

                StockLocation.objects.create(
                    variant=variant,
                    warehouse=warehouse,
                    stock=getattr(variant, 'stock', 0),
                    reserved_quantity=0,
                    low_stock_threshold=getattr(variant, 'low_stock_threshold', 5),
                    reorder_point=getattr(variant, 'reorder_point', 10),
                    max_stock_level=getattr(variant, 'max_stock_level', 100)
                )

                # Initialize analytics for the parent product
                ProductAnalytics.objects.get_or_create(
                    product=variant.product,
                    defaults={
                        'total_views': 0,
                        'total_sales_count': 0,
                        'conversion_rate': 0.0
                    }
                )

                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating variant: {str(e)}")
            raise ValidationError(f"Failed to create variant: {str(e)}")


# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# ------------------------ Unified Search with Algolia ------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

# ==============================================================================
# 1. CORE SEARCH ENDPOINT (CLEANER CONTROL FLOW)
# ==============================================================================

@api_view(['GET'])
def unified_search(request):
    """
    Unified search endpoint with intelligent intent detection.
    Searches across products, brands, categories, and other attributes.
    """
    # 1. Parameter Parsing
    params = parse_search_params(request)
    query = params['query']

    # Initialize response structure
    response_data = {
        "show_suggestions": bool(query),
        "show_results": bool(query),
        "query": query,
        "results": [],
        "suggestions": [],
        "popular_searches": [],
        "categories": [],
        "facets": {},
        "filters": {
            "category": params.get("category"),
            "brand": params.get("brand"),
            "sort_by": params.get("sort_by"),
            "min_price": params.get("min_price"),
            "max_price": params.get("max_price"),
        },
        "total_count": 0,
        "total_pages": 0,
        "has_next": False,
        "has_previous": False,
        "search_intent": None,  # Intent detection results
    }
    
    # Always include popular searches if requested
    if params['include_popular']:
        response_data['popular_searches'] = get_popular_searches()
    
    # --- Handle Empty Query ---
    if not query:
        response_data.update(handle_empty_query())
        response_data['show_suggestions'] = False
        response_data['show_results'] = False
        return Response(response_data)
    
    # --- Handle Short Query (1-2 chars) ---
    if len(query) <= SHORT_QUERY_LENGTH:
        if params["include_suggestions"]:
            response_data["suggestions"] = get_enhanced_suggestions(query)
        response_data["show_suggestions"] = True
        response_data["show_results"] = False
        return Response(response_data)
    
    # --- Full Search with Intent Detection ---
    track_search_query(query)
    
    # Detect search intent (brand, category, or product)
    search_intent = detect_search_intent(query)
    response_data['search_intent'] = search_intent
    
    # Apply detected filters automatically
    if search_intent['type'] == 'brand' and 'brand' in search_intent['filters']:
        params['brand'] = search_intent['filters']['brand']
        logger.info(f"Auto-applying brand filter: {params['brand']}")
    elif search_intent['type'] == 'category' and 'category' in search_intent['filters']:
        params['category'] = search_intent['filters']['category']
        logger.info(f"Auto-applying category filter: {params['category']}")
    
    # Get suggestions
    if params["include_suggestions"]:
        response_data["suggestions"] = get_enhanced_suggestions(query, search_intent)
    
    # Perform the search
    search_results = algolia_search_products(params)
    
    response_data.update(search_results)
    response_data['show_suggestions'] = True
    response_data['show_results'] = True
    
    return Response(response_data)


# ==============================================================================
# 2. HELPER FUNCTIONS FOR UNIFIED_SEARCH
# ==============================================================================

def parse_search_params(request):
    """Parses and sanitizes all request query parameters."""
    return {
        'query': request.GET.get('q', '').strip(),
        'category': request.GET.get('category'),
        'min_price': request.GET.get('min_price'),
        'max_price': request.GET.get('max_price'),
        'brand': request.GET.get('brand'),
        'sort_by': request.GET.get('sort_by', 'relevance'),
        'page': int(request.GET.get('page', 1)),
        'per_page': int(request.GET.get('per_page', 20)),
        'include_suggestions': request.GET.get('suggestions', 'true').lower() == 'true',
        'include_popular': request.GET.get('popular', 'true').lower() == 'true',
    }

def detect_search_intent(query):
    """
    Flexible search intent detection that analyzes the query against multiple product attributes.
    Returns matches for brands, categories, and any other searchable fields.
    """
    query_lower = query.lower().strip()
    intent = {
        'type': 'product',  # Default
        'matches': {},
        'filters': {},
        'suggestions': []
    }
    
    if not query or len(query) < 2:
        return intent
    
    # Define searchable attributes and their configurations
    search_config = [
        {
            'name': 'brand',
            'field': 'brand',
            'model': Product,
            'display_name': 'Brand',
            'icon': 'business',
            'priority': 10  # Higher priority = checked first for exact matches
        },
        {
            'name': 'category',
            'field': 'name',
            'model': Category,
            'display_name': 'Category',
            'icon': 'category',
            'priority': 10
        },
    ]
    
    # Search across all configured attributes
    for config in search_config:
        try:
            model = config['model']
            field = config['field']
            attr_name = config['name']
            
            # Build query filter
            filter_kwargs = {f'{field}__icontains': query}
            if hasattr(model, 'is_active'):
                filter_kwargs['is_active'] = True
            
            # Execute query
            if model == Category:
                results = model.objects.filter(**filter_kwargs).values('id', 'name')[:5]
                matches = list(results)
                logger.debug(f"Category matches for query '{query}': {matches}")
            else:
                results = model.objects.filter(**filter_kwargs).values_list(field, flat=True).distinct()[:5]
                matches = [r for r in results if r]  # Filter out None/empty
            
            if matches:
                # Store matches
                intent['matches'][attr_name] = matches
                
                # Check for exact match
                is_exact = False
                if model == Category:
                    is_exact = any(m['name'].lower() == query_lower for m in matches)
                    if is_exact:
                        exact_match = next(m for m in matches if m['name'].lower() == query_lower)
                        intent['filters']['category'] = exact_match['id']
                else:
                    is_exact = any(str(m).lower() == query_lower for m in matches)
                    if is_exact:
                        intent['filters'][attr_name] = query
                
                # Set type if exact match with highest priority
                if is_exact and (intent['type'] == 'product' or config['priority'] > 
                    next((c['priority'] for c in search_config if c['name'] == intent['type']), 0)):
                    intent['type'] = attr_name
                
                # Add to suggestions
                for match in matches[:2]:  # Limit to 2 per attribute
                    if model == Category:
                        intent['suggestions'].append({
                            'text': match['name'],
                            'type': attr_name,
                            'subtitle': config['display_name'],
                            'icon': config['icon'],
                            'value': match['id'] if attr_name == 'category' else match['name']
                        })
                    else:
                        intent['suggestions'].append({
                            'text': str(match),
                            'type': attr_name,
                            'subtitle': config['display_name'],
                            'icon': config['icon'],
                            'value': match
                        })
        
        except Exception as e:
            logger.warning(f"{config['display_name']} detection failed: {e}")
    
    return intent

def handle_empty_query():
    """Handles the empty search state (no query)."""
    return {
        'categories': get_search_categories(),
        'featured_products': get_featured_products_algolia(),
    }


# ==============================================================================
# 3. ALGOLIA SEARCH PRODUCT LOGIC (CLEANER)
# ==============================================================================

def build_algolia_filters(params):
    """Constructs the Algolia filters string and numeric filters list."""
    filters = ['is_active:true']
    numeric_filters = []

    # Category filter
    if params['category']:
        try:
            category_name = Category.objects.get(id=params['category']).name
            filters.append(f'get_category_name:"{category_name}"')
        except Category.DoesNotExist:
            logger.warning(f"Category ID {params['category']} not found.")

    # Brand filter - FIX: Use different quotes or escape
    if params['brand']:
        filters.append(f"get_brand_name:\"{params['brand']}\"")
        
    # Numeric filters for price
    if params['min_price']:
        numeric_filters.append(f"get_total_price >= {params['min_price']}")
    if params['max_price']:
        numeric_filters.append(f"get_total_price <= {params['max_price']}")
        
    return ' AND '.join(filters), numeric_filters

def get_algolia_sort_index(sort_by):
    """Maps a user-friendly sort_by string to an Algolia index suffix."""
    prefix = f"{settings.ALGOLIA.get('INDEX_PREFIX', '')}{DEFAULT_INDEX_NAME}"
    
    sort_map = {
        'price_low': f'{prefix}_price_asc',
        'price_high': f'{prefix}_price_desc',
        'popularity': f'{prefix}_popularity_desc',
        'newest': f'{prefix}_created_desc',
        'name': f'{prefix}_name_asc',
    }
    # For 'relevance', we return None to use the primary index
    return sort_map.get(sort_by, None)


def algolia_search_products(params):
    if not ALGOLIA_AVAILABLE:
        logger.warning("Algolia not configured — using fallback search.")
        return fallback_database_search(**params)

    filters_str, numeric_filters = build_algolia_filters(params)
    
    # If searching by category only, use empty query for broader results
    search_query = params['query']
    if params.get('category') and not params.get('brand'):
        # Check if the query matches the category name
        try:
            category = Category.objects.get(id=params['category'])
            if category.name.lower() == search_query.lower():
                search_query = ""  # Empty query to get all products in category
                logger.info(f"Category-only search detected, using empty query for category: {category.name}")
        except Category.DoesNotExist:
            pass
    
    search_params = {
        'filters': filters_str,
        'page': max(params.get('page', 1) - 1, 0),
        'hitsPerPage': params.get('per_page', 20),
        'numericFilters': numeric_filters,
        'facets': ['get_category_name', 'get_brand_name', 'get_price_range'],
    }

    logger.info(f"🔍 Algolia Search: query='{search_query}', filters='{filters_str}'")

    try:
        results = raw_search(Product, search_query, search_params)
        hits = results.get('hits', [])
        
        logger.info(f"✅ Algolia returned {len(hits)} hits out of {results.get('nbHits', 0)} total")
        
        products_data = resolve_algolia_hits_to_products(hits)
        return {
            'results': products_data,
            'total_count': results.get('nbHits', 0),
            'page': params['page'],
            'total_pages': results.get('nbPages', 1),
            'has_next': params['page'] < results.get('nbPages', 1),
            'has_previous': params['page'] > 1,
            'facets': results.get('facets', {}),
            'processing_time_ms': results.get('processingTimeMS', 0),
            'filters': {k: v for k, v in params.items() if k in ['category', 'min_price', 'max_price', 'brand', 'sort_by']},
        }
    except Exception as exc:
        logger.exception(f"Algolia raw_search failed: {exc}")
        return fallback_database_search(**params)

def resolve_algolia_hits_to_products(hits):
    """
    Batch-fetches product data from the database based on Algolia results (hits)
    and serializes it.
    """
    object_ids = [hit['objectID'] for hit in hits]
    
    # Fetch all products in one query using the objectIDs
    products_map = {
        str(p.id): p for p in Product.objects.filter(id__in=object_ids)
    }
    
    products_data = []
    
    for hit in hits:
        product = products_map.get(hit['objectID'])
        if product:
            # Use the ProductSerializer to get complete data
            serializer = ProductSerializer(product, context={'request': None})
            product_data = serializer.data
            
            # Add Algolia-specific data to the serialized output
            product_data['_algolia_score'] = hit.get('_rankingInfo', {}).get('nbTypos', 0)
            product_data['_highlighted'] = hit.get('_highlightResult', {})
            
            products_data.append(product_data)
        else:
            logger.warning(f"Product {hit['objectID']} found in Algolia but not in database")
            
    return products_data


# ==============================================================================
# 4. OTHER UTILITY FUNCTIONS (NO MAJOR CHANGES NEEDED)
# ==============================================================================

def _format_suggestions(raw, category=None):
    formatted = []
    for item in raw:
        if not item:
            continue
        if isinstance(item, dict):
            text_value = item.get("text")
            if isinstance(text_value, dict):
                text_value = (
                    text_value.get("text")
                    or text_value.get("value")
                    or str(text_value)
                )
            formatted.append(
                {
                    "text": text_value or "",
                    "type": item.get("type", "product"),
                    "category": item.get("category", category),
                }
            )
        else:
            formatted.append(
                {"text": str(item), "type": "product", "category": category}
            )
    return formatted

def get_algolia_suggestions(query, limit=5):
    if not query:
        return []
    if not ALGOLIA_AVAILABLE:
        return _format_suggestions(get_database_suggestions(query, limit))
    try:
        params = {
            "hitsPerPage": limit,
            "attributesToRetrieve": ["name"],
            "attributesToHighlight": ["name"],
            "typoTolerance": "min",
        }
        response = raw_search(Product, query, params)
        seen, names = set(), []
        for hit in response.get("hits", []):
            name = hit.get("name")
            if name and name not in seen:
                names.append(name)
                seen.add(name)
        logger.info(f"Algolia suggestions for '{query}': {names}")
        return _format_suggestions(names or get_database_suggestions(query, limit))
    except Exception as exc:
        logger.warning(f"Algolia suggestions failed ({exc}); using DB fallback.")
        return _format_suggestions(get_database_suggestions(query, limit))


def get_enhanced_suggestions(query, search_intent=None, limit=5):
    """
    Returns mixed suggestions including products and any matched attributes.
    """
    suggestions = []
    
    if not query:
        return suggestions
    
    # Get product name suggestions first
    product_suggestions = get_algolia_suggestions(query, limit=3)
    suggestions.extend(product_suggestions)
    
    # Add attribute-based suggestions from intent detection
    if search_intent and 'suggestions' in search_intent:
        for suggestion in search_intent['suggestions']:
            suggestions.append({
                "text": suggestion['text'],
                "type": suggestion['type'],
                "subtitle": suggestion.get('subtitle'),
                "icon": suggestion.get('icon'),
                "value": suggestion.get('value'),
                "category": suggestion.get('value') if suggestion['type'] == 'category' else None
            })
    
    return suggestions[:limit]


def get_featured_products_algolia(limit=8):
    if not ALGOLIA_AVAILABLE:
        return get_database_featured_products(limit)

    try:
        params = {
            "filters": "is_active:true AND featured_on_homepage:true",
            "hitsPerPage": limit,
            "page": 0,
            "attributesToRetrieve": ["objectID"],
        }
        response = raw_search(Product, "", params)
        hits = response.get("hits", [])
        if not hits:
            return get_database_featured_products(limit)
        resolved = resolve_algolia_hits_to_products(hits)
        return resolved[:limit]
    except Exception as exc:
        logger.warning(f"Algolia featured products failed ({exc}); using DB fallback.")
        return get_database_featured_products(limit)


def fallback_database_search(**kwargs):
    query = kwargs.get("query", "")
    category_id = kwargs.get("category") or kwargs.get("category_id")
    min_price = kwargs.get("min_price")
    max_price = kwargs.get("max_price")
    brand = kwargs.get("brand")
    sort_by = kwargs.get("sort_by", "relevance")
    page = kwargs.get("page", 1)
    per_page = kwargs.get("per_page", 20)

    try:
        products = Product.objects.filter(is_active=True).select_related(
            "category"
        ).prefetch_related("variants", "images")

        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(brand__icontains=query)
            )

        if category_id:
            products = products.filter(category_id=category_id)

        if brand:
            products = products.filter(brand__icontains=brand)

        if min_price:
            products = products.filter(base_price__gte=min_price)
        if max_price:
            products = products.filter(base_price__lte=max_price)

        ordering_map = {
            "price_low": "base_price",
            "price_high": "-base_price",
            "newest": "-created_at",
            "popularity": "-merchandising__popularity_score",
            "name": "name",
        }
        products = products.order_by(ordering_map.get(sort_by, "-created_at"))

        paginator = Paginator(products, per_page)
        page_obj = paginator.get_page(page)
        serializer = ProductSerializer(page_obj, many=True)

        return {
            "results": serializer.data,
            "total_count": paginator.count,
            "page": page,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "facets": {},
            "fallback": True,
            "filters": {
                k: v
                for k, v in kwargs.items()
                if k in ["category", "min_price", "max_price", "brand", "sort_by"]
            },
        }
    except Exception as exc:
        logger.error(f"Fallback search error: {exc}")
        return {
            "results": [],
            "total_count": 0,
            "page": 1,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False,
            "error": str(exc),
            "fallback": True,
        }


def get_database_suggestions(query, limit=5):
    if not query:
        return []
    try:
        qs = (
            Product.objects.filter(is_active=True, name__icontains=query)
            .order_by("-merchandising__popularity_score", "-created_at")
            .values_list("name", flat=True)
            .distinct()[:limit]
        )
        return list(qs)
    except Exception as exc:
        logger.warning(f"Database suggestions error: {exc}")
        return []


def get_database_featured_products(limit=8):
    try:
        products = (
            Product.objects.filter(is_active=True, merchandising__featured_on_homepage=True)
            .select_related("category")
            .prefetch_related("variants", "images")[:limit]
        )
        return ProductSerializer(products, many=True).data
    except Exception as exc:
        logger.warning(f"Database featured products error: {exc}")
        return []


def get_popular_searches(limit=5):
    try:
        top_products = (
            ProductAnalytics.objects.select_related("product")
            .order_by("-total_views")[:limit]
        )
        return [
            {"query": analytics.product.name, "count": analytics.total_views}
            for analytics in top_products
            if analytics.product
        ]
    except Exception as exc:
        logger.warning(f"Popular searches lookup failed: {exc}")
        return []


def get_search_categories(limit=10):
    try:
        categories = (
            Category.objects.filter(is_active=True)
            .order_by("-created_at")
            .values("id", "name")[:limit]
        )
        return list(categories)
    except Exception as exc:
        logger.warning(f"Search categories lookup failed: {exc}")
        return []


def track_search_query(query):
    if not query:
        return
    try:
        cache_key = f"search_query:{query.lower()}"
        current = cache.get(cache_key, 0) + 1
        cache.set(cache_key, current, 86400)
        if current > 25:
            logger.info(f"Trending search: '{query}' ({current} hits today)")
    except Exception as exc:
        logger.debug(f"Search query tracking failed: {exc}")