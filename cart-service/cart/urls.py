from . import views
from rest_framework.routers import DefaultRouter


app_name = 'cart'

router = DefaultRouter()
router.register(r'carts', views.CartViewSet, basename='cart')
router.register(r'cart-items', views.CartItemViewSet, basename='cartitem')
router.register(r'wishlist', views.WishlistViewSet, basename='wishlist')
urlpatterns = router.urls


