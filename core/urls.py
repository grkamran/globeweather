from django.contrib import admin
from django.urls import path
from app import views

urlpatterns = [
    path("admin/", admin.site.urls),

    path("", views.home, name="home"),

    # API endpoints
    path("api/search/", views.api_search, name="api_search"),
    path("api/suggest/", views.api_suggest, name="api_suggest"),
]
