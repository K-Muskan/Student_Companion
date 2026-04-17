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
    path('debug/emotions/<int:assessment_id>/', views.debug_emotions, name='debug_emotions'),

    # Completion page with MSE analysis
    path('complete/', views.complete, name='complete'),
    
    # Download routes
    path('download-report-text/', views.download_report_text, name='download_report_text'),
    path('download-report-json/', views.download_report_json, name='download_report_json'),
    path('report/<int:assessment_id>/', views.view_saved_report, name='view_mse_report'),    
    path(
        'analysis/<int:assessment_id>/run/',
        views.trigger_analysis_pipeline,
        name='trigger_analysis_pipeline',
    ),
     path(
        'analysis/<int:assessment_id>/',
        views.view_analysis_result,
        name='view_analysis_result',
     ),
    path('therapist/<int:assessment_id>/', views.therapist_session, name='therapist_session'),
    path('therapist/status/<int:assessment_id>/', views.therapist_status, name='therapist_status'),
]

