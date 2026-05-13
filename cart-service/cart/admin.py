from django.contrib import admin
from .models import Cart, CartItem, Wishlist, WishlistItem, Coupon


admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Wishlist)
admin.site.register(WishlistItem)
admin.site.register(Coupon)