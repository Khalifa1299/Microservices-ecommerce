from django.core.management.base import BaseCommand
import pandas as pd
from products.models import (
    Product, ProductVariant, ProductImage, 
    ProductAttribute, ProductAttributeValue, Category
)
from django.db import transaction
from django.core.files import File
from django.utils.text import slugify
import logging
import requests
from io import BytesIO
from decimal import Decimal

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import products with variants, attributes, and images from Excel sheets'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to Excel file')

    def download_image(self, url):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return BytesIO(response.content)
        except Exception as e:
            logger.error(f"Error downloading image from {url}: {str(e)}")
        return None

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        
        # Read all sheets
        products_df = pd.read_excel(file_path, sheet_name='Products')
        variants_df = pd.read_excel(file_path, sheet_name='Variants')
        attributes_df = pd.read_excel(file_path, sheet_name='Attributes')
        images_df = pd.read_excel(file_path, sheet_name='Images')

        with transaction.atomic():
            # Process products
            for _, row in products_df.iterrows():
                try:
                    product_id = row['id']
                    category, _ = Category.objects.get_or_create(
                        name=row['category'],
                        defaults={'slug': slugify(row['category'])}
                    )

                    product = Product.objects.create(
                        id=product_id,
                        name=row['name'],
                        description=row['description'],
                        base_price=Decimal(str(row['base_price'])),
                        wholesale_price=Decimal(str(row.get('wholesale_price', 0))),
                        category=category,
                        brand=row.get('brand'),
                        origin_country=row.get('origin_country', 'Egypt'),
                        is_active=True
                    )

                    # Process attributes for this product
                    product_attributes = attributes_df[attributes_df['product_id'] == product_id]
                    attribute_dict = {}
                    for _, attr_row in product_attributes.iterrows():
                        attribute, _ = ProductAttribute.objects.get_or_create(
                            name=attr_row['name'],
                            defaults={'slug': slugify(attr_row['name'])}
                        )
                        values = str(attr_row['values']).split('|')
                        attribute_values = []
                        for value in values:
                            attr_value, _ = ProductAttributeValue.objects.get_or_create(
                                attribute=attribute,
                                value=value.strip()
                            )
                            attribute_values.append(attr_value)
                        attribute_dict[attr_row['name']] = attribute_values

                    # Process variants for this product
                    product_variants = variants_df[variants_df['product_id'] == product_id]
                    for _, var_row in product_variants.iterrows():
                        variant = ProductVariant.objects.create(
                            product=product,
                            sku=var_row['sku'],
                            price=Decimal(str(var_row['price'])),
                            stock=int(var_row['stock']),
                            low_stock_threshold=int(var_row.get('low_stock_threshold', 5)),
                            reorder_point=int(var_row.get('reorder_point', 10)),
                            max_stock_level=int(var_row.get('max_stock_level', 100)),
                            is_active=True
                        )

                        # Assign attribute values to variant
                        attr_assignments = str(var_row['attribute_values']).split(',')
                        for assignment in attr_assignments:
                            attr_name, value = assignment.split(':')
                            if attr_name in attribute_dict:
                                matching_value = next(
                                    (av for av in attribute_dict[attr_name] if av.value == value.strip()),
                                    None
                                )
                                if matching_value:
                                    variant.attribute_values.add(matching_value)

                    # Process images for this product
                    product_images = images_df[images_df['product_id'] == product_id]
                    for i, (_, img_row) in enumerate(product_images.iterrows()):
                        image_content = self.download_image(img_row['url'].strip())
                        if image_content:
                            image_name = f"{slugify(product.name)}_{i+1}.jpg"
                            ProductImage.objects.create(
                                product=product,
                                image=File(image_content, name=image_name),
                                is_primary=bool(img_row.get('is_primary', i == 0)),
                                alt_text=img_row.get('alt_text', f"{product.name} image {i+1}")
                            )

                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully created product {product.name}')
                    )

                except Exception as e:
                    logger.error(f"Error processing product ID {product_id}: {str(e)}")
                    raise