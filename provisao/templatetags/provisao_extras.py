import json
from django import template

register = template.Library()


@register.filter
def jsonparcelas(parcelas_qs):
    """
    Serializa um queryset de ParcelaFerias para JSON inline no HTML.
    Uso: {{ periodo.parcelas.all|jsonparcelas }}
    Retorna string JSON escapada para uso seguro em data-attributes.
    """
    dados = [p.to_dict() for p in parcelas_qs]
    # mark_safe não é necessário pois usamos no atributo data-, mas precisamos
    # de aspas simples no HTML para o JSON funcionar com aspas duplas internas.
    return json.dumps(dados, ensure_ascii=False)