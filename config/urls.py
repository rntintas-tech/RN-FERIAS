"""
config/urls.py — Roteamento principal do projeto ferias_rn.

Inclui as URLs nativas de autenticação do Django (login/logout),
apontando para nosso template customizado em provisao/login.html.
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Login: usa LoginView do Django com nosso template personalizado
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='provisao/login.html'),
        name='login',
    ),

    # Logout: redireciona para a tela de login após sair
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='login'),
        name='logout',
    ),

    path('', include('provisao.urls')),
]