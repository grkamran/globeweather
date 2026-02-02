from django.contrib import admin
from django.urls import path
from app.views import home, api_search, api_suggest

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("api/search/", api_search, name="api_search"),
    path("api/suggest/", api_suggest, name="api_suggest"),
]
