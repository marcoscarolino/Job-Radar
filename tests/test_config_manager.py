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


def test_desativacao_email_respeitada_mesmo_com_env_vars(tmp_path, monkeypatch):
    test_json = tmp_path / "user_config.json"
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    # Configura explicitamente email desativado
    salvar_config({
        "canais_notificacao": {
            "email": {
                "ativo": False,
                "destinatario": "teste@email.com",
            }
        }
    })

    # Simula variáveis de ambiente do GitHub Actions / ambiente de produção
    monkeypatch.setenv("EMAIL_DESTINATARIO", "env@email.com")
    monkeypatch.setenv("EMAIL_SMTP_USER", "user@email.com")
    monkeypatch.setenv("EMAIL_SMTP_PASS", "senha123")

    cfg = carregar_config()
    # Deve continuar rigorosamente desativado
    assert cfg["canais_notificacao"]["email"]["ativo"] is False


def test_frequencia_email_salvar_e_carregar(tmp_path, monkeypatch):
    test_json = tmp_path / "user_config.json"
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    salvar_config({"frequencia_email": "duas_vezes_ao_dia"})
    cfg = carregar_config()
    assert cfg["frequencia_email"] == "duas_vezes_ao_dia"


def test_expurgar_vagas_incompativeis(tmp_path, monkeypatch):
    test_db = tmp_path / "jobs.db"
    test_json = tmp_path / "user_config.json"
    test_out_json = tmp_path / "jobs.json"
    monkeypatch.setattr("config.DB_PATH", str(test_db))
    monkeypatch.setattr("database.database.DB_PATH", str(test_db))
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    salvar_config({
        "cargos_fortes": ["Product Designer"],
        "cargos_ambiguos": [],
        "cidades": ["São Paulo"],
        "aceitar_remoto": True,
    })

    from database.database import iniciar_db, salvar_vaga, expurgar_vagas_incompativeis
    iniciar_db()

    vaga_valida = Job("Product Designer Pleno", "Empresa UX", "São Paulo", "https://link1.com", "gupy", modalidade="Remoto")
    vaga_invalida = Job("Scrum Master Senior", "Empresa Agile", "São Paulo", "https://link2.com", "gupy", modalidade="Remoto")

    salvar_vaga(vaga_valida)
    salvar_vaga(vaga_invalida)

    expurgar_vagas_incompativeis()

    import sqlite3
    conn = sqlite3.connect(str(test_db))
    rows = conn.execute("SELECT titulo FROM vagas_vistas").fetchall()
    conn.close()

    titulos = [r[0] for r in rows]
    assert "Product Designer Pleno" in titulos
    assert "Scrum Master Senior" not in titulos

