from django.contrib.sitemaps import Sitemap
from .models import Category, Product

class ProductSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8
    def items(self): return Product.objects.all()
    def lastmod(self, obj): return obj.created_at

class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7
    def items(self): return Category.objects.all()