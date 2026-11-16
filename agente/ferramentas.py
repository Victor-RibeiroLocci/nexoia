"""Tool verificar_datas no padrão do Cap. 5 da Fase 3: função Python + contrato Pydantic + declaração + executor controlado.

Os feriados vêm só da BrasilAPI: se a consulta falhar, a exceção sobe e o executor devolve o erro ao LLM, sem dados inventados."""
import logging
from datetime import date, timedelta
from typing import Literal, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
cache_feriados = {}  # guarda só respostas de sucesso da BrasilAPI: uma falha não fica presa no cache


# --- CAPACIDADE: funções Python comuns, que não dependem do LLM ---
def feriados_do_ano(ano):
    """GET na BrasilAPI (sem autenticação) e devolve {data: nome}. Se a consulta falhar (rede, status de erro via
    raise_for_status ou JSON inválido), a exceção sobe: o executar_tool() a captura e devolve o erro ao LLM."""
    if ano not in cache_feriados:
        resposta = requests.get(f"https://brasilapi.com.br/api/feriados/v1/{ano}", timeout=6)
        resposta.raise_for_status()
        cache_feriados[ano] = {date.fromisoformat(f["date"]): f["name"] for f in resposta.json()}
    return cache_feriados[ano]


def verificar_datas(data_inicio, data_fim, dias_semana=None):
    """Aponta feriados nacionais e fins de semana no período, opcionalmente só nos dias da semana pedidos."""
    if not 0 <= (data_fim - data_inicio).days <= 400:
        raise ValueError("data_fim deve ser igual ou posterior a data_inicio, num período de até 400 dias")
    datas = [d for d in (data_inicio + timedelta(i) for i in range((data_fim - data_inicio).days + 1)) if not dias_semana or DIAS[d.weekday()] in dias_semana]
    feriados = {d: nome for ano in range(data_inicio.year, data_fim.year + 1) for d, nome in feriados_do_ano(ano).items()}
    fim_de_semana_conflita = not {"sábado", "domingo"} & set(dias_semana or [])  # sábado/domingo pedido de propósito não é conflito
    motivos = {d: f"feriado nacional: {feriados[d]}" if d in feriados else "fim de semana" if fim_de_semana_conflita and d.weekday() >= 5 else None for d in datas}
    rotulo = {d: f"{d:%d/%m/%Y} ({DIAS[d.weekday()]})" for d in datas}
    conflitos = [{"data": rotulo[d], "motivo": m} for d, m in motivos.items() if m]
    return {"periodo": f"{data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}", "recorrencia": ", ".join(dias_semana or ["todos os dias do período"]),
            "total_datas": len(datas), "tem_conflito": bool(conflitos), "conflitos": conflitos,
            "datas_livres": [rotulo[d] for d, m in motivos.items() if not m], "fonte_feriados": "BrasilAPI",
            "observacao": "Apenas feriados nacionais; feriados estaduais e municipais não são verificados."}


# --- CONTRATO: formato aceito antes da execução ---
class ArgumentosDatas(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    data_inicio: date = Field(strict=False)  # aceita "AAAA-MM-DD" e recusa datas inexistentes (ex.: 2026-11-31)
    data_fim: date = Field(strict=False)
    dias_semana: Optional[list[Literal[DIAS]]] = None


# --- DECLARAÇÃO: descreve a tool para o LLM (não executa nada) ---
tools = [{"type": "function", "name": "verificar_datas",
          "description": "Verifica se um período tem feriados nacionais do Brasil ou fins de semana. Use somente quando a temporalidade "
                         "informada pelo usuário puder ser convertida em datas concretas.",
          "parameters": {"type": "object", "required": ["data_inicio", "data_fim"], "properties": {
              "data_inicio": {"type": "string", "description": "Primeira data do período, no formato AAAA-MM-DD"},
              "data_fim": {"type": "string", "description": "Última data do período, no formato AAAA-MM-DD (igual a data_inicio para um único dia)"},
              "dias_semana": {"type": "array", "items": {"type": "string", "enum": list(DIAS)},
                              "description": "Opcional, para recorrências: ex. [\"terça\"] para toda terça-feira do período"}}}}]
tools_permitidas = {"verificar_datas": (verificar_datas, ArgumentosDatas)}  # allowlist: nome -> (função, contrato)


# --- EXECUTOR CONTROLADO: o nome vindo do LLM nunca vira código direto ---
def executar_tool(nome, argumentos):
    if nome not in tools_permitidas:
        logging.warning("Tool recusada: %s", nome)
        return {"erro": "tool_nao_permitida", "detalhe": f"A tool '{nome}' não está disponível."}
    funcao, contrato = tools_permitidas[nome]
    try:
        dados = contrato.model_validate(argumentos)
    except ValidationError as erro:
        logging.warning("Argumentos inválidos para %s: %s", nome, argumentos)
        return {"erro": "argumentos_invalidos", "detalhe": [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in erro.errors()]}
    try:
        logging.info("Executando tool: %s %s", nome, argumentos)
        return funcao(**dados.model_dump())
    except Exception as erro:
        logging.error("Falha durante a execução da tool %s: %s", nome, erro)
        return {"erro": "falha_execucao", "detalhe": str(erro)}


if __name__ == "__main__":  # teste rápido, sem LLM: python ferramentas.py
    print(executar_tool("verificar_datas", {"data_inicio": "2026-11-01", "data_fim": "2026-11-07"}))
    print(executar_tool("verificar_datas", {"data_inicio": "2026-11-01", "data_fim": "2026-11-30", "dias_semana": ["terça"]}))
    # falha na consulta externa: a BrasilAPI responde 404 para anos fora de 1900–2199 -> {"erro": "falha_execucao", ...}
    print(executar_tool("verificar_datas", {"data_inicio": "1800-01-01", "data_fim": "1800-01-01"}))
