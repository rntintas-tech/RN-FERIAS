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
    
    # PasswordChangeView: valida senha atual + define nova + confirma
    # success_url redireciona para index após troca bem-sucedida
    path('trocar-senha/',
         auth_views.PasswordChangeView.as_view(
             template_name='provisao/trocar_senha.html',
             success_url='/',
         ),
         name='trocar_senha'),

    path('', include('provisao.urls')),
]