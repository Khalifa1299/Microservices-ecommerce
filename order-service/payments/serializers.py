# payments/serializers.py
from rest_framework import serializers
from .models import PaymentMethod, PaymentTransaction, Refund
from django.db import transaction

class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for listing payment methods"""
    masked_card_number = serializers.ReadOnlyField()
    expiry_date = serializers.ReadOnlyField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'cardholder_name',
            'card_number',  # Last 4 digits only
            'masked_card_number',
            'expiry_month',
            'expiry_year',
            'expiry_date',
            'card_type',
            'is_default',
            'billing_address_id',
            'is_expired',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'masked_card_number', 'expiry_date']
    
    def get_is_expired(self, obj):
        return obj.is_expired()

class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment methods with full card details"""
    full_card_number = serializers.CharField(write_only=True, max_length=19, min_length=13)
    cvv = serializers.CharField(write_only=True, max_length=4, min_length=3)
    
    class Meta:
        model = PaymentMethod
        fields = [
            'cardholder_name',
            'full_card_number',
            'expiry_month',
            'expiry_year',
            'cvv',
            'card_type',
            'is_default',
            'billing_address_id',
        ]
    
    def validate_full_card_number(self, value):
        """Validate card number"""
        # Remove spaces and dashes
        card_number = value.replace(' ', '').replace('-', '')
        
        # Check if it's numeric
        if not card_number.isdigit():
            raise serializers.ValidationError("Card number must contain only digits")
        
        # Check length
        if len(card_number) < 13 or len(card_number) > 19:
            raise serializers.ValidationError("Invalid card number length")
        
        return card_number
    
    def validate_expiry_month(self, value):
        """Validate expiry month"""
        try:
            month = int(value)
            if month < 1 or month > 12:
                raise serializers.ValidationError("Month must be between 01 and 12")
        except ValueError:
            raise serializers.ValidationError("Invalid month format")
        return value.zfill(2)  # Ensure 2 digits
    
    def validate_expiry_year(self, value):
        """Validate expiry year"""
        try:
            year = int(value)
            if year < 0 or year > 99:
                raise serializers.ValidationError("Invalid year format")
        except ValueError:
            raise serializers.ValidationError("Invalid year format")
        return value.zfill(2)  # Ensure 2 digits
    
    def validate(self, data):
        """Validate expiry date"""
        from datetime import datetime
        
        try:
            expiry_month = int(data['expiry_month'])
            expiry_year = int(f"20{data['expiry_year']}")
            expiry_date = datetime(expiry_year, expiry_month, 1)
            
            if expiry_date < datetime.now():
                raise serializers.ValidationError("Card has expired")
        except (ValueError, KeyError):
            raise serializers.ValidationError("Invalid expiry date")
        
        return data
    
    def create(self, validated_data):
        """Create payment method"""
        full_card_number = validated_data.pop('full_card_number')
        cvv = validated_data.pop('cvv')  # CVV not stored, used only for validation
        
        # Extract last 4 digits
        last_four = full_card_number[-4:]
        
        # In production, integrate with payment gateway here
        # gateway_token = stripe.Token.create(card={
        #     'number': full_card_number,
        #     'exp_month': validated_data['expiry_month'],
        #     'exp_year': validated_data['expiry_year'],
        #     'cvc': cvv,
        # })
        
        # Create payment method with only last 4 digits
        payment_method = PaymentMethod.objects.create(
            card_number=last_four,
            # gateway_token=gateway_token.id,  # Store token from payment gateway
            **validated_data
        )
        
        return payment_method

class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating payment methods (limited fields)"""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'cardholder_name',
            'expiry_month',
            'expiry_year',
            'is_default',
            'billing_address_id',
        ]
    
    def validate_expiry_month(self, value):
        """Validate expiry month"""
        try:
            month = int(value)
            if month < 1 or month > 12:
                raise serializers.ValidationError("Month must be between 01 and 12")
        except ValueError:
            raise serializers.ValidationError("Invalid month format")
        return value.zfill(2)
    
    def validate_expiry_year(self, value):
        """Validate expiry year"""
        try:
            year = int(value)
            if year < 0 or year > 99:
                raise serializers.ValidationError("Invalid year format")
        except ValueError:
            raise serializers.ValidationError("Invalid year format")
        return value.zfill(2)

class PaymentTransactionSerializer(serializers.ModelSerializer):
    payment_method_details = PaymentMethodSerializer(source='payment_method', read_only=True)
    
    class Meta:
        model = PaymentTransaction
        fields = '__all__'
        read_only_fields = ['transaction_id', 'created_at', 'updated_at']

class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = '__all__'
        read_only_fields = ['created_at']