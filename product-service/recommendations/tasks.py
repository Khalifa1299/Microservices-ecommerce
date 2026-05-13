from celery import shared_task
from .services.similarity_computer import SimilarityComputer
import logging

logger = logging.getLogger(__name__)


@shared_task
def compute_product_similarities():
    """Compute all product similarities"""
    try:
        logger.info("Starting product similarity computation")
        computer = SimilarityComputer()
        
        computer.compute_content_based_similarity()
        logger.info("Content-based similarities computed")
        
        computer.compute_collaborative_similarity()
        logger.info("Collaborative similarities computed")
        
        computer.compute_frequently_bought_together()
        logger.info("Frequently bought together computed")
        
        logger.info("Product similarity computation completed successfully")
        return "Success"
    except Exception as e:
        logger.error(f"Error computing similarities: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def clear_expired_recommendation_cache():
    """Clear expired recommendation cache"""
    from django.utils import timezone
    from .models import UserRecommendationCache
    
    try:
        expired_count = UserRecommendationCache.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()[0]
        
        logger.info(f"Cleared {expired_count} expired recommendation caches")
        return f"Cleared {expired_count} caches"
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return f"Error: {str(e)}"