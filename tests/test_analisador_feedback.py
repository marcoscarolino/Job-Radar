from __future__ import annotations

import pytest
from analisador_feedback import analisar_comentario_feedback
from job import Job, RegrasFiltro


def test_analisar_feedback_bloquear_empresa(tmp_path, monkeypatch):
    test_json = tmp_path / "user_config.json"
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    vaga = {"id": "1", "titulo": "Gerente de Projetos", "empresa": "Empresa Ruim Corp"}
    res = analisar_comentario_feedback(vaga, "Não quero vagas dessa empresa, é péssima")

    assert res["alterado"] is True
    assert "Empresa Ruim Corp" in res["config"]["empresas_bloqueadas"]

    # Valida no Job._avaliar
    regras = RegrasFiltro(
        keywords_forte=["Gerente de Projetos"],
        keywords_ambiguo=[],
        qualificadores_dados=[],
        ferramentas_titulo=[],
        qualificadores_cargo=[],
        cidades=["São Paulo"],
        empresas_bloqueadas=res["config"]["empresas_bloqueadas"],
    )

    job_bloqueado = Job("Gerente de Projetos", "Empresa Ruim Corp", "São Paulo", "http://l.com", "gupy", modalidade="Remoto")
    job_ok = Job("Gerente de Projetos", "Empresa Boa Ltda", "São Paulo", "http://l2.com", "gupy", modalidade="Remoto")

    assert job_bloqueado.combina_com(regras) is False
    assert job_ok.combina_com(regras) is True


def test_analisar_feedback_bloquear_titulo(tmp_path, monkeypatch):
    test_json = tmp_path / "user_config.json"
    monkeypatch.setattr("config_manager.CONFIG_PATH", test_json)

    vaga = {"id": "2", "titulo": "Scrum Master Senior", "empresa": "Tech Solutions"}
    res = analisar_comentario_feedback(vaga, "Não quero vagas do cargo Scrum Master")

    assert res["alterado"] is True
    assert any("scrum master" in t.lower() for t in res["config"]["titulos_bloqueados"])

    regras = RegrasFiltro(
        keywords_forte=["Scrum Master Senior"],
        keywords_ambiguo=[],
        qualificadores_dados=[],
        ferramentas_titulo=[],
        qualificadores_cargo=[],
        cidades=["São Paulo"],
        titulos_bloqueados=res["config"]["titulos_bloqueados"],
    )

    job_bloqueado = Job("Scrum Master Senior", "Tech Solutions", "São Paulo", "http://l.com", "gupy", modalidade="Remoto")
    assert job_bloqueado.combina_com(regras) is False
