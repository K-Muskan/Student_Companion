from django.urls import path
from . import views

app_name = 'questionnaire'

urlpatterns = [
    # Landing/Intro page (index.html with intro video)
    path('', views.index, name='index'),
    
    # Question pages
    path('question/<int:qid>/', views.question_page, name='question_page'),
    
    # Save answer API endpoint
    path('save-answer/', views.save_answer, name='save_answer'),
    path('save-text-answer/', views.save_text_answer, name='save_text_answer'),

    # Completion page with MSE analysis
    path('complete/', views.complete, name='complete'),
    
    # Download routes
    path('download-report-text/', views.download_report_text, name='download_report_text'),
    path('download-report-json/', views.download_report_json, name='download_report_json'),
    
]
