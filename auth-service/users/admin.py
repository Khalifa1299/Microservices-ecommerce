from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Address, UserProfile, UserActivity

# Register User with custom UserAdmin
admin.site.register(User, UserAdmin)

# Simple registration for other models
admin.site.register(Address)
admin.site.register(UserProfile)
admin.site.register(UserActivity) 