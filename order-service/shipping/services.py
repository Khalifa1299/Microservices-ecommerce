# apps/shipping/services.py
import hashlib
from decimal import Decimal
from typing import List, Dict
from django.core.cache import cache
from django.db import transaction
from .models import Shipment, ShippingRate

# Helper to load adapters dynamically
def get_carrier_adapter(carrier_name: str):
    # This would usually return a class from your own adapter modules
    # e.g., from .adapters.aramex import AramexAdapter
    # For now, we assume it's a factory function
    pass

class RateService:
    cache_timeout = 60 * 60  # Cache rates for 1 hour
    def get_shipping_rates(self, rate_data: Dict) -> List[Dict]:
        """Get shipping rates with MKH as local default"""
        cache_key = self._generate_cache_key(rate_data)
        cached_rates = cache.get(cache_key)
        
        if cached_rates:
            return cached_rates
        
        rates = []
        
        try:
            carrier_rates = self._calculate_mkh_rates(rate_data)
                #else:
                    # Future-proofing for async API calls
                    #adapter = get_carrier_adapter(carrier)
                    #carrier_rates = adapter.get_rates(rate_data)
                
            rates.append(carrier_rates)
        except Exception as e:
            print(f"Error getting rates: {e}")
        
        cache.set(cache_key, rates, self.cache_timeout)
        return sorted(rates, key=lambda x: x['rate'])


    def _calculate_mkh_rates(self, rate_data: Dict):
        """Local calculation logic for your own store shipping"""
        weight = Decimal(rate_data.get('weight', 0))
        
        
        total_rate = []
        # for standard
        total_rate.append(Decimal('50.00') + (weight * Decimal('5.00')))
        # for express
        total_rate.append(Decimal('100.00') + (weight * Decimal('10.00')))
        # for receive and deliver
        total_rate.append(Decimal('0.00') + (weight * Decimal('0.00')))

        return {
            'carrier': 'mkh',
            'rate': total_rate,
            'transit_days': 2,
            'delivery_date': None # Calculated in the Serializer/View
        }

    def _generate_cache_key(self, rate_data: Dict) -> str:
        # extract the city and district from the text based address field to create a location-based key
        city = rate_data['destination_address'].split(',')[1].strip() if ',' in rate_data['destination_address'] else 'unknown'
        district = rate_data['destination_address'].split(',')[2].strip() if ',' in rate_data['destination_address'] else 'default'
        # We ignore postal_code if it's empty to prevent cache fragmentation
        loc_id = f"{city}-{district}".lower()
        pkg_id = f"{rate_data['weight']}-{rate_data['length']}x{rate_data['width']}x{rate_data['height']}"
        
        combined = f"{loc_id}:{pkg_id}"
        return f"rates:{hashlib.md5(combined.encode()).hexdigest()}"
    

class ShipmentService:

    @transaction.atomic
    def create_shipment(self, validated_data: Dict) -> Shipment:
        # 'order_id' key holds the actual Order object after PrimaryKeyRelatedField validation
        order = validated_data['order_id']

        # destination_address is a TextField snapshot on the Shipment model — store as plain text
        destination_address = validated_data.get('destination_address', '')

        shipment = Shipment.objects.create(
            order=order,
            carrier=validated_data['carrier'],
            service_type=validated_data['service_type'],
            destination_address=str(destination_address),
            weight=validated_data['weight'],
            length=validated_data['length'],
            width=validated_data['width'],
            height=validated_data['height'],
            package_type=validated_data.get('package_type', 'package'),
        )

        return shipment
    

class TrackingService:
    def track_shipment(self, shipment_id: str) -> Dict:
        """Get tracking information for a shipment"""
        try:
            shipment = Shipment.objects.get(id=shipment_id)
            
            if not shipment.tracking_number:
                return {
                    'status': 'No tracking number available',
                    'events': []
                }
            
           
            # Return current data from database
            events = shipment.tracking_events.all()[:10]  # Last 10 events
            
            return {
                'shipment_id': str(shipment.id),
                'tracking_number': shipment.tracking_number,
                'status': shipment.status,
                'estimated_delivery': shipment.estimated_delivery,
                'events': [
                    {
                        'type': event.event_type,
                        'description': event.event_description,
                        'location': event.location,
                        'time': event.event_time
                    }
                    for event in events
                ]
            }
        except Shipment.DoesNotExist:
            raise ValueError("Shipment not found")

