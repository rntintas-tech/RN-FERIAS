"""
Utilitário para processar o CSV de provisão de férias exportado do ERP.
Lida com as peculiaridades do formato: linhas sem código (continuação do colaborador anterior),
datas em formato numérico Excel (serial), e campos decimais com vírgula.
"""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


def excel_serial_para_data(serial):
    """
    Converte número serial do Excel para date.
    Ex: 45536 → 2024-08-26
    O Excel conta dias desde 01/01/1900, com um bug proposital para 1900 (dia 60).
    """
    try:
        serial = int(float(str(serial).replace(',', '.')))
        # O Excel tem um bug: considera 1900 como bissexto. Por isso subtrai 2 ao invés de 1.
        return date(1899, 12, 30) + timedelta(days=serial)
    except (ValueError, TypeError):
        return None


def parse_data(valor):
    """
    Tenta converter string para date.
    Aceita: DD/MM/YYYY, YYYY-MM-DD, ou número serial do Excel.
    """
    if not valor or str(valor).strip() in ('', '0'):
        return None

    valor = str(valor).strip()

    # Tenta número serial do Excel
    if valor.isdigit() and len(valor) == 5:
        return excel_serial_para_data(valor)

    # Tenta formatos de data comuns
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(valor, fmt).date()
        except ValueError:
            continue

    return None


def parse_decimal(valor):
    """Converte string com vírgula ou ponto para Decimal."""
    if not valor or str(valor).strip() == '':
        return Decimal('0')
    try:
        return Decimal(str(valor).strip().replace(',', '.'))
    except InvalidOperation:
        return Decimal('0')


def processar_csv(arquivo_texto):
    """
    Processa o conteúdo do CSV exportado do ERP.

    Retorna uma lista de dicts, um por linha válida:
    {
        'empresa': str,
        'codigo': str,
        'nome': str,
        'cargo': str,
        'data_admissao': date|None,
        'inicio_aquisitivo': date|None,
        'fim_aquisitivo': date|None,
        'limite_ideal': date|None,
        'limite_maximo': date|None,
        'faltas': Decimal,
        'dias_direito': Decimal,
        'dias_gozo': Decimal,
        'dias_restantes': Decimal,
        'dias_programados': Decimal,
    }

    Peculiaridade do ERP: quando um colaborador tem dois períodos aquisitivos,
    a segunda linha não repete código/nome/cargo/admissão — deixa em branco.
    Esse parse preenche esses campos da linha anterior.
    """
    linhas = []
    ultimo_codigo = ''
    ultimo_nome = ''
    ultimo_cargo = ''
    ultima_empresa = ''
    ultima_admissao = None

    # Detecta delimitador automaticamente
    amostra = arquivo_texto[:2000]
    delimitador = '\t' if '\t' in amostra else ';' if amostra.count(';') > amostra.count(',') else ','

    reader = csv.reader(io.StringIO(arquivo_texto), delimiter=delimitador)

    cabecalho_encontrado = False
    for linha in reader:
        if not any(linha):
            continue  # Linha vazia

        # Pula até encontrar o cabeçalho (contém "FUNCIONÁRIO" ou "FUNCIONARIO")
        if not cabecalho_encontrado:
            linha_upper = [c.upper().strip() for c in linha]
            if any('FUNCION' in c for c in linha_upper):
                cabecalho_encontrado = True
            continue

        # Normaliza quantidade de colunas
        while len(linha) < 15:
            linha.append('')

        empresa         = str(linha[0]).strip()
        codigo          = str(linha[1]).strip()
        nome            = str(linha[2]).strip()
        cargo           = str(linha[3]).strip()
        data_admissao   = parse_data(linha[4])
        inicio_aq       = parse_data(linha[5])
        fim_aq          = parse_data(linha[6])
        limite_ideal    = parse_data(linha[7])
        limite_maximo   = parse_data(linha[8])
        faltas          = parse_decimal(linha[9])
        dias_direito    = parse_decimal(linha[10])
        dias_gozo       = parse_decimal(linha[11])
        dias_restantes  = parse_decimal(linha[12])
        dias_programados= parse_decimal(linha[13])

        # Se a linha não tem código, é continuação do colaborador anterior
        if not codigo:
            codigo        = ultimo_codigo
            nome          = ultimo_nome
            cargo         = ultimo_cargo
            empresa       = ultima_empresa
            data_admissao = ultima_admissao
        else:
            ultimo_codigo  = codigo
            ultimo_nome    = nome
            ultimo_cargo   = cargo
            ultima_empresa = empresa
            ultima_admissao= data_admissao

        # Ignora linhas sem período aquisitivo válido
        if not inicio_aq or not fim_aq:
            continue

        # Ignora linhas sem código de colaborador (erro no CSV)
        if not codigo:
            continue

        linhas.append({
            'empresa':          empresa,
            'codigo':           codigo,
            'nome':             nome,
            'cargo':            cargo,
            'data_admissao':    data_admissao,
            'inicio_aquisitivo':inicio_aq,
            'fim_aquisitivo':   fim_aq,
            'limite_ideal':     limite_ideal,
            'limite_maximo':    limite_maximo,
            'faltas':           faltas,
            'dias_direito':     dias_direito,
            'dias_gozo':        dias_gozo,
            'dias_restantes':   dias_restantes,
            'dias_programados': dias_programados,
        })

    return linhas


def analisar_importacao(linhas_csv):
    """
    Compara linhas do CSV com o banco atual.
    Retorna um relatório com:
    - novos: colaboradores no CSV mas não no banco
    - removidos: colaboradores no banco mas não no CSV
    - existentes: códigos que existem em ambos
    """
    from provisao.models import Colaborador

    codigos_csv = set(l['codigo'] for l in linhas_csv)
    codigos_banco = set(Colaborador.objects.filter(ativo=True).values_list('codigo', flat=True))

    return {
        'novos':      codigos_csv - codigos_banco,
        'removidos':  codigos_banco - codigos_csv,
        'existentes': codigos_csv & codigos_banco,
    }
