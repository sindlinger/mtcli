Exemplos prontos (copiar/colar)

Ajuda + detecção

python mtcli.py            # agora mostra ajuda e exemplos
python mtcli.py detect



Abrir MT5 com template (indicador já anexado)

python mtcli.py open --symbol EURUSD --period M15 --template MeuTemplate.tpl

Instalar e rodar o EA escutador (para “dar comandos” sem reiniciar)

python mtcli.py listener install
python mtcli.py listener run --symbol EURUSD --period M15
python mtcli.py listener send apply-template  --symbol EURUSD --period M15 --template MeuTemplate.tpl
python mtcli.py listener send attach-indicator --symbol EURUSD --period H1 --indicator Examples\Heiken_Ashi --subwindow 0

(O EA abre/aplica via ChartOpen/ChartApplyTemplate/ChartIndicatorAdd.)
(O arquivo de comando fica em MQL5\Files\cmd.txt dentro da Data Folder.) 
metatrader5.com

Strategy Tester — visual e otimização

Backtest visual de um EA (+ relatório e fechamento automático)



python mtcli.py tester run \
  --ea Examples\MACD\MACD Sample \
  --symbol EURUSD --period M1 --model everytick \
  --visual --date-from 2024.01.01 --date-to 2024.06.01 \
  --report \reports\macd_{ts}.htm --replace-report --shutdown
Chaves suportadas pelo MT5: Visual, Model, FromDate/ToDate, Report, ReplaceReport, ShutdownTerminal. 
metatrader5.com
Nota: a velocidade do modo visual é controlada na UI durante o teste; não há chave de INI para isso. 
metatrader5.com


Otimização genética com critério e forward


python mtcli.py tester run \
  --ea Examples\MACD\MACD Sample \
  --symbol EURUSD --period M15 --model everytick \
  --opt fast --criterion complex \
  --forward custom --forward-date 2024.04.01 \
  --use-local --use-cloud \
  --report \reports\macd_opt_{ts}.xml --replace-report --shutdown
(Optimization=2 genética, OptimizationCriterion=7 complexo, uso de agentes locais e MQL5 Cloud; relatório de otimização sai como .xml). 
metatrader5.com


Definir “atraso de execução” simulado


python mtcli.py tester run ... --exec-delay-ms 120

(ExecutionMode=120 = atraso fixo 120 ms; -1 ativa atraso aleatório). 
metatrader5.com


Rodar em paralelo (instâncias separadas; portas diferentes

python mtcli.py tester run ... --port 3001 --report \reports\run1_{ts}.htm --shutdown
python mtcli.py tester run ... --port 3002 --report \reports\run2_{ts}.htm --shutdown

(Use pastas de instalação diferentes se for abrir múltiplas cópias; duas cópias não rodam da mesma pasta.) 
metatrader5.com


Otimização guiada por JSON → [TesterInputs] (sem editar .set)

Crie inputs.json:

{
  "Lots": 0.10,
  "Risk": {"value": 1.0, "start": 0.5, "step": 0.5, "stop": 5},
  "Reverse": false,
  "OpenTime": "03:00"
}

Rode:


python mtcli.py tester run \
  --ea Examples\MACD\MACD Sample \
  --symbol EURUSD --period M15 --opt fast \
  --inputs-json inputs.json \
  --report \reports\guide_{ts}.xml --replace-report --shutdown



O CLI gera um .ini com [Tester] + [TesterInputs], no formato amplamente usado na comunidade (param=valor||inicio||passo||fim||Y|N). Exemplos reais públicos: 
GitHub
+1

Se preferir .set: salve seu .set em MQL5\Profiles\Tester e passe --ea-parameters MeuEA.set. 
metatrader5.com

Batch — N execuções em série (grade cartesiana)

plan.json:


{
  "base": {
    "ea": "Examples\\MACD\\MACD Sample",
    "symbol": "EURUSD",
    "period": "M15",
    "model": "everytick",
    "opt": "off",
    "date_from": "2024.01.01",
    "date_to": "2024.03.01",
    "replace_report": true,
    "shutdown": true,
    "inputs": { "Lots": 0.10 }
  },
  "grid": {
    "Risk": [0.5, 1.0, 1.5],
    "Reverse": [false, true]
  }
}

Rodar:

python mtcli.py tester batch --plan plan.json --ini-dir ./inis

Isso executa 3×2 = 6 testes, gerando INIs em ./inis e relatórios auto‑nomeados (batch_{ts}).


Compilar pelo MetaEditor (com/sem compilação)

python mtcli.py metaeditor compile --file "C:\...\MQL5\Experts\MyEA.mq5"
python mtcli.py metaeditor compile --file "C:\...\MQL5\Scripts\myscript.mq5" --syntax-only

(Switches suportados: /compile, /log, e /s para apenas sintaxe.) 
metatrader5.com


Dicas operacionais (importantes)

Chaves e blocos oficiais: /config, /profile, /portable; seções [StartUp] (inclui Template, Expert, Script, etc.) e [Tester] (visual, otimização, datas, agentes, critério, relatório…). 
metatrader5.com

Pastas padrão: perfis/templates/tester ficam dentro da Data Folder (…\AppData\Roaming\MetaQuotes\Terminal\<id>\MQL5\Profiles\...). Abra pelo File → Open Data Folder. 
metatrader5.com

Agentes locais/remotos/cloud e paralelismo do tester. 
metatrader5.com
+1

Visual: é ligado por Visual=1; controle fino (velocidade/pausa) é feito na UI do testador. 
metatrader5.com

Por que escolhi esses formatos/encodings?

Os INIs gerados são salvos em UTF‑16 LE (Windows/Unicode amigável). A estrutura de arquivos da plataforma e a documentação indicam uso de arquivos de texto Unicode. 
metatrader5.com

Códigos MQL5 são gravados como UTF‑8, o padrão mais compatível para fontes.
“Visual no Strategy Tester via CLI?” → Sim, Visual=1 no bloco [Tester] (a flag --visual faz isso). 
metatrader5.com

“Otimização?” → Sim: Optimization=1|2|3 (slow/genética/all‑symbols) e OptimizationCriterion=...; forward test ajustável. 
metatrader5.com

“Comandos do MetaEditor?” → Sim: /compile:"arquivo" + /log:"arquivo.log" e /s para só sintaxe. 
metatrader5.com
