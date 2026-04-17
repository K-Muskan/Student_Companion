from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/analytics/', views.dashboard_analytics, name='dashboard_analytics'),
]