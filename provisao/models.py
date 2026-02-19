from django.db import models
from django.utils import timezone


class Colaborador(models.Model):
    """Representa um funcionário da empresa."""
    codigo = models.CharField(max_length=20, unique=True, verbose_name='Código')
    nome = models.CharField(max_length=150, verbose_name='Nome')
    cargo = models.CharField(max_length=150, verbose_name='Cargo')
    empresa = models.CharField(max_length=200, verbose_name='Empresa', default='001 - RN TINTAS')
    data_admissao = models.DateField(null=True, blank=True, verbose_name='Data de Admissão')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')

    class Meta:
        ordering = ['nome']
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class PeriodoAquisitivo(models.Model):
    """
    Cada colaborador pode ter múltiplos períodos aquisitivos vindos do ERP.
    As férias agendadas ficam em ParcelaFerias (relação 1→N),
    pois um colaborador pode fracionar as férias em vários meses.
    """
    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.CASCADE,
        related_name='periodos',
        verbose_name='Colaborador'
    )
    inicio_aquisitivo = models.DateField(verbose_name='Início Aquisitivo')
    fim_aquisitivo = models.DateField(verbose_name='Fim Aquisitivo')
    limite_ideal = models.DateField(null=True, blank=True, verbose_name='Limite Ideal')
    limite_maximo = models.DateField(null=True, blank=True, verbose_name='Limite Máximo')

    faltas = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name='Faltas')
    dias_direito = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name='Dias Direito')
    dias_gozo = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name='Dias Gozo')
    dias_restantes = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name='Dias Restantes')
    dias_programados = models.DecimalField(max_digits=5, decimal_places=1, default=0, verbose_name='Dias Programados')

    class Meta:
        ordering = ['colaborador__nome', 'inicio_aquisitivo']
        verbose_name = 'Período Aquisitivo'
        verbose_name_plural = 'Períodos Aquisitivos'
        unique_together = ['colaborador', 'inicio_aquisitivo']

    def __str__(self):
        return f"{self.colaborador.nome} | {self.inicio_aquisitivo} → {self.fim_aquisitivo}"

    @property
    def status_limite(self):
        """
        Retorna o status visual baseado nos prazos do período.
        'danger'   → passou do limite máximo
        'warning'  → limite ideal dentro de 60 dias
        'ok'       → dentro do prazo
        'sem_dias' → sem dias de direito
        """
        if not self.dias_direito or self.dias_direito == 0:
            return 'sem_dias'

        hoje = timezone.now().date()

        if self.limite_maximo and hoje > self.limite_maximo:
            return 'danger'

        if self.limite_ideal:
            if (self.limite_ideal - hoje).days <= 60:
                return 'warning'

        return 'ok'

    @property
    def status_badge(self):
        """Retorna (classe_bootstrap, texto) para o badge de status."""
        badges = {
            'danger':   ('bg-danger',              '⚠ URGENTE'),
            'warning':  ('bg-warning text-dark',   '⏰ Atenção'),
            'ok':       ('bg-success',             '✓ OK'),
            'sem_dias': ('bg-secondary',           '— Sem dias'),
        }
        return badges.get(self.status_limite, ('bg-secondary', '-'))


class ParcelaFerias(models.Model):
    """
    Uma parcela de férias dentro de um período aquisitivo.
    Um período pode ter múltiplas parcelas — férias fracionadas em meses diferentes.
    Ex: 10 dias em Jul/2025 + 20 dias em Set/2025 dentro do mesmo período aquisitivo.
    """
    periodo = models.ForeignKey(
        PeriodoAquisitivo,
        on_delete=models.CASCADE,
        related_name='parcelas',
        verbose_name='Período'
    )
    mes_ferias = models.CharField(max_length=7, verbose_name='Mês das Férias',
                                  help_text='Formato YYYY-MM (ex: 2025-07)')
    dias = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                               verbose_name='Dias')
    observacao = models.TextField(blank=True, verbose_name='Observação')

    class Meta:
        ordering = ['mes_ferias']
        verbose_name = 'Parcela de Férias'
        verbose_name_plural = 'Parcelas de Férias'

    def __str__(self):
        return f"{self.periodo} → {self.mes_ferias_display}"

    @property
    def mes_ferias_display(self):
        """Retorna 'Jul/2025' a partir de '2025-07'."""
        try:
            ano, mes = self.mes_ferias.split('-')
            nomes = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
            return f"{nomes[int(mes)-1]}/{ano}"
        except Exception:
            return self.mes_ferias

    def to_dict(self):
        """Serializa para JSON (usado nas respostas AJAX do modal)."""
        return {
            'id': self.id,
            'mes_ferias': self.mes_ferias,
            'mes_ferias_display': self.mes_ferias_display,
            'dias': str(self.dias) if self.dias else '',
            'observacao': self.observacao,
        }


class ImportacaoProvisao(models.Model):
    """Registra cada importação de provisão — serve como log de histórico."""
    data_importacao = models.DateTimeField(auto_now_add=True)
    total_linhas = models.IntegerField(default=0, verbose_name='Total de linhas no CSV')
    novos = models.IntegerField(default=0, verbose_name='Colaboradores novos')
    removidos = models.IntegerField(default=0, verbose_name='Colaboradores removidos')
    atualizados = models.IntegerField(default=0, verbose_name='Períodos atualizados')
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ['-data_importacao']
        verbose_name = 'Importação de Provisão'

    def __str__(self):
        return f"Importação {self.data_importacao.strftime('%d/%m/%Y %H:%M')}"