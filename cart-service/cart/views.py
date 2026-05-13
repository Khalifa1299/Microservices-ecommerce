from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from .models import Cart, CartItem, Wishlist, WishlistItem, Coupon
from .serializers import CartSerializer, CartItemSerializer, WishlistSerializer, WishlistItemSerializer, CouponSerializer
import logging

logger = logging.getLogger(__name__)


def _invalidate_cart(user_id):
    cache.delete(f'data:{user_id}')


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CART VIEWS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class CartViewSet(viewsets.ModelViewSet):
    """ViewSet for Cart operations"""
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'], url_path='me')
    def get_my_cart(self, request):
        """
        Get the current user's cart
        Returns: The user's cart with items and totals
        """
        cache_key = f'data:{request.user.id}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached, status=status.HTTP_200_OK)

        try:
            # Get or create cart - this ensures cart has a primary key
            cart, created = Cart.objects.get_or_create(user=request.user)

            # If cart was just created, recalculate totals now that it has a pk
            if created:
                cart.save()

            serializer = self.get_serializer(cart)
            cache.set(cache_key, serializer.data, 1800)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error retrieving user cart: {str(e)}")
            return Response(
                {'error': f'Failed to retrieve cart: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='remove-coupon')
    def remove_coupon(self, request):
        """
        Remove a coupon from the user's cart.
        Returns: Updated cart without coupon.
        """
        try:
            cart = Cart.objects.get(user=self.request.user)
            if cart.coupon:
                cart.coupon = None
                cart.save()
                _invalidate_cart(self.request.user.id)

                # Return the entire cart object with the coupon removed
                cart_serializer = self.get_serializer(cart)
                logger.info(f"Coupon removed from cart for user {self.request.user}")
                return Response(data=cart_serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': 'No coupon applied to cart'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Cart.DoesNotExist:
            return Response(
                {'error': 'Cart not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error removing coupon: {str(e)}")
            return Response(
                {'error': f'Failed to remove coupon: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    @action(detail=False, methods=['post'], url_path='apply-coupon')
    def apply_coupon(self, request):
        """
        Apply a coupon to the user's cart.
        Expects: {'coupon_code': 'CODE123'}
        Returns: Updated cart with applied coupon and discount.
        """
        coupon_code = request.data.get('coupon_code')
        if not coupon_code:
            return Response(
                {'error': 'Coupon code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            coupon = Coupon.objects.get(code=coupon_code, active=True)
            serializer = CouponSerializer(coupon)
            if coupon.is_valid():
                cart, created = Cart.objects.get_or_create(user=self.request.user)
                if not cart:  # Assuming Cart has related CartItem objects
                    logger.warning("No cart items found for user %s", self.request.user)
                    return Response(
                        {'error': 'Cart is empty'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                cart.coupon = coupon
                cart.save()
                _invalidate_cart(self.request.user.id)

                logger.info(f"Coupon {coupon_code} applied to cart for user {self.request.user}")
                logger.info(f"new cart total after Coupon applied {cart.discounted_total}")
                
                # Return the entire cart object with the coupon applied
                cart_serializer = self.get_serializer(cart)
                return Response(data=cart_serializer.data, status=status.HTTP_200_OK)
            else:
                logger.error(f"Coupon {coupon_code} is expired or not yet valid")
                return Response(
                    {'error': 'Coupon is expired or not yet valid'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Coupon.DoesNotExist:
            logger.error(f"Coupon {coupon_code} does not exist")
            return Response(
                {'error': 'Invalid coupon code'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error applying coupon {coupon_code}: {str(e)}")
            return Response(
                {'error': f'Failed to apply coupon: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CartItemViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """List user's cart items - matches Flutter structure"""
        queryset = CartItem.objects.filter(cart__user=request.user)
        serializer = CartItemSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })
    
    def create(self, request):
        """Add item to cart - matches Flutter structure"""
        serializer = CartItemSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create cart - ensures cart has a primary key
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        with transaction.atomic():
            # Set user from request
            cart_item = serializer.save(cart=cart)
            # Recalculate cart totals
            cart.save()

        _invalidate_cart(request.user.id)
        return Response({
            'success': True,
            'message': 'Item added to cart',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    def partial_update(self, request, pk=None):
        """Update cart item quantity - matches Flutter structure"""
        try:
            cart_item = CartItem.objects.select_related('cart').get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CartItemSerializer(cart_item, data=request.data, partial=True)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            serializer.save()
            # Recalculate cart totals
            cart_item.cart.save()

        _invalidate_cart(request.user.id)
        return Response({
            'success': True,
            'message': 'Cart item updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        

    def destroy(self, request, pk=None):
        """Remove item from cart - matches Flutter structure"""
        try:
            cart_item = CartItem.objects.select_related('cart').get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        cart = cart_item.cart
        cart_item.delete()
        # Recalculate cart totals after item deletion
        cart.save()

        _invalidate_cart(request.user.id)
        return Response({
            'success': True,
            'message': 'Item removed from cart'
        }, status=status.HTTP_200_OK)
    
    def retreive(self, request, pk=None):
        """Retrieve a specific cart item"""
        try:
            cart_item = CartItem.objects.select_related('cart').get(pk=pk, cart__user=request.user)
        except CartItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = CartItemSerializer(cart_item)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< WISHLIST VIEWS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------


class WishlistViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """List user's wishlist items"""
        queryset = WishlistItem.objects.filter(user=request.user)
        serializer = WishlistItemSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })
    
    def create(self, request):
        """Add item to wishlist"""
        serializer = WishlistItemSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        wishlist, created = Wishlist.objects.get_or_create(user=request.user)
        
        with transaction.atomic():
            # Set user from request
            wishlist_item = serializer.save(user=request.user, wishlist=wishlist)
        
        wishlist.save()
        
        return Response({
            'success': True,
            'message': 'Item added to wishlist',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    

    def destroy(self, request, pk=None):
        """Remove item from wishlist"""
        try:
            wishlist_item = WishlistItem.objects.get(pk=pk, user=request.user)
        except WishlistItem.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Wishlist item not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        wishlist_item.delete()
        return Response({
            'success': True,
            'message': 'Item removed from wishlist'
        }, status=status.HTTP_200_OK)


