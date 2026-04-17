from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone
from Questionaire_project import analytics
from Login.models import UserActivityLog, DownloadLog


def home(request):
    return redirect('account_login')


@login_required
def dashboard(request):
    return render(request, "Login/dashboard.html")


@login_required
def dashboard_analytics(request):
    user_id = request.user.id
    return JsonResponse({
        'score_trend': analytics.get_score_trend(user_id),
        'facial_emotions': analytics.get_facial_emotion_history(user_id),
        'feeling_scores': analytics.get_feeling_scores(user_id),
        'recommendations': analytics.get_latest_recommendations(user_id),
        'summary': analytics.get_dashboard_summary(user_id),
        'sessions': analytics.get_session_list(user_id),
        'stats': analytics.get_stats(user_id),
        'wellness': analytics.get_wellness_factors(user_id),
    })


@login_required
def log_download(request, assessment_id, download_type):
    """Called when user downloads PDF/JSON/TXT — logs it for the counter."""
    if download_type not in ['pdf', 'json', 'txt']:
        return JsonResponse({'error': 'invalid type'}, status=400)
    DownloadLog.objects.create(
        user=request.user,
        assessment_id=assessment_id,
        download_type=download_type
    )
    return JsonResponse({'status': 'logged'})


@receiver(user_logged_in)
def log_user_activity(sender, request, user, **kwargs):
    today = timezone.now().date()
    UserActivityLog.objects.get_or_create(
        user=user,
        activity_date=today
    )