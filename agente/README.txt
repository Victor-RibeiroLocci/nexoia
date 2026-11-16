NexoIA - Fase 3
===============

O NexoIA ajuda a cadastrar uma intenção de comunicação com 8 campos: nome,
produto/tema, público, objetivo, contexto, tipo, temporalidade e critério de
sucesso.

Na Fase 3, ele ganhou uma nova capacidade: quando o usuário informa a
temporalidade, o agente consulta a BrasilAPI e avisa se as datas caem em
feriado nacional ou fim de semana.

O app usa o Google Gemini como LLM e abre no navegador.


O QUE VOCÊ PRECISA
------------------

- Python 3.10 ou superior
- Uma chave gratuita do Gemini: https://aistudio.google.com/apikey


COMO ABRIR (Windows, cerca de 5 minutos)
----------------------------------------

Abra o PowerShell dentro da pasta chat-gemini (a que tem o app.py) e rode:

1. Instalar

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt

2. Informar a chave do Gemini

    $env:GOOGLE_API_KEY = "sua-chave"

   No Prompt de Comando (cmd), use:  set GOOGLE_API_KEY=sua-chave

3. Abrir o agente

    .venv\Scripts\python.exe -m streamlit run app.py

   O navegador abre sozinho em http://localhost:8501.
   Para fechar, use Ctrl + C no terminal.


COMO TESTAR
-----------

O app já abre pronto para os testes: prompt system_prompt_NexoIA_v5,
ferramenta verificar_datas ligada e temperatura 0.0.

Antes de cada teste, clique em "+ Nova" na barra lateral. Depois de enviar a
mensagem, clique em "Ver chamada e resposta da API" para ver a consulta feita.

Teste 1 - Execução bem-sucedida. Copie e envie:

    Quero cadastrar a intenção 'Nova anuidade Cartão Gold'. O tema é a nova tarifa de anuidade do cartão Gold. O público são os clientes atuais do cartão Gold. O objetivo é informar a nova tarifa e reduzir dúvidas no atendimento. O contexto é a mudança na tabela de tarifas do cartão. O tipo é uma campanha de e-mail. A comunicação deve acontecer na primeira semana de novembro de 2026. O critério de sucesso é uma taxa de abertura de pelo menos 40%.

   Esperado: aviso de Finados (02/11) e dos fins de semana (01/11 e 07/11),
   datas livres de 03 a 06/11 e a pergunta "manter ou ajustar?".

Teste 2 - Informação obrigatória ausente. Copie e envie:

    Quero cadastrar a intenção 'Nova anuidade Cartão Gold'. O tema é a nova tarifa de anuidade do cartão Gold. O público são os clientes atuais do cartão Gold. O objetivo é informar a nova tarifa e reduzir dúvidas no atendimento. O contexto é a mudança na tabela de tarifas do cartão. O tipo é uma campanha de e-mail. O critério de sucesso é uma taxa de abertura de pelo menos 40%.

   Esperado: a API não é consultada e o NexoIA pergunta quando a comunicação
   deve acontecer.

Teste 3 - Falha na consulta externa. Copie e envie:

    Quero cadastrar a intenção 'Nova anuidade Cartão Gold'. O tema é a nova tarifa de anuidade do cartão Gold. O público são os clientes atuais do cartão Gold. O objetivo é informar a nova tarifa e reduzir dúvidas no atendimento. O contexto é a mudança na tabela de tarifas do cartão. O tipo é uma campanha de e-mail. A comunicação deve acontecer no dia 01/01/1800. O critério de sucesso é uma taxa de abertura de pelo menos 40%.

   Esperado: a BrasilAPI responde 404 (só aceita anos de 1900 a 2199) e o
   NexoIA informa que não foi possível verificar as datas, sem inventar
   feriados.


ARQUIVOS
--------

app.py               Tela de chat e ciclo do agente com o Gemini
ferramentas.py       Tool verificar_datas: valida os dados e consulta a BrasilAPI
SystemPrompt/        Instruções do agente (a versão usada é a v5)
requirements.txt     Bibliotecas necessárias
estilo.css           Visual do app (opcional)
mascote.svg          Mascote do app (opcional)


SE ALGO DER ERRADO
------------------

"No module named streamlit"
    Rode o passo 3 exatamente como está, começando com .venv\Scripts\python.exe

"Defina a variável de ambiente GOOGLE_API_KEY"
    Repita o passo 2 no mesmo terminal e abra o agente de novo.

Erro 503 ou 429 do Gemini
    O serviço está sobrecarregado. Espere alguns segundos e reenvie a mensagem.

A chave do Gemini nunca fica no código: ela é lida da variável de ambiente
GOOGLE_API_KEY.
