from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'product', 'user', 'rating', 'title', 'comment',
            'is_approved', 'created_at', 'updated_at',
            'user_name', 'user_email', 'user_avatar'
        ]
        read_only_fields = ['created_at', 'updated_at', 'user', 'is_approved']
    
    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() if obj.user else "Anonymous"
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else ""
    
    def get_user_avatar(self, obj):
        # Return a default avatar or user's avatar if implemented
        return None
