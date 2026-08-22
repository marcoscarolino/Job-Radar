from __future__ import annotations

import os
import sqlite3
import subprocess
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from config_manager import carregar_config, salvar_config

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


DB_PATH = Path(__file__).parent / "data" / "jobs.db"
RUNNING_PROCESS = None
RUNNING_LOCK = threading.Lock()
LAST_RUN_LOGS = []


def obter_vagas_recientes(limit: int = 100) -> list[dict]:
    """Retorna as vagas mais recentes gravadas no SQLite data/jobs.db que combinam com as regras ativas."""
    if not DB_PATH.exists():
        return []

    from perfis import obter_regras_perfil
    from job import Job

    regras = obter_regras_perfil("brasil")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, titulo, empresa, local, link AS url, site AS fonte,
                   encontrada_em AS criado_em, modalidade, relevancia AS score,
                   publicado_em
            FROM vagas_vistas
            ORDER BY encontrada_em DESC, ROWID DESC
            """,
        )
        colunas = [column[0] for column in cursor.description]
        vagas = []
        for row in cursor.fetchall():
            row_dict = dict(zip(colunas, row))

            j = Job(
                titulo=row_dict.get("titulo") or "",
                empresa=row_dict.get("empresa") or "",
                local=row_dict.get("local") or "",
                link=row_dict.get("url") or "",
                site=row_dict.get("fonte") or "",
                publicado_em=row_dict.get("publicado_em") or "",
                modalidade=row_dict.get("modalidade") or "",
            )

            if j.combina_com(regras):
                if not row_dict.get("score"):
                    row_dict["score"] = j.pontuar_relevancia(regras)
                if not row_dict.get("publicado_em"):
                    row_dict["publicado_em"] = "Recente"
                vagas.append(row_dict)
                if len(vagas) >= limit:
                    break
        conn.close()
        return vagas
    except Exception as e:
        return []


def sincronizar_configuracao_github():
    """Faz commit e push de data/user_config.json para o GitHub para atualizar o GitHub Actions."""
    def _push():
        try:
            cwd = Path(__file__).parent
            subprocess.run(["git", "add", "data/user_config.json"], cwd=cwd, check=True)
            subprocess.run(["git", "commit", "-m", "chore: atualizar configuracoes do usuario via interface"], cwd=cwd, check=False)
            subprocess.run(["git", "push", "origin", "main"], cwd=cwd, check=False)
        except Exception as e:
            pass

    threading.Thread(target=_push, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    config = carregar_config()
    return jsonify({"success": True, "config": config})


@app.route("/api/config", methods=["POST"])
def update_config():
    novos_dados = request.get_json()
    if not novos_dados:
        return jsonify({"success": False, "error": "Payload JSON ausente"}), 400

    config_salva = salvar_config(novos_dados)
    return jsonify({"success": True, "config": config_salva, "message": "Configurações salvas!"})


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    vagas = obter_vagas_recientes(limit=100)
    return jsonify({"success": True, "vagas": vagas, "total": len(vagas)})


@app.route("/api/run", methods=["POST"])
def run_scraper():
    global RUNNING_PROCESS, LAST_RUN_LOGS

    dados = request.get_json(silent=True) or {}
    force = dados.get("force", False)

    with RUNNING_LOCK:
        if RUNNING_PROCESS is not None and RUNNING_PROCESS.poll() is None:
            if force:
                try:
                    RUNNING_PROCESS.terminate()
                except Exception:
                    pass
            else:
                return jsonify({"success": False, "message": "Já existe uma busca em andamento!", "is_running": True}), 400

        # Dispara a busca em thread separada
        def executor():
            global RUNNING_PROCESS, LAST_RUN_LOGS
            LAST_RUN_LOGS = ["Iniciando varredura com novos parâmetros..."]
            python_bin = Path(__file__).parent / "venv" / "bin" / "python"
            if not python_bin.exists():
                python_bin = "python3"

            try:
                proc = subprocess.Popen(
                    [str(python_bin), "main.py", "--perfil", "brasil", "--once"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                RUNNING_PROCESS = proc

                for line in proc.stdout:
                    LAST_RUN_LOGS.append(line.strip())
                    if len(LAST_RUN_LOGS) > 200:
                        LAST_RUN_LOGS.pop(0)

                proc.wait()
                LAST_RUN_LOGS.append("Varredura local concluída com sucesso.")
            except Exception as e:
                LAST_RUN_LOGS.append(f"Erro na execução: {e}")


        t = threading.Thread(target=executor, daemon=True)
        t.start()

    return jsonify({"success": True, "message": "Varredura iniciada em segundo plano!"})


@app.route("/api/cancel", methods=["POST"])
def cancel_scraper():
    global RUNNING_PROCESS, LAST_RUN_LOGS
    with RUNNING_LOCK:
        if RUNNING_PROCESS is not None and RUNNING_PROCESS.poll() is None:
            try:
                RUNNING_PROCESS.terminate()
                RUNNING_PROCESS = None
                LAST_RUN_LOGS.append("Busca cancelada pelo usuário.")
                return jsonify({"success": True, "message": "Busca cancelada com sucesso!"})
            except Exception as e:
                return jsonify({"success": False, "message": f"Erro ao cancelar: {e}"}), 500
        return jsonify({"success": True, "message": "Nenhuma busca em andamento."})



@app.route("/api/clear-jobs", methods=["POST"])
def clear_jobs():
    from database.database import limpar_banco_vagas
    try:
        limpar_banco_vagas()
        return jsonify({"success": True, "message": "Lista de vagas limpa com sucesso!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erro ao limpar banco de vagas: {e}"}), 500


@app.route("/api/status", methods=["GET"])
def get_status():
    is_running = RUNNING_PROCESS is not None and RUNNING_PROCESS.poll() is None
    return jsonify({
        "success": True,
        "is_running": is_running,
        "logs": LAST_RUN_LOGS[-30:] if LAST_RUN_LOGS else [],
    })


@app.route("/api/test-notification", methods=["POST"])
def test_notification():
    from notifier.dispatcher import enviar_notificacao_multicanal
    dados = request.json or {}
    canal = dados.get("canal", "email")

    test_msg = "[JobRadar Teste] As notificações estão funcionando perfeitamente!"
    test_html = """
    <h2>JobRadar - Teste de Notificação</h2>
    <p>Seu canal de alerta foi configurado e validado com sucesso!</p>
    <p>Você receberá novas vagas compatíveis por este canal.</p>
    """

    res = enviar_notificacao_multicanal(
        texto_simples=test_msg,
        assunto="JobRadar - Teste de Notificação",
        corpo_html=test_html,
        forcar_canal=canal,
    )

    resultado_canal = res.get(canal)
    if isinstance(resultado_canal, tuple):
        ok, detalhe = resultado_canal
    else:
        ok, detalhe = bool(resultado_canal), "Canal de notificação não respondeu."

    if ok:
        return jsonify({"success": True, "message": detalhe})
    else:
        return jsonify({"success": False, "message": detalhe}), 400


if __name__ == "__main__":
    print("\n🚀 JobRadar Web UI rodando em http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
