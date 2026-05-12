from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/analytics/', views.dashboard_analytics, name='dashboard_analytics'),
    path('crisis-support/', views.crisis_support, name='crisis_support'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('terms/', views.terms_of_service, name='terms_of_service'),
    path('help/', views.help_center, name='help_center'),
]