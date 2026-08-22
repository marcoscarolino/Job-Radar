from datetime import datetime, timezone
import pytest

from firebase_service import deve_enviar_alerta
from perfis import criar_regras_usuario
from job import Job


def test_deve_enviar_alerta_a_cada_3_horas():
    # 'a_cada_3_horas' sempre deve retornar True para qualquer data/hora
    agora = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)
    ultimo_envio = "2026-08-22T11:00:00+00:00"
    assert deve_enviar_alerta("a_cada_3_horas", ultimo_envio, agora) is True
    assert deve_enviar_alerta("sempre", None, agora) is True


def test_deve_enviar_alerta_diario():
    agora_hoje = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)
    
    # Se nunca enviou antes, deve enviar
    assert deve_enviar_alerta("diario", None, agora_hoje) is True

    # Se já enviou hoje, NÃO deve enviar
    ultimo_envio_hoje = "2026-08-22T08:00:00+00:00"
    assert deve_enviar_alerta("diario", ultimo_envio_hoje, agora_hoje) is False

    # Se o último envio foi ontem, DEVE enviar
    ultimo_envio_ontem = "2026-08-21T18:00:00+00:00"
    assert deve_enviar_alerta("diario", ultimo_envio_ontem, agora_hoje) is True


def test_deve_enviar_alerta_semanal():
    # 2026-08-24 é uma segunda-feira (weekday == 0)
    segunda_feira = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    assert segunda_feira.weekday() == 0

    # 2026-08-25 é uma terça-feira (weekday == 1)
    terca_feira = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    assert terca_feira.weekday() == 1

    # Na terça-feira NÃO deve enviar semanal
    assert deve_enviar_alerta("semanal", None, terca_feira) is False

    # Na segunda-feira com último envio na semana passada, DEVE enviar
    ultimo_envio_passado = "2026-08-17T09:00:00+00:00"
    assert deve_enviar_alerta("semanal", ultimo_envio_passado, segunda_feira) is True

    # Na segunda-feira se JÁ enviou hoje, NÃO deve enviar novamente
    ultimo_envio_hoje = "2026-08-24T06:00:00+00:00"
    assert deve_enviar_alerta("semanal", ultimo_envio_hoje, segunda_feira) is False


def test_criar_regras_usuario_isolamento_de_perfis():
    user_designer = {
        "cargos_fortes": ["Product Designer", "UX Designer"],
        "cargos_ambiguos": ["UI Designer"],
        "cidades": ["São Paulo"],
        "aceitar_remoto": True,
        "modalidades_aceitas": {"remoto": True, "hibrido": False, "presencial": False},
        "senioridades_alvo": ["Sênior"],
    }

    user_pm = {
        "cargos_fortes": ["Gerente de Projetos", "Project Manager"],
        "cargos_ambiguos": ["Scrum Master"],
        "cidades": ["Recife"],
        "aceitar_remoto": True,
        "modalidades_aceitas": {"remoto": True, "hibrido": True, "presencial": True},
        "senioridades_alvo": ["Pleno", "Sênior"],
    }

    regras_designer = criar_regras_usuario(user_designer)
    regras_pm = criar_regras_usuario(user_pm)

    vaga_design = Job(
        titulo="Product Designer Sênior",
        empresa="TechCorp",
        local="Remoto",
        link="https://exemplo.com/vaga-design",
        site="Gupy",
        modalidade="remoto",
    )

    vaga_pm = Job(
        titulo="Gerente de Projetos de TI",
        empresa="Empresa X",
        local="Recife",
        link="https://exemplo.com/vaga-pm",
        site="LinkedIn",
        modalidade="hibrido",
    )

    # Vaga de Design combina com Designer, mas NÃO com PM
    assert vaga_design.combina_com(regras_designer) is True
    assert vaga_design.combina_com(regras_pm) is False

    # Vaga de PM combina com PM, mas NÃO com Designer
    assert vaga_pm.combina_com(regras_pm) is True
    assert vaga_pm.combina_com(regras_designer) is False
