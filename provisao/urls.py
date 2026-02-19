from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('importar/', views.importar, name='importar'),
    path('importar/confirmar/', views.confirmar_importacao, name='confirmar_importacao'),
    path('parcelas/salvar/', views.salvar_parcela, name='salvar_parcela'),
    path('parcelas/deletar/', views.deletar_parcela, name='deletar_parcela'),
]