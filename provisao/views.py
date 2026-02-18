from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
import json

from .models import Colaborador, PeriodoAquisitivo, ImportacaoProvisao
from .utils import processar_csv, analisar_importacao


def index(request):
    """Tela principal: tabela de colaboradores com seus períodos e mês de férias."""
    colaboradores = (
        Colaborador.objects
        .filter(ativo=True)
        .prefetch_related('periodos')
        .order_by('nome')
    )

    # Filtro por nome/cargo (busca simples)
    busca = request.GET.get('busca', '').strip()
    if busca:
        colaboradores = colaboradores.filter(nome__icontains=busca) | \
                        colaboradores.filter(cargo__icontains=busca)

    # Estatísticas rápidas para o topo
    total = colaboradores.count()
    urgentes = sum(
        1 for c in colaboradores
        for p in c.periodos.all()
        if p.status_limite == 'danger'
    )
    atencao = sum(
        1 for c in colaboradores
        for p in c.periodos.all()
        if p.status_limite == 'warning'
    )

    ultima_importacao = ImportacaoProvisao.objects.first()

    return render(request, 'provisao/index.html', {
        'colaboradores': colaboradores,
        'busca': busca,
        'total': total,
        'urgentes': urgentes,
        'atencao': atencao,
        'ultima_importacao': ultima_importacao,
    })


def importar(request):
    """Tela de importação: faz upload do CSV e mostra análise antes de confirmar."""
    if request.method == 'GET':
        return render(request, 'provisao/importar.html')

    # POST: recebeu o CSV
    arquivo = request.FILES.get('arquivo')
    texto_csv = request.POST.get('texto_csv', '').strip()

    # Aceita upload de arquivo OU colar o texto diretamente
    if arquivo:
        conteudo = arquivo.read().decode('utf-8-sig', errors='replace')  # utf-8-sig remove BOM
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

    # Salva os dados na sessão para confirmar depois
    # (evita reprocessar o arquivo no passo de confirmação)
    request.session['linhas_csv'] = [
        {**l, 'inicio_aquisitivo': str(l['inicio_aquisitivo']),
               'fim_aquisitivo': str(l['fim_aquisitivo']),
               'limite_ideal': str(l['limite_ideal']) if l['limite_ideal'] else None,
               'limite_maximo': str(l['limite_maximo']) if l['limite_maximo'] else None,
               'data_admissao': str(l['data_admissao']) if l['data_admissao'] else None,
               'faltas': str(l['faltas']),
               'dias_direito': str(l['dias_direito']),
               'dias_gozo': str(l['dias_gozo']),
               'dias_restantes': str(l['dias_restantes']),
               'dias_programados': str(l['dias_programados']),
        }
        for l in linhas
    ]

    # Nomes dos colaboradores novos e removidos para exibição
    novos_nomes = [l['nome'] for l in linhas if l['codigo'] in analise['novos']]
    novos_nomes = list(dict.fromkeys(novos_nomes))  # deduplica mantendo ordem

    removidos_objs = Colaborador.objects.filter(
        codigo__in=analise['removidos'], ativo=True
    ).values('codigo', 'nome')

    return render(request, 'provisao/confirmar_importacao.html', {
        'total_linhas': len(linhas),
        'novos': list(analise['novos']),
        'novos_nomes': novos_nomes,
        'removidos': list(analise['removidos']),
        'removidos_objs': list(removidos_objs),
        'existentes_count': len(analise['existentes']),
    })


@require_POST
def confirmar_importacao(request):
    """
    Executa a importação de fato:
    - Atualiza períodos dos colaboradores existentes
    - Adiciona novos colaboradores (se solicitado)
    - Inativa removidos (se solicitado)
    """
    linhas = request.session.get('linhas_csv')
    if not linhas:
        messages.error(request, 'Sessão expirada. Faça o upload novamente.')
        return redirect('importar')

    adicionar_novos  = request.POST.get('adicionar_novos') == '1'
    remover_antigos  = request.POST.get('remover_antigos') == '1'

    from datetime import date

    def str_para_date(s):
        if not s or s == 'None':
            return None
        return date.fromisoformat(s)

    from decimal import Decimal

    novos_count = removidos_count = atualizados_count = 0

    with transaction.atomic():
        for l in linhas:
            inicio_aq = str_para_date(l['inicio_aquisitivo'])
            fim_aq    = str_para_date(l['fim_aquisitivo'])

            # Garante que o colaborador existe
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
                    # Criou mas não deveria — desfaz parcialmente marcando inativo
                    colaborador.ativo = False
                    colaborador.save()
                    continue
                novos_count += 1
            else:
                # Atualiza dados cadastrais (cargo pode mudar)
                colaborador.nome   = l['nome']
                colaborador.cargo  = l['cargo']
                colaborador.ativo  = True
                colaborador.save()

            # Atualiza ou cria o período aquisitivo
            # Preserva o mes_ferias e observacao que já foram preenchidos manualmente!
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
                # Atualiza apenas os dados numéricos — preserva mes_ferias e observacao!
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

        # Remove colaboradores que saíram da provisão
        if remover_antigos:
            codigos_csv = set(l['codigo'] for l in linhas)
            removidos = Colaborador.objects.filter(ativo=True).exclude(codigo__in=codigos_csv)
            removidos_count = removidos.count()
            removidos.update(ativo=False)

    # Registra no log
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


@require_POST
def salvar_mes_ferias(request):
    """
    Salva o mês de férias de um período via AJAX.
    Espera JSON: { "periodo_id": 1, "mes_ferias": "2025-07" }
    """
    try:
        data = json.loads(request.body)
        periodo_id = data.get('periodo_id')
        mes_ferias = data.get('mes_ferias', '').strip()

        periodo = get_object_or_404(PeriodoAquisitivo, pk=periodo_id)

        # Valida formato YYYY-MM
        if mes_ferias and len(mes_ferias) == 7 and mes_ferias[4] == '-':
            periodo.mes_ferias = mes_ferias
        elif mes_ferias == '':
            periodo.mes_ferias = None
        else:
            return JsonResponse({'ok': False, 'erro': 'Formato inválido'}, status=400)

        periodo.save()
        return JsonResponse({
            'ok': True,
            'display': periodo.mes_ferias_display,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)


@require_POST
def salvar_observacao(request):
    """Salva observação de um período via AJAX."""
    try:
        data = json.loads(request.body)
        periodo = get_object_or_404(PeriodoAquisitivo, pk=data['periodo_id'])
        periodo.observacao = data.get('observacao', '')
        periodo.save()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)}, status=500)
