from django.contrib import admin
from django.urls import path, include
from Login.views import home # import your custom login view
from django.conf import settings  # ← ADD THIS IMPORT
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),                 # / → login
    path('accounts/', include('allauth.urls')), # allauth
    path('', include('Login.urls')),   # IMPORTANT
    path('assessment/', include('Questionaire_project.urls')),
]

# THIS IS CRITICAL - Add this to serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


