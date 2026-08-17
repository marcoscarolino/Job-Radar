from __future__ import annotations

import os
import sqlite3
import subprocess
import threading
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from config_manager import carregar_config, salvar_config

app = Flask(__name__)

DB_PATH = Path(__file__).parent / "data" / "jobs.db"
RUNNING_PROCESS = None
RUNNING_LOCK = threading.Lock()
LAST_RUN_LOGS = []


def obter_vagas_recientes(limit: int = 100) -> list[dict]:
    """Retorna as vagas mais recentes gravadas no SQLite data/jobs.db com score de relevância."""
    if not DB_PATH.exists():
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, titulo, empresa, local, link AS url, site AS fonte,
                   encontrada_em AS criado_em, modalidade, relevancia AS score
            FROM vagas_vistas
            ORDER BY encontrada_em DESC, ROWID DESC
            LIMIT ?
            """,
            (limit,),
        )
        colunas = [column[0] for column in cursor.description]
        vagas = []
        for row in cursor.fetchall():
            row_dict = dict(zip(colunas, row))
            if row_dict.get("score") is None:
                row_dict["score"] = 5  # Score padrão se não gravado
            vagas.append(row_dict)
        conn.close()
        return vagas
    except Exception as e:
        return []


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
    return jsonify({"success": True, "config": config_salva, "message": "Configurações salvas com sucesso!"})


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    vagas = obter_vagas_recientes(limit=100)
    return jsonify({"success": True, "vagas": vagas, "total": len(vagas)})


@app.route("/api/run", methods=["POST"])
def run_scraper():
    global RUNNING_PROCESS, LAST_RUN_LOGS

    with RUNNING_LOCK:
        if RUNNING_PROCESS is not None and RUNNING_PROCESS.poll() is None:
            return jsonify({"success": False, "message": "Já existe uma busca em andamento!"}), 400

        # Dispara a busca em thread separada
        def executor():
            global RUNNING_PROCESS, LAST_RUN_LOGS
            LAST_RUN_LOGS = ["Iniciando varredura com novos parâmetros..."]
            python_bin = Path(__file__).parent / "venv" / "bin" / "python"
            if not python_bin.exists():
                python_bin = "python3"

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

        t = threading.Thread(target=executor, daemon=True)
        t.start()

    return jsonify({"success": True, "message": "Varredura iniciada em segundo plano!"})


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
    canal = dados.get("canal", "telegram")

    test_msg = "🔔 <b>[JobRadar Teste]</b> As notificações multicanal estão funcionando perfeitamente!"
    test_html = """
    <h2>📡 JobRadar - Teste de Notificação</h2>
    <p>Seu canal de alerta foi configurado e validado com sucesso!</p>
    <p>Você receberá novas vagas compatíveis diretamente por este canal.</p>
    """

    res = enviar_notificacao_multicanal(
        texto_simples=test_msg,
        assunto="🔔 JobRadar - Teste de Notificação",
        corpo_html=test_html,
    )

    if res.get(canal):
        return jsonify({"success": True, "message": f"Alerta enviado com sucesso para {canal}!"})
    else:
        return jsonify({"success": False, "message": f"Falha ao enviar alerta para {canal}. Verifique os dados digitados e tente novamente."}), 400


if __name__ == "__main__":
    print("\n🚀 JobRadar Web UI rodando em http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
