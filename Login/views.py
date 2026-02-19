# from django.http import JsonResponse
# from django.shortcuts import redirect
# from allauth.account.views import LoginView

# def home(request):
#     return redirect('account_login')  # redirects / to /accounts/login/


# def login(request):
#     return JsonResponse({"message": "Login endpoint"})


from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required


def home(request):
    return redirect('account_login')


def dashboard(request):
    return render(request, "Login/dashboard.html")
