from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
import json
from decimal import Decimal, InvalidOperation

from .models import Colaborador, PeriodoAquisitivo, ParcelaFerias, ImportacaoProvisao
from .utils import processar_csv, analisar_importacao

@login_required
def index(request):
    """Tela principal: tabela de colaboradores com seus períodos e parcelas de férias."""
    colaboradores = (
        Colaborador.objects
        .filter(ativo=True)
        .prefetch_related('periodos__parcelas')
        .order_by('nome')
    )

    busca = request.GET.get('busca', '').strip()
    if busca:
        colaboradores = colaboradores.filter(nome__icontains=busca) | \
                        colaboradores.filter(cargo__icontains=busca)

    total = colaboradores.count()
    urgentes = sum(1 for c in colaboradores for p in c.periodos.all() if p.status_limite == 'danger')
    atencao  = sum(1 for c in colaboradores for p in c.periodos.all() if p.status_limite == 'warning')

    ultima_importacao = ImportacaoProvisao.objects.first()

    return render(request, 'provisao/index.html', {
        'colaboradores':    colaboradores,
        'busca':            busca,
        'total':            total,
        'urgentes':         urgentes,
        'atencao':          atencao,
        'ultima_importacao': ultima_importacao,
    })


@login_required
def importar(request):
    """Tela de importação: faz upload do CSV e mostra análise antes de confirmar."""
    if request.method == 'GET':
        return render(request, 'provisao/importar.html')

    arquivo  = request.FILES.get('arquivo')
    texto_csv = request.POST.get('texto_csv', '').strip()

    if arquivo:
        conteudo = arquivo.read().decode('utf-8-sig', errors='replace')
    elif texto_csv:
        conteudo = texto_csv
    else:
        messages.error(request, 'Selecione um arquivo ou cole o conteúdo do CSV.')
        return redirect('importar')

    try:
        linhas = processar_csv(conteudo)
    except Exception as e:
        messages.error(request, f'Erro ao processar o CSV: {e}')
        return redirect('importar')

    if not linhas:
        messages.error(request, 'Nenhuma linha válida encontrada no CSV. Verifique o formato.')
        return redirect('importar')

    analise = analisar_importacao(linhas)
    request.session['linhas_csv'] = linhas

    return render(request, 'provisao/confirmar_importacao.html', {
        'linhas':          linhas,
        'total_linhas':    len(linhas),
        'novos':           analise['novos'],
        'removidos':       analise['removidos'],
        'existentes_count': len(analise['existentes']),
        'novos_nomes':     analise['novos_nomes'],
        'removidos_objs':  analise['removidos_objs'],
    })


@login_required
@require_POST
def confirmar_importacao(request):
    """Processa a importação confirmada pelo usuário."""
    linhas = request.session.get('linhas_csv')
    if not linhas:
        messages.error(request, 'Sessão expirada. Faça o upload novamente.')
        return redirect('importar')

    adicionar_novos = request.POST.get('adicionar_novos') == '1'
    remover_antigos = request.POST.get('remover_antigos') == '1'

    from datetime import date

    def str_para_date(s):
        if not s or s == 'None':
            return None
        return date.fromisoformat(s)

    novos_count = removidos_count = atualizados_count = 0

    with transaction.atomic():
        for l in linhas:
            inicio_aq = str_para_date(l['inicio_aquisitivo'])
            fim_aq    = str_para_date(l['fim_aquisitivo'])

            colaborador, criado = Colaborador.objects.get_or_create(
                codigo=l['codigo'],
                defaults={
                    'nome':          l['nome'],
                    'cargo':         l['cargo'],
                    'empresa':       l['empresa'],
                    'data_admissao': str_para_date(l['data_admissao']),
                    'ativo':         True,
                }
            )

            if criado:
                if not adicionar_novos:
                    colaborador.ativo = False
                    colaborador.save()
                    continue
                novos_count += 1
            else:
                colaborador.nome    = l['nome']
                colaborador.cargo   = l['cargo']
                colaborador.empresa = l['empresa']  # ← adicionar essa linha
                colaborador.ativo   = True
                colaborador.save()
                atualizados_count += 1

            # Preserva parcelas de férias: get_or_create garante que registros
            # existentes (com parcelas vinculadas) não sejam recriados
            periodo, periodo_criado = PeriodoAquisitivo.objects.get_or_create(
                colaborador=colaborador,
                inicio_aquisitivo=inicio_aq,
                defaults={
                    'fim_aquisitivo':   fim_aq,
                    'limite_ideal':     str_para_date(l['limite_ideal']),
                    'limite_maximo':    str_para_date(l['limite_maximo']),
                    'faltas':           Decimal(l['faltas']),
                    'dias_direito':     Decimal(l['dias_direito']),
                    'dias_gozo':        Decimal(l['dias_gozo']),
                    'dias_restantes':   Decimal(l['dias_restantes']),
                    'dias_programados': Decimal(l['dias_programados']),
                }
            )

            if not periodo_criado:
                # Atualiza apenas dados do ERP — parcelas de férias são preservadas
                periodo.fim_aquisitivo   = fim_aq
                periodo.limite_ideal     = str_para_date(l['limite_ideal'])
                periodo.limite_maximo    = str_para_date(l['limite_maximo'])
                periodo.faltas           = Decimal(l['faltas'])
                periodo.dias_direito     = Decimal(l['dias_direito'])
                periodo.dias_gozo        = Decimal(l['dias_gozo'])
                periodo.dias_restantes   = Decimal(l['dias_restantes'])
                periodo.dias_programados = Decimal(l['dias_programados'])
                periodo.save()
                atualizados_count += 1

        if remover_antigos:
            codigos_csv = set(l['codigo'] for l in linhas)
            removidos = Colaborador.objects.filter(ativo=True).exclude(codigo__in=codigos_csv)
            removidos_count = removidos.count()
            removidos.update(ativo=False)

    ImportacaoProvisao.objects.create(
        total_linhas=len(linhas),
        novos=novos_count,
        removidos=removidos_count,
        atualizados=atualizados_count,
    )

    del request.session['linhas_csv']

    messages.success(
        request,
        f'Importação concluída! '
        f'{novos_count} adicionados, {removidos_count} inativados, {atualizados_count} atualizados.'
    )
    return redirect('index')


