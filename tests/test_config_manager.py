from __future__ import annotations

import json
from pathlib import Path
import pytest

from config_manager import DEFAULT_CONFIG, carregar_config, salvar_config
from job import Job, RegrasFiltro


def test_carregar_config_padrao():
    config = carregar_config()
    assert "cargos_fortes" in config
    assert "ferramentas" in config
    assert "cidades" in config
    assert "modalidades_aceitas" in config
    assert "preferencia_modalidade" in config
    assert "scrapers_ativos" in config
    assert isinstance(config["scrapers_ativos"], dict)


def test_salvar_e_carregar_config(tmp_path, monkeypatch):
    test_json = tmp_path / "user_config.json"
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    novas_config = {
        "cargos_fortes": ["Desenvolvedor Python", "Engenheiro de Dados"],
        "ferramentas": ["python", "aws", "pmp", "coursera"],
        "cidades": ["São Paulo", "Recife"],
        "modalidades_aceitas": {"remoto": True, "hibrido": False, "presencial": False},
        "preferencia_modalidade": "remoto",
        "scrapers_ativos": {
            "gupy": True,
            "linkedin": False,
        },
    }

    salvar_config(novas_config)
    assert test_json.exists()

    config_carregada = carregar_config()
    assert "Desenvolvedor Python" in config_carregada["cargos_fortes"]
    assert "aws" in config_carregada["ferramentas"]
    assert config_carregada["modalidades_aceitas"]["hibrido"] is False
    assert config_carregada["preferencia_modalidade"] == "remoto"


def test_pontuacao_preferencia_modalidade():
    regras = RegrasFiltro(
        keywords_forte=["Analista de Dados"],
        keywords_ambiguo=[],
        qualificadores_dados=[],
        ferramentas_titulo=[],
        qualificadores_cargo=[],
        cidades=["Remoto"],
        preferencia_modalidade="remoto",
        modalidades_aceitas={"remoto": True, "hibrido": True, "presencial": True},
    )

    job_remoto = Job("Analista de Dados", "Empresa A", "Brasil", "http://link.com", "gupy", modalidade="Remoto")
    job_hibrido = Job("Analista de Dados", "Empresa B", "São Paulo", "http://link2.com", "gupy", modalidade="Híbrido")

    # Vaga remota deve ganhar +3 pontos de bônus por bater a preferência do usuário
    assert job_remoto.pontuar_relevancia(regras) > job_hibrido.pontuar_relevancia(regras)
