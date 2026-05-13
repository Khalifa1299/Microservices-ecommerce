from django.db.models import Count, Q
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from products.models import Product
from recommendations.models import ProductSimilarity, FrequentlyBoughtTogether, UserProductInteraction

# OrderItem removed — order-service owns order data, product-service cannot import it directly.
# compute_frequently_bought_together() is stubbed until Phase 4 (Kafka):
#   order-service will publish order.placed events → product-service consumes them
#   and builds its own local FrequentlyBoughtTogether records without cross-DB queries.


class SimilarityComputer:
    """Compute and store product similarities"""
    
    @staticmethod
    def compute_content_based_similarity():
        """Compute similarity based on product content (name, description, category)"""
        products = Product.objects.filter(is_active=True)
        
        if products.count() < 2:
            return
        
        # Create text representations
        product_texts = []
        product_ids = []
        
        for product in products:
            text = f"{product.name} {product.description} {product.category.name if product.category else ''}"
            # Add tags if you have them
            # text += " " + " ".join([tag.name for tag in product.tags.all()])
            product_texts.append(text)
            product_ids.append(product.id)
        
        # Compute TF-IDF
        vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
        tfidf_matrix = vectorizer.fit_transform(product_texts)
        
        # Compute cosine similarity
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Store similarities (only top 10 for each product)
        ProductSimilarity.objects.filter(similarity_type='content').delete()
        
        for i, product_id in enumerate(product_ids):
            # Get top 10 similar products (excluding itself)
            similar_indices = similarity_matrix[i].argsort()[::-1][1:11]
            
            similarities_to_create = []
            for j in similar_indices:
                if similarity_matrix[i][j] > 0.1:  # Threshold
                    similarities_to_create.append(
                        ProductSimilarity(
                            product_id=product_id,
                            similar_product_id=product_ids[j],
                            similarity_score=float(similarity_matrix[i][j]),
                            similarity_type='content'
                        )
                    )
            
            ProductSimilarity.objects.bulk_create(similarities_to_create, ignore_conflicts=True)
    
    @staticmethod
    def compute_collaborative_similarity():
        """Compute similarity based on user behavior (users who viewed X also viewed Y)"""
        # Get products with enough interactions
        products = Product.objects.filter(
            interactions__isnull=False
        ).annotate(
            interaction_count=Count('interactions')
        ).filter(interaction_count__gte=5)
        
        product_ids = list(products.values_list('id', flat=True))
        
        if len(product_ids) < 2:
            return
        
        # Create user-product interaction matrix
        interactions = UserProductInteraction.objects.filter(
            product_id__in=product_ids
        ).values('user_id', 'product_id', 'weight')
        
        # Build matrix
        user_product_matrix = {}
        users = set()
        
        for interaction in interactions:
            user_id = interaction['user_id']
            product_id = interaction['product_id']
            weight = interaction['weight']
            
            users.add(user_id)
            
            if user_id not in user_product_matrix:
                user_product_matrix[user_id] = {}
            
            user_product_matrix[user_id][product_id] = weight
        
        # Convert to numpy matrix
        user_list = list(users)
        matrix = np.zeros((len(user_list), len(product_ids)))
        
        for i, user_id in enumerate(user_list):
            for j, product_id in enumerate(product_ids):
                matrix[i][j] = user_product_matrix.get(user_id, {}).get(product_id, 0)
        
        # Compute item-item similarity
        if matrix.shape[0] > 0:
            item_similarity = cosine_similarity(matrix.T)
            
            # Store similarities
            ProductSimilarity.objects.filter(similarity_type='collaborative').delete()
            
            similarities_to_create = []
            for i, product_id in enumerate(product_ids):
                similar_indices = item_similarity[i].argsort()[::-1][1:11]
                
                for j in similar_indices:
                    if item_similarity[i][j] > 0.1:
                        similarities_to_create.append(
                            ProductSimilarity(
                                product_id=product_id,
                                similar_product_id=product_ids[j],
                                similarity_score=float(item_similarity[i][j]),
                                similarity_type='collaborative'
                            )
                        )
            
            ProductSimilarity.objects.bulk_create(similarities_to_create, ignore_conflicts=True)
    
    @staticmethod
    def compute_frequently_bought_together():
        # Stubbed — requires order data from order-service.
        # Will be implemented in Phase 4 via Kafka consumer:
        #   topic: orders.placed → consume order items → build FrequentlyBoughtTogether locally.
        pass