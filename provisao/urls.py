from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('importar/', views.importar, name='importar'),
    path('importar/confirmar/', views.confirmar_importacao, name='confirmar_importacao'),
    path('api/salvar-mes-ferias/', views.salvar_mes_ferias, name='salvar_mes_ferias'),
    path('api/salvar-observacao/', views.salvar_observacao, name='salvar_observacao'),
]
