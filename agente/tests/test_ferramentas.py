"""Testes da tool verificar_datas (sem internet: a BrasilAPI é simulada).

Rodar:  python -m pytest -q      (dentro da pasta agente/)
"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ferramentas  # noqa: E402

FERIADOS_2026 = [
    {"date": "2026-11-02", "name": "Finados", "type": "national"},
    {"date": "2026-11-15", "name": "Proclamação da República", "type": "national"},
]


class RespostaFalsa:
    def __init__(self, dados, status=200):
        self._dados, self.status_code = dados, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: Not Found")

    def json(self):
        return self._dados


@pytest.fixture(autouse=True)
def brasilapi_simulada(monkeypatch):
    ferramentas.cache_feriados.clear()
    chamadas = []

    def get(url, timeout=None):
        chamadas.append(url)
        if url.endswith("/1800"):
            return RespostaFalsa([], 404)
        return RespostaFalsa(FERIADOS_2026)

    monkeypatch.setattr(ferramentas.requests, "get", get)
    return chamadas


def test_periodo_com_feriado_e_fim_de_semana():
    r = ferramentas.executar_tool("verificar_datas", {"data_inicio": "2026-11-01", "data_fim": "2026-11-07"})
    assert r["tem_conflito"] is True
    motivos = {c["data"][:10]: c["motivo"] for c in r["conflitos"]}
    assert motivos["02/11/2026"] == "feriado nacional: Finados"
    assert motivos["01/11/2026"] == "fim de semana" and motivos["07/11/2026"] == "fim de semana"
    assert [d[:10] for d in r["datas_livres"]] == ["03/11/2026", "04/11/2026", "05/11/2026", "06/11/2026"]
    assert r["fonte_feriados"] == "BrasilAPI"


def test_recorrencia_limita_aos_dias_pedidos():
    r = ferramentas.executar_tool(
        "verificar_datas", {"data_inicio": "2026-11-01", "data_fim": "2026-11-30", "dias_semana": ["terça"]})
    assert r["total_datas"] == 4 and r["tem_conflito"] is False


def test_fim_de_semana_pedido_de_proposito_nao_e_conflito():
    r = ferramentas.executar_tool(
        "verificar_datas", {"data_inicio": "2026-11-07", "data_fim": "2026-11-08", "dias_semana": ["sábado", "domingo"]})
    assert r["tem_conflito"] is False


def test_allowlist_recusa_tool_desconhecida(brasilapi_simulada):
    r = ferramentas.executar_tool("apagar_banco", {})
    assert r["erro"] == "tool_nao_permitida"
    assert brasilapi_simulada == []  # nada foi consultado


@pytest.mark.parametrize("argumentos", [
    {"data_inicio": "2026-11-31", "data_fim": "2026-12-01"},                     # data inexistente
    {"data_inicio": "2026-11-01"},                                               # campo obrigatório ausente
    {"data_inicio": "2026-11-01", "data_fim": "2026-11-02", "extra": "x"},       # campo fora do contrato
    {"data_inicio": "2026-11-01", "data_fim": "2026-11-02", "dias_semana": ["feriado"]},  # dia inválido
])
def test_contrato_recusa_argumentos_invalidos(argumentos, brasilapi_simulada):
    r = ferramentas.executar_tool("verificar_datas", argumentos)
    assert r["erro"] == "argumentos_invalidos"
    assert brasilapi_simulada == []  # a API não é chamada com dados inválidos


def test_falha_da_api_vira_erro_estruturado_sem_dados_inventados():
    r = ferramentas.executar_tool("verificar_datas", {"data_inicio": "1800-01-01", "data_fim": "1800-01-01"})
    assert r["erro"] == "falha_execucao" and "404" in r["detalhe"]
    assert "conflitos" not in r


def test_falha_nao_fica_presa_no_cache():
    ferramentas.executar_tool("verificar_datas", {"data_inicio": "1800-01-01", "data_fim": "1800-01-01"})
    assert 1800 not in ferramentas.cache_feriados


def test_periodo_invertido_ou_longo_demais():
    r = ferramentas.executar_tool("verificar_datas", {"data_inicio": "2026-11-10", "data_fim": "2026-11-01"})
    assert r["erro"] == "falha_execucao"
