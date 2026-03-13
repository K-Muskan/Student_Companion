from django.urls import path

from .consumers import EmotionStreamConsumer

websocket_urlpatterns = [
    path("ws/emotion/<int:assessment_id>/<str:scale>/", EmotionStreamConsumer.as_asgi()),
]