@login_required
@require_POST
def salvar_parcela(request):
    """
    Cria uma nova parcela de férias para um período.
    Espera JSON: { periodo_id, mes_ferias, dias (opcional), observacao }
    Retorna a lista atualizada de parcelas do período.
    """
    try:
        data = json.loads(request.body)
        periodo = get_object_or_404(PeriodoAquisitivo, pk=data['periodo_id'])

        mes = data.get('mes_ferias', '').strip()
        if not mes or len(mes) != 7 or mes[4] != '-':
            return JsonResponse({'ok': False, 'erro': 'Mês inválido. Use o formato YYYY-MM.'}, status=400)

        dias_raw = data.get('dias', '').strip() if data.get('dias') else None
        dias = None
        if dias_raw:
            try:
                dias = Decimal(dias_raw)
            except InvalidOperation:
                return JsonResponse({'ok': False, 'erro': 'Dias inválido.'}, status=400)

        # Valida o limite de dias apenas quando o campo dias é informado
        if dias is not None and periodo.dias_direito:
            ja_usados = sum(p.dias for p in periodo.parcelas.all() if p.dias is not None)
            if ja_usados + dias > periodo.dias_direito:
                disponiveis = periodo.dias_direito - ja_usados
                return JsonResponse({
                    'ok': False,
                    'erro': f'Limite excedido. Disponível: {int(disponiveis)}d de {int(periodo.dias_direito)}d ({int(ja_usados)}d já usados).'
                }, status=400)

        ParcelaFerias.objects.create(
            periodo=periodo,
            mes_ferias=mes,
            dias=dias,
            observacao=data.get('observacao', '').strip(),
        )

        parcelas = list(periodo.parcelas.all().order_by('mes_ferias'))
        dias_usados = sum(p.dias for p in parcelas if p.dias is not None)
        return JsonResponse({
            'ok':            True,
            'parcelas':      [p.to_dict() for p in parcelas],
            'dias_usados':   float(dias_usados),
            'dias_direito':  float(periodo.dias_direito or 0),
            'status_badge':  list(periodo.status_badge),   # ['bg-danger', '⚠ URGENTE']
            'status_limite': periodo.status_limite,        # 'danger' | 'warning' | 'ok'
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@login_required
@require_POST
def deletar_parcela(request):
    """
    Remove uma parcela de férias.
    Espera JSON: { parcela_id }
    Retorna a lista atualizada de parcelas do período.
    """
    try:
        data = json.loads(request.body)
        parcela = get_object_or_404(ParcelaFerias, pk=data['parcela_id'])
        periodo_id = parcela.periodo_id
        parcela.delete()

        periodo = get_object_or_404(PeriodoAquisitivo, pk=periodo_id)
        parcelas = list(ParcelaFerias.objects.filter(periodo_id=periodo_id).order_by('mes_ferias'))
        dias_usados = sum(p.dias for p in parcelas if p.dias is not None)
        return JsonResponse({
            'ok':            True,
            'parcelas':      [p.to_dict() for p in parcelas],
            'dias_usados':   float(dias_usados),
            'dias_direito':  float(periodo.dias_direito or 0),
            'status_badge':  list(periodo.status_badge),   # ['bg-danger', '⚠ URGENTE']
            'status_limite': periodo.status_limite,        # 'danger' | 'warning' | 'ok'
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)