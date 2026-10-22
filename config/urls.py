"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView

from store.sitemaps import CategorySitemap, ProductSitemap

sitemaps = {"products": ProductSitemap, "categories": CategorySitemap}

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path(
        "admin/",
        RedirectView.as_view(pattern_name="admin_dashboard", permanent=False),
    ),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("store.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "store.views.pages.permission_denied"
handler404 = "store.views.pages.page_not_found"
handler500 = "store.views.pages.server_error"
