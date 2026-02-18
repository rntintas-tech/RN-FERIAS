from django.contrib import admin
from .models import Colaborador, PeriodoAquisitivo, ImportacaoProvisao


class PeriodoInline(admin.TabularInline):
    model = PeriodoAquisitivo
    extra = 0
    fields = ['inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito', 'mes_ferias']
    readonly_fields = ['inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito']


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nome', 'cargo', 'empresa', 'ativo']
    list_filter = ['ativo', 'empresa']
    search_fields = ['nome', 'codigo', 'cargo']
    inlines = [PeriodoInline]


@admin.register(PeriodoAquisitivo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ['colaborador', 'inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito', 'mes_ferias']
    list_filter = ['mes_ferias']
    search_fields = ['colaborador__nome', 'colaborador__codigo']


@admin.register(ImportacaoProvisao)
class ImportacaoAdmin(admin.ModelAdmin):
    list_display = ['data_importacao', 'total_linhas', 'novos', 'removidos', 'atualizados']
    readonly_fields = ['data_importacao', 'total_linhas', 'novos', 'removidos', 'atualizados']
