"""
Utilitário para processar o CSV de provisão de férias exportado do ERP.
Lida com as peculiaridades do formato: linhas sem código (continuação do colaborador anterior),
datas em formato numérico Excel (serial), e campos decimais com vírgula.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


# Mapa: código da empresa (3 dígitos) → nome sintético
_EMPRESA_MAP = {
    '001': '001 - RN - MATRIZ',
    '002': '002 - RN - TC1',
    '003': '003 - RN - TP',
    '004': '004 - RN - PA1',
    '005': '005 - RN - VG1',
    '006': '006 - RN - VG2',
    '007': '007 - RN - CB',
    '008': '008 - RN - SR',
    '009': '009 - RN - EM',
    '010': '010 - RN - PA2',
    '011': '011 - RN - TC2',
    '012': '012 - RN - LB',
    '013': '013 - RN - CX',
    '014': '014 - RN - CP',
    '015': '015 - RN - AF1',
    '016': '016 - RN - CL',
    '017': '017 - RN - BE',
    '018': '018 - RN - NP',
    '019': '019 - RN - LV',
    '020': '020 - RN - OL',
    '021': '021 - RN - SA',
    '022': '022 - RN - SG',
    '023': '023 - RN - ET',
    '024': '024 - RN - PD',
    '025': '025 - RN - CG',
    '026': '026 - RN - CZ',
    '027': '027 - RN - MC1',
    '028': '028 - RN - IT',
    '029': '029 - RN - SL',
    '030': '030 - RN - MS',
    '031': '031 - RN - OF',
    '032': '032 - RN - JC',
    '033': '033 - RN - IJ',
    '034': '034 - RN - CEN',
    '035': '035 - RN - AR',
    '036': '036 - RN - AF2',
    '038': '038 - RN - BM',
    '039': '039 - RN - PA3',
    '040': '040 - RN - PC2',
    '041': '041 - RN - ITINERANTE',
    '043': '043 - RN - IN',
    '044': '044 - RN - CM',
    '045': '045 - RN - PS',
    '046': '046 - RN - EV',
    '047': '047 - RN - PC1',
    '048': '048 - RN - AT',
    '050': '050 - RN - BP',
    '051': '051 - RN - AF3',
    '052': '052 - RN - LV3',
    '053': '053 - RN - AF4',
    '054': '054 - RN - MC3',
    '055': '055 - RN - BR',
    '057': '057 - RN - IP2',
    '058': '058 - RN - IP1',
    '059': '059 - RN - MG',
    '060': '060 - RN - MM',
    '061': '061 - RN - JG',
    '097': '097 - RN - CD PA',
    '098': '098 - RN - OUTLET',
    '099': '099 - RN - ECOMMERCE',
    '100': '100 - RN - CD VG',
}



def sintetizar_empresa(empresa_raw):
    """
    Converte o nome longo do ERP para o nome sintético da loja.
    Extrai o código dos 3 primeiros dígitos e busca no mapa.
    Ex: '001 - RN TINTAS E FERR. LTDA - MATRIZ' → '001 - RN - MATRIZ'
    Se não encontrar no mapa, retorna o código + ' - RN - ???' para não perder a info.
    """
    codigo = str(empresa_raw).strip()[:3]
    return _EMPRESA_MAP.get(codigo, f"{codigo} - RN - ???")


# Mapa: prefixo uppercase → nome canônico
# Qualquer cargo que COMECE com a chave vira o valor.
# Ex: "VENDEDOR EXTERNO" começa com "VENDEDOR" → "Vendedor"
_CARGO_PREFIXOS = [
    ('GERENTE DE LOJA',         'Gerente de Loja'),
    ('VENDEDOR',                'Vendedor'),
    ('ASSISTENTE DE LOJA',      'Assistente de Loja'),
    ('ASSISTENTE COMERCIAL',    'Assistente Comercial'),
    ('COORDENADOR COMERCIAL',   'Coordenador Comercial'),
]


def sintetizar_cargo(cargo_raw):
    """
    Normaliza o cargo em dois passos:
    1. Remove sufixo de nível/patente (romano ou G+numeral): 'VENDEDOR II' → 'VENDEDOR'
    2. Agrupa variações por prefixo: 'VENDEDOR EXTERNO' → 'Vendedor'

    Isso garante que no filtro apareça apenas o cargo base, sem fragmentar
    em múltiplas opções para o mesmo tipo de função.
    """
    # Passo 1: remove sufixo numérico/romano
    sem_sufixo = re.sub(
        r'\s+(G\d+\s*[-–]\s*)?(I{1,4}|IV|VI{0,3}|IX)\s*$',
        '',
        cargo_raw.strip()
    )

    # Passo 2: agrupa por prefixo canônico
    upper = sem_sufixo.upper()
    for prefixo, canonico in _CARGO_PREFIXOS:
        if upper == prefixo or upper.startswith(prefixo + ' '):
            return canonico

    # Sem match: título capitalizado (ex: "CAIXA" → "Caixa")
    return sem_sufixo.title()


def excel_serial_para_data(serial):
    """
    Converte número serial do Excel para date.
    Ex: 45536 → 2024-08-26
    O Excel conta dias desde 01/01/1900, com um bug proposital para 1900 (dia 60).
    """
    try:
        serial = int(float(str(serial).replace(',', '.')))
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

    if valor.isdigit() and len(valor) == 5:
        return excel_serial_para_data(valor)

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

    Retorna lista de dicts prontos para salvar na session (sem objetos date/Decimal —
    tudo convertido para str/None para ser serializável em JSON).

    Peculiaridade do ERP: quando um colaborador tem dois períodos aquisitivos,
    a segunda linha vem sem código/nome/cargo/empresa — preenche da linha anterior.
    """
    linhas = []
    ultimo_codigo   = ''
    ultimo_nome     = ''
    ultimo_cargo    = ''
    ultima_empresa  = ''
    ultima_admissao = None

    amostra     = arquivo_texto[:2000]
    delimitador = '\t' if '\t' in amostra else ';' if amostra.count(';') > amostra.count(',') else ','

    reader = csv.reader(io.StringIO(arquivo_texto), delimiter=delimitador)

    cabecalho_encontrado = False
    for linha in reader:
        if not any(linha):
            continue

        if not cabecalho_encontrado:
            linha_upper = [c.upper().strip() for c in linha]
            if any('FUNCION' in c for c in linha_upper):
                cabecalho_encontrado = True
            continue

        while len(linha) < 15:
            linha.append('')

        # Lê os campos brutos
        empresa_raw      = str(linha[0]).strip()
        codigo           = str(linha[1]).strip()
        nome             = str(linha[2]).strip()
        cargo_raw        = str(linha[3]).strip()
        data_admissao    = parse_data(linha[4])
        inicio_aq        = parse_data(linha[5])
        fim_aq           = parse_data(linha[6])
        limite_ideal     = parse_data(linha[7])
        limite_maximo    = parse_data(linha[8])
        faltas           = parse_decimal(linha[9])
        dias_direito     = parse_decimal(linha[10])
        dias_gozo        = parse_decimal(linha[11])
        dias_restantes   = parse_decimal(linha[12])
        dias_programados = parse_decimal(linha[13])

        # Linha sem código = continuação do colaborador anterior
        if not codigo:
            codigo        = ultimo_codigo
            nome          = ultimo_nome
            empresa_raw   = ultima_empresa
            cargo_raw     = ultimo_cargo
            data_admissao = ultima_admissao
        else:
            ultimo_codigo   = codigo
            ultimo_nome     = nome
            ultima_empresa  = empresa_raw
            ultimo_cargo    = cargo_raw
            ultima_admissao = data_admissao

        # Normaliza DEPOIS de resolver qual valor usar (próprio ou herdado)
        empresa = sintetizar_empresa(empresa_raw)
        cargo   = sintetizar_cargo(cargo_raw)

        if not inicio_aq or not fim_aq:
            continue

        if not codigo:
            continue

        # Serializa para JSON (session não aceita date nem Decimal)
        linhas.append({
            'empresa':           empresa,
            'codigo':            codigo,
            'nome':              nome,
            'cargo':             cargo,
            'data_admissao':     data_admissao.isoformat() if data_admissao else None,
            'inicio_aquisitivo': inicio_aq.isoformat(),
            'fim_aquisitivo':    fim_aq.isoformat(),
            'limite_ideal':      limite_ideal.isoformat()  if limite_ideal  else None,
            'limite_maximo':     limite_maximo.isoformat() if limite_maximo else None,
            'faltas':            str(faltas),
            'dias_direito':      str(dias_direito),
            'dias_gozo':         str(dias_gozo),
            'dias_restantes':    str(dias_restantes),
            'dias_programados':  str(dias_programados),
        })

    return linhas


def analisar_importacao(linhas_csv):
    """
    Compara linhas do CSV com o banco atual.
    Retorna conjuntos de códigos + dados extras para o template de confirmação.
    """
    from provisao.models import Colaborador

    codigos_csv   = set(l['codigo'] for l in linhas_csv)
    codigos_banco = set(Colaborador.objects.filter(ativo=True).values_list('codigo', flat=True))

    novos     = codigos_csv - codigos_banco
    removidos = codigos_banco - codigos_csv

    novos_nomes    = {l['codigo']: l['nome'] for l in linhas_csv if l['codigo'] in novos}
    removidos_objs = Colaborador.objects.filter(codigo__in=removidos)

    return {
        'novos':          novos,
        'removidos':      removidos,
        'existentes':     codigos_csv & codigos_banco,
        'novos_nomes':    novos_nomes,
        'removidos_objs': removidos_objs,
    }