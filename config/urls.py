from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.contrib.sitemaps.views import sitemap
from store.sitemaps import ProductSitemap, CategorySitemap


sitemaps={"products": ProductSitemap, "categories": CategorySitemap}

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('admin/', RedirectView.as_view(pattern_name='admin_dashboard', permanent=False)),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("store.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
