from django.contrib import admin
from .models import Colaborador, PeriodoAquisitivo, ParcelaFerias, ImportacaoProvisao


class ParcelaInline(admin.TabularInline):
    model = ParcelaFerias
    extra = 1
    fields = ['mes_ferias', 'dias', 'observacao']


class PeriodoInline(admin.TabularInline):
    model = PeriodoAquisitivo
    extra = 0
    fields = ['inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito']
    readonly_fields = ['inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito']
    show_change_link = True


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nome', 'cargo', 'empresa', 'data_admissao', 'ativo']
    list_filter = ['ativo', 'empresa']
    search_fields = ['nome', 'codigo', 'cargo']
    inlines = [PeriodoInline]


@admin.register(PeriodoAquisitivo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ['colaborador', 'inicio_aquisitivo', 'fim_aquisitivo', 'limite_maximo', 'dias_direito']
    search_fields = ['colaborador__nome', 'colaborador__codigo']
    inlines = [ParcelaInline]


@admin.register(ParcelaFerias)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ['periodo', 'mes_ferias', 'dias', 'observacao']
    search_fields = ['periodo__colaborador__nome', 'mes_ferias']
    list_filter = ['mes_ferias']


@admin.register(ImportacaoProvisao)
class ImportacaoAdmin(admin.ModelAdmin):
    list_display = ['data_importacao', 'total_linhas', 'novos', 'removidos', 'atualizados']
    readonly_fields = ['data_importacao', 'total_linhas', 'novos', 'removidos', 'atualizados']