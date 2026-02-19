from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    #new urls of this layers app only can be added here
    path('dashboard/', views.dashboard, name='dashboard'),
]

