#!/usr/bin/env python3
# mtcli.py — CLI para MetaTrader 5 (Windows + WSL)
# v2 — ajuda por padrão + visual/tester avançado + batch + JSON->TesterInputs
import argparse, os, sys, shutil, subprocess, platform, json, itertools, time
from pathlib import Path

# ========= Detecção de ambiente =========

def is_wsl():
    rel = platform.release().lower()
    return "microsoft" in rel or "wsl" in os.environ.get("WSL_DISTRO_NAME","").lower()

def wsl_to_win(p: Path) -> str:
    s = str(p)
    if not is_wsl():
        return s
    try:
        out = subprocess.check_output(["wslpath","-w",s]).decode().strip()
        return out
    except Exception:
        if s.startswith("/mnt/") and len(s) > 7:
            drive = s[5].upper()
            rest = s[7:].replace("/", "\\")
            return f"{drive}:\\{rest}"
        return s

def run_win_exe(exe: Path, args: list[str]) -> int:
    '''Executa um .exe do Windows tanto no Windows quanto no WSL.'''
    if is_wsl():
        cmdexe = Path("/mnt/c/Windows/System32/cmd.exe")
        exe_win = wsl_to_win(exe)
        conv = []
        for a in args:
            if a.startswith("/"):
                if ":" in a:
                    k, v = a.split(":", 1)
                    conv.append(f'{k}:{wsl_to_win(Path(v))}')
                else:
                    conv.append(a)
            else:
                conv.append(f'"{wsl_to_win(Path(a))}"')
        cmd = [str(cmdexe), "/C", f'"{exe_win}" ' + " ".join(conv)]
        return subprocess.call(cmd)
    else:
        return subprocess.call([str(exe)] + args)

def find_default_terminal() -> Path|None:
    guesses = [
        Path("C:/Program Files/MetaTrader 5/terminal64.exe"),
        Path("C:/Program Files/MetaTrader 5/terminal.exe"),
        Path("C:/Program Files (x86)/MetaTrader 5/terminal64.exe"),
        Path("C:/Program Files (x86)/MetaTrader 5/terminal.exe"),
    ]
    for g in guesses:
        if g.exists():
            return g
    return None

def find_default_metaeditor() -> Path|None:
    guesses = [
        Path("C:/Program Files/MetaTrader 5/metaeditor64.exe"),
        Path("C:/Program Files/MetaTrader 5/metaeditor.exe"),
        Path("C:/Program Files (x86)/MetaTrader 5/metaeditor64.exe"),
        Path("C:/Program Files (x86)/MetaTrader 5/metaeditor.exe"),
    ]
    for g in guesses:
        if g.exists():
            return g
    return None

def find_default_data_dir() -> Path|None:
    base = Path(os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Roaming\MetaQuotes\Terminal"))
    if base.exists():
        candidates = [p for p in base.iterdir() if p.is_dir() and (p / "MQL5").exists()]
        if candidates:
            def key(p):
                ini = p / "Config" / "terminal.ini"
                try: return ini.stat().st_mtime
                except Exception: return 0
            return sorted(candidates, key=key, reverse=True)[0]
    return None

# ========= IO util =========

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def write_text_utf8(p: Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")

def write_text_utf16(p: Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-16-le")  # INIs: Unicode/Windows-friendly

def ts_now():
    return time.strftime("%Y%m%d-%H%M%S")

def timeframe_ok(tf: str) -> str:
    tf = tf.upper()
    allowed = {"M1","M2","M3","M4","M5","M6","M10","M12","M15","M20","M30",
               "H1","H2","H3","H4","H6","H8","H12","D1","W1","MN1"}
    if tf not in allowed:
        raise SystemExit(f"Timeframe inválido: {tf}")
    return tf

# ========= Builders de INI =========

def build_ini_startup(symbol: str|None, period: str|None, template: str|None,
                      expert: str|None, script: str|None, expert_params: str|None,
                      script_params: str|None, shutdown: bool|None) -> str:
    lines = ["[StartUp]"]
    if expert: lines.append(f"Expert={expert}")
    if script: lines.append(f"Script={script}")
    if expert_params: lines.append(f"ExpertParameters={expert_params}")
    if script_params: lines.append(f"ScriptParameters={script_params}")
    if symbol: lines.append(f"Symbol={symbol}")
    if period: lines.append(f"Period={period}")
    if template: lines.append(f"Template={template}")
    if shutdown is not None: lines.append(f"ShutdownTerminal={1 if shutdown else 0}")
    return "\n".join(lines) + "\n"

def build_ini_tester(ea: str, ea_params: str|None, symbol: str, period: str,
                     model: int, optimization: int, criterion: int|None,
                     date_from: str|None, date_to: str|None, forward_mode: int|None,
                     forward_date: str|None, deposit: str|None, currency: str|None,
                     leverage: str|None, visual: bool|None, report: str|None,
                     replace_report: bool|None, shutdown: bool|None,
                     use_local: int|None, use_remote: int|None, use_cloud: int|None,
                     execution_mode: int|None, login: str|None, port: int|None) -> str:
    lines = ["[Tester]"]
    lines.append(f"Expert={ea}")
    if ea_params: lines.append(f"ExpertParameters={ea_params}")
    lines.append(f"Symbol={symbol}")
    lines.append(f"Period={period}")
    if login: lines.append(f"Login={login}")
    lines.append(f"Model={model}")  # 0..4
    if execution_mode is not None: lines.append(f"ExecutionMode={execution_mode}")
    lines.append(f"Optimization={optimization}")  # 0 off; 1 slow; 2 fast genetic; 3 all symbols
    if criterion is not None: lines.append(f"OptimizationCriterion={criterion}")
    if date_from: lines.append(f"FromDate={date_from}")
    if date_to: lines.append(f"ToDate={date_to}")
    if forward_mode is not None: lines.append(f"ForwardMode={forward_mode}")
    if forward_date: lines.append(f"ForwardDate={forward_date}")
    if report: lines.append(f"Report={report}")
    if replace_report is not None: lines.append(f"ReplaceReport={1 if replace_report else 0}")
    if deposit: lines.append(f"Deposit={deposit}")
    if currency: lines.append(f"Currency={currency}")
    if leverage: lines.append(f"Leverage={leverage}")
    if use_local is not None: lines.append(f"UseLocal={use_local}")
    if use_remote is not None: lines.append(f"UseRemote={use_remote}")
    if use_cloud is not None: lines.append(f"UseCloud={use_cloud}")
    if visual is not None: lines.append(f"Visual={1 if visual else 0}")
    if port is not None: lines.append(f"Port={port}")
    return "\n".join(lines) + "\n"

def _fmt_val(v):
    if isinstance(v, bool): return "true" if v else "false"
    return str(v)

def build_ini_testerinputs(inputs: dict) -> str:
    '''
    Constrói a seção [TesterInputs].
    Formatos aceitos por item:
      - valor único:   {"Lots": 0.10}
      - otimização:    {"Risk": {"start":0.5,"step":0.5,"stop":5,"value":1.0}}
                        -> Risk=1.0||0.5||0.5||5||Y
      - strings/horários: {"OpenTime": "03:00"} -> OpenTime=03:00
    '''
    lines = ["[TesterInputs]"]
    for name, spec in inputs.items():
        if isinstance(spec, dict) and all(k in spec for k in ("start","step","stop")):
            cur = spec.get("value", spec["start"])
            line = f"{name}={_fmt_val(cur)}||{_fmt_val(spec['start'])}||{_fmt_val(spec['step'])}||{_fmt_val(spec['stop'])}||Y"
        else:
            val = spec.get("value") if isinstance(spec, dict) else spec
            line = f"{name}={_fmt_val(val)}"
        lines.append(line)
    return "\n".join(lines) + "\n"

# ========= Códigos MQL5 (EA escutador + Script) =========

EA_LISTENER_CODE = r'''
#property strict
input string In_CommandFile = "cmd.txt"; // MQL5\Files\cmd.txt

int OnInit(){ EventSetTimer(1); return(INIT_SUCCEEDED); }
void OnDeinit(const int _){ EventKillTimer(); }

ENUM_TIMEFRAMES ParseTF(const string s){
   string u=StringToUpper(s);
   if(u=="M1") return PERIOD_M1; if(u=="M5") return PERIOD_M5; if(u=="M15") return PERIOD_M15;
   if(u=="M30") return PERIOD_M30; if(u=="H1") return PERIOD_H1; if(u=="H4") return PERIOD_H4;
   if(u=="D1") return PERIOD_D1; if(u=="W1") return PERIOD_W1; if(u=="MN1"||u=="MN") return PERIOD_MN1;
   return PERIOD_CURRENT;
}
long FindChartId(const string sym, ENUM_TIMEFRAMES tf){
   long id=ChartFirst();
   while(id>=0){
      if(ChartSymbol(id)==sym && (tf==PERIOD_CURRENT || ChartPeriod(id)==tf)) return id;
      id=ChartNext(id);
   }
   return 0;
}
void CmdApplyTpl(string sym, string s_tf, string tpl){
   ENUM_TIMEFRAMES tf = ParseTF(s_tf);
   long cid = FindChartId(sym, tf);
   if(cid==0) cid = ChartOpen(sym, tf);
   if(cid==0){ Print("Falha ChartOpen: ", GetLastError()); return; }
   if(!ChartApplyTemplate(cid, tpl)) Print("Falha ChartApplyTemplate: ", GetLastError());
   else PrintFormat("Template '%s' aplicado em %s %s", tpl, sym, s_tf);
}
void CmdAttachInd(string sym, string s_tf, string ind, int subwin){
   ENUM_TIMEFRAMES tf = ParseTF(s_tf);
   long cid = FindChartId(sym, tf);
   if(cid==0) cid = ChartOpen(sym, tf);
   if(cid==0){ Print("Falha ChartOpen: ", GetLastError()); return; }
   int handle = iCustom(sym, tf, ind);
   if(handle==INVALID_HANDLE){ Print("iCustom falhou: ", GetLastError()); return; }
   if(!ChartIndicatorAdd(cid, subwin, handle)) Print("ChartIndicatorAdd falhou: ", GetLastError());
   else PrintFormat("Indicador '%s' anexado em %s %s (subjanela %d)", ind, sym, s_tf, subwin);
}
void OnTimer(){
   if(!FileIsExist(In_CommandFile)) return;
   int h=FileOpen(In_CommandFile, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h==INVALID_HANDLE) return;
   string line = FileReadString(h);
   FileClose(h);
   FileDelete(In_CommandFile);
   string parts[]; int n = StringSplit(line,';',parts);
   if(n<1) return;
   string cmd = parts[0];
   if(cmd=="APPLY_TPL" && n>=4) CmdApplyTpl(parts[1], parts[2], parts[3]);
   else if(cmd=="ATTACH_IND" && n>=5) CmdAttachInd(parts[1], parts[2], parts[3], (int)StringToInteger(parts[4]));
   else Print("Comando desconhecido: ", line);
}
'''.lstrip()

SCRIPT_APLICAR_TEMPLATE = r'''
#property script_show_inputs
input string In_Template   = "MeuTemplate.tpl";
input string In_Symbol     = "";
input ENUM_TIMEFRAMES In_TF = PERIOD_CURRENT;
input bool   In_OpenIfMiss = true;

long FindChartId(const string sym, ENUM_TIMEFRAMES tf){
   long id = ChartFirst();
   while(id >= 0){
      if((sym=="" || ChartSymbol(id)==sym) && (tf==PERIOD_CURRENT || ChartPeriod(id)==tf)) return id;
      id = ChartNext(id);
   }
   return 0;
}
void OnStart(){
   string sym = (In_Symbol=="" ? _Symbol : In_Symbol);
   ENUM_TIMEFRAMES tf = (In_TF==PERIOD_CURRENT ? (ENUM_TIMEFRAMES)Period() : In_TF);
   long cid = FindChartId(sym, tf);
   if(cid==0 && In_OpenIfMiss){
      cid = ChartOpen(sym, tf);
      if(cid==0){ Print("Falha ChartOpen: ", GetLastError()); return; }
   }
   if(!ChartApplyTemplate(cid, In_Template)) Print("Falha ChartApplyTemplate: ", GetLastError());
   else PrintFormat("Template '%s' aplicado em %s %s", In_Template, sym, EnumToString(tf));
}
'''.lstrip()

# ========= Ações =========

def resolve_paths(args):
    terminal = Path(args.terminal) if args.terminal else find_default_terminal()
    metaeditor = Path(args.metaeditor) if args.metaeditor else find_default_metaeditor()
    data_dir = Path(args.data_dir) if args.data_dir else find_default_data_dir()
    if not terminal:
        print("[-] Não encontrei terminal64.exe. Use --terminal para informar o caminho.")
    if not metaeditor:
        print("[-] Não encontrei metaeditor64.exe. Use --metaeditor para informar o caminho.")
    if not data_dir:
        print("[-] Não encontrei Data Folder. Use --data-dir para informar o caminho.")
    return terminal, metaeditor, data_dir

def cmd_detect(args):
    terminal, metaeditor, data_dir = resolve_paths(args)
    print("[Detect]")
    print("Terminal :", terminal)
    print("MetaEditor:", metaeditor)
    print("DataDir  :", data_dir)

def cmd_profile_create(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir: raise SystemExit(1)
    charts = data_dir / "MQL5" / "Profiles" / "Charts"
    dst = charts / args.name
    if dst.exists():
        print(f"[=] Profile '{args.name}' já existe em {dst}")
        return
    src = charts / "Default"
    if src.exists(): shutil.copytree(src, dst)
    else: ensure_dir(dst)
    print(f"[+] Profile criado em: {dst}")

def cmd_open(args):
    terminal, _, data_dir = resolve_paths(args)
    if not terminal: raise SystemExit(1)
    if args.profile and not (data_dir and (data_dir / "MQL5" / "Profiles" / "Charts" / args.profile).exists()):
        print(f"[!] Aviso: profile '{args.profile}' não encontrado; o MT5 ainda tentará abrir.")
    if args.template or args.symbol or args.period or args.expert or args.script:
        ini = Path(args.ini or (Path.cwd() / "start.ini"))
        content = build_ini_startup(
            args.symbol, timeframe_ok(args.period) if args.period else None,
            args.template, args.expert, args.script,
            args.expert_parameters, args.script_parameters, args.shutdown)
        write_text_utf16(ini, content)
        code = run_win_exe(terminal, [f"/config:{ini}"] + ([f"/profile:{args.profile}"] if args.profile else []) + (["/portable"] if args.portable else []))
    else:
        args_list = ([f"/profile:{args.profile}"] if args.profile else []) + (["/portable"] if args.portable else [])
        code = run_win_exe(terminal, args_list)
    sys.exit(code)

def install_source(metaeditor: Path, data_dir: Path, rel_path: str, code: str):
    src = data_dir / "MQL5" / rel_path
    write_text_utf8(src, code)
    log = src.with_suffix(".log")
    args = [f'/compile:{src}', f'/log:{log}']
    rc = run_win_exe(metaeditor, args)
    if rc != 0: print(f"[!] MetaEditor retornou código {rc} (ver log: {log})")
    else:       print(f"[+] Compilado: {src} (log: {log})")
    return src

def cmd_listener_install(args):
    _, metaeditor, data_dir = resolve_paths(args)
    if not (metaeditor and data_dir): raise SystemExit(1)
    install_source(metaeditor, data_dir, "Experts/CommandListenerEA.mq5", EA_LISTENER_CODE)

def cmd_script_install(args):
    _, metaeditor, data_dir = resolve_paths(args)
    if not (metaeditor and data_dir): raise SystemExit(1)
    install_source(metaeditor, data_dir, "Scripts/AplicarTemplate.mq5", SCRIPT_APLICAR_TEMPLATE)

def cmd_listener_run(args):
    terminal, _, _ = resolve_paths(args)
    if not terminal: raise SystemExit(1)
    ini = Path(args.ini or (Path.cwd() / "listener.ini"))
    content = build_ini_startup(
        args.symbol, timeframe_ok(args.period),
        None, "CommandListenerEA", None, None, None, False)
    write_text_utf16(ini, content)
    sys.exit(run_win_exe(terminal, [f"/config:{ini}"]))

def cmd_listener_send(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir: raise SystemExit(1)
    files = data_dir / "MQL5" / "Files"
    ensure_dir(files)
    cmdfile = files / "cmd.txt"
    if args.subcmd == "apply-template":
        tf = timeframe_ok(args.period)
        line = f"APPLY_TPL;{args.symbol};{tf};{args.template}"
    elif args.subcmd == "attach-indicator":
        tf = timeframe_ok(args.period)
        sub = str(args.subwindow if args.subwindow is not None else 0)
        line = f"ATTACH_IND;{args.symbol};{tf};{args.indicator};{sub}"
    else:
        raise SystemExit("Comando desconhecido.")
    cmdfile.write_text(line, encoding="ascii")
    print(f"[>] Comando enviado: {line}")
    print(f"[i] O EA lê e apaga {cmdfile}.")

def cmd_tester_run(args):
    terminal, _, _ = resolve_paths(args)
    if not terminal: raise SystemExit(1)

    ini = Path(args.ini or (Path.cwd() / f"tester-{ts_now()}.ini"))
    report = args.report
    if report and "{ts}" in report:
        report = report.replace("{ts}", ts_now())

    content = build_ini_tester(
        ea=args.ea,
        ea_params=args.ea_parameters,
        symbol=args.symbol,
        period=timeframe_ok(args.period),
        model={"everytick":0,"ohlc1":1,"open":2,"math":3,"realticks":4}[args.model],
        optimization={"off":0,"slow":1,"fast":2,"allsymbols":3}[args.opt],
        criterion={"max_balance":0,"balance_x_profit":1,"balance_x_exp_payoff":2,"(100%-dd)xbal":3,
                   "balance_x_recovery":4,"balance_x_sharpe":5,"custom_ontester":6,"complex":7}.get(args.criterion, None),
        date_from=args.date_from, date_to=args.date_to,
        forward_mode={"off":0,"1/2":1,"1/3":2,"1/4":3,"custom":4}.get(args.forward, None),
        forward_date=args.forward_date,
        deposit=args.deposit, currency=args.currency, leverage=args.leverage,
        visual=args.visual, report=report, replace_report=args.replace_report,
        shutdown=args.shutdown,
        use_local={False:0, True:1}.get(args.use_local, None),
        use_remote={False:0, True:1}.get(args.use_remote, None),
        use_cloud={False:0, True:1}.get(args.use_cloud, None),
        execution_mode=args.exec_delay_ms if args.exec_delay_ms is not None else None,
        login=args.login, port=args.port
    )

    if args.inputs_json:
        data = json.loads(Path(args.inputs_json).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit("--inputs-json deve conter um objeto {param: espec}.")
        content += "\n" + build_ini_testerinputs(data)

    write_text_utf16(ini, content)
    print(f"[i] INI do tester em: {ini}")
    sys.exit(run_win_exe(terminal, [f"/config:{ini}"]))

def cmd_tester_batch(args):
    terminal, _, _ = resolve_paths(args)
    if not terminal: raise SystemExit(1)

    spec = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    base = spec.get("base", {})
    grid = spec.get("grid", {})
    keys = sorted(grid.keys())
    values = [grid[k] for k in keys]
    import itertools
    combos = list(itertools.product(*values))
    print(f"[i] Executando {len(combos)} combinações...")
    rc_global = 0

    for idx, combo in enumerate(combos, 1):
        inputs = base.get("inputs", {}).copy()
        label_parts = []
        for k, v in zip(keys, combo):
            inputs[k] = v
            label_parts.append(f"{k}-{str(v).replace(':','')}")
        label = "_".join(label_parts)

        ini = Path(args.ini_dir) / f"batch_{idx:03d}_{label}.ini"
        report_name = base.get("report", r"\reports\batch_{ts}.htm").replace("{ts}", ts_now()).replace("{label}", label)

        content = build_ini_tester(
            ea=base["ea"], ea_params=base.get("ea_parameters"),
            symbol=base["symbol"], period=timeframe_ok(base["period"]),
            model={"everytick":0,"ohlc1":1,"open":2,"math":3,"realticks":4}[base.get("model","everytick")],
            optimization={"off":0,"slow":1,"fast":2,"allsymbols":3}[base.get("opt","off")],
            criterion={"max_balance":0,"balance_x_profit":1,"balance_x_exp_payoff":2,"(100%-dd)xbal":3,
                       "balance_x_recovery":4,"balance_x_sharpe":5,"custom_ontester":6,"complex":7}.get(base.get("criterion"), None),
            date_from=base.get("date_from"), date_to=base.get("date_to"),
            forward_mode={"off":0,"1/2":1,"1/3":2,"1/4":3,"custom":4}.get(base.get("forward"), None),
            forward_date=base.get("forward_date"),
            deposit=base.get("deposit"), currency=base.get("currency"), leverage=base.get("leverage"),
            visual=base.get("visual"), report=report_name, replace_report=base.get("replace_report"),
            shutdown=base.get("shutdown", True),
            use_local={False:0, True:1}.get(base.get("use_local"), None),
            use_remote={False:0, True:1}.get(base.get("use_remote"), None),
            use_cloud={False:0, True:1}.get(base.get("use_cloud"), None),
            execution_mode=base.get("exec_delay_ms"), login=base.get("login"),
            port=base.get("port")
        )
        content += "\n" + build_ini_testerinputs(inputs)
        write_text_utf16(ini, content)

        print(f"[{idx}/{len(combos)}] {label} -> {ini}")
        rc = run_win_exe(terminal, [f"/config:{ini}"])
        rc_global = rc_global or rc
        if rc != 0:
            print(f"[!] Código de retorno {rc} nesta combinação.")

    sys.exit(rc_global)

def cmd_metaeditor_compile(args):
    _, metaeditor, _ = resolve_paths(args)
    if not metaeditor: raise SystemExit(1)
    log = Path(args.log) if args.log else (Path(args.file).with_suffix(".log"))
    a = [f'/compile:{Path(args.file)}', f'/log:{log}']
    if args.syntax_only: a.append('/s')
    sys.exit(run_win_exe(metaeditor, a))

# ========= Parser =========

def main():
    p = argparse.ArgumentParser(prog="mtcli", description="CLI para MetaTrader 5 (Windows + WSL)")
    p.add_argument("--terminal", help="Caminho para terminal64.exe")
    p.add_argument("--metaeditor", help="Caminho para metaeditor64.exe")
    p.add_argument("--data-dir", help="Caminho para a Data Folder (…\\MetaQuotes\\Terminal\\<id>)")

    # Se nenhum subcomando for passado, mostra help + exemplos
    if len(sys.argv) == 1:
        p.print_help()
        print("\nExemplos rápidos:")
        print("  mtcli detect")
        print("  mtcli open --symbol EURUSD --period M15 --template MeuTemplate.tpl")
        print("  mtcli tester run --ea Examples\\MACD\\MACD Sample --symbol EURUSD --period M1 --visual --date-from 2024.01.01 --date-to 2024.06.01 --report \\reports\\run_{ts}.htm --replace-report --shutdown")
        sys.exit(0)

    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="Detecta caminhos padrão")
    d.set_defaults(func=cmd_detect)

    prof = sub.add_parser("profile", help="Gerenciar perfis")
    profsub = prof.add_subparsers(dest="pcmd", required=True)
    pc = profsub.add_parser("create", help="Criar perfil (copia 'Default' se existir)")
    pc.add_argument("name")
    pc.set_defaults(func=cmd_profile_create)

    opn = sub.add_parser("open", help="Abrir MT5 com perfil/template/EA/Script")
    opn.add_argument("--profile")
    opn.add_argument("--template", help="Nome do .tpl em MQL5\\Profiles\\Templates")
    opn.add_argument("--symbol")
    opn.add_argument("--period")
    opn.add_argument("--expert", help="Ex.: CommandListenerEA")
    opn.add_argument("--expert-parameters", help="Nome do .set em MQL5\\Profiles\\Tester")
    opn.add_argument("--script")
    opn.add_argument("--script-parameters")
    opn.add_argument("--shutdown", action="store_true", help="Fechar terminal ao fim do Script")
    opn.add_argument("--portable", action="store_true", help="Portable mode")
    opn.add_argument("--ini", help="Salvar INI gerado neste caminho")
    opn.set_defaults(func=cmd_open)

    lst = sub.add_parser("listener", help="Instalar/rodar EA escutador e enviar comandos")
    lsub = lst.add_subparsers(dest="lcmd", required=True)
    li = lsub.add_parser("install", help="Instala e compila Experts\\CommandListenerEA.mq5")
    li.set_defaults(func=cmd_listener_install)
    lr = lsub.add_parser("run", help="Abre MT5 com o EA escutador anexado")
    lr.add_argument("--symbol", required=True)
    lr.add_argument("--period", required=True)
    lr.add_argument("--ini", help="Salvar INI gerado neste caminho")
    lr.set_defaults(func=cmd_listener_run)
    ls = lsub.add_parser("send", help="Envia um comando ao EA (arquivo MQL5\\Files\\cmd.txt)")
    lssub = ls.add_subparsers(dest="subcmd", required=True)
    ap = lssub.add_parser("apply-template", help="APPLY_TPL;SYMBOL;TF;TEMPLATE")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--template", required=True)
    ap.set_defaults(func=cmd_listener_send)
    ai = lssub.add_parser("attach-indicator", help="ATTACH_IND;SYMBOL;TF;INDICATOR;SUBWIN")
    ai.add_argument("--symbol", required=True)
    ai.add_argument("--period", required=True)
    ai.add_argument("--indicator", required=True)
    ai.add_argument("--subwindow", type=int, default=0)
    ai.set_defaults(func=cmd_listener_send)

    sc = sub.add_parser("script", help="Instalar scripts de apoio")
    scsub = sc.add_subparsers(dest="scmd", required=True)
    si = scsub.add_parser("install-aplicar-template", help="Instala Scripts\\AplicarTemplate.mq5")
    si.set_defaults(func=cmd_script_install)

    tst = sub.add_parser("tester", help="Executar Strategy Tester/otimização")
    ts = tst.add_subparsers(dest="tcmd", required=True)
    tr = ts.add_parser("run", help="Rodar teste/otimização")
    tr.add_argument("--ea", required=True, help=r"EA relativo (ex.: Examples\MACD\MACD Sample)")
    tr.add_argument("--ea-parameters", dest="ea_parameters", help=r"Arquivo .set em MQL5\Profiles\Tester (opcional)")
    tr.add_argument("--symbol", required=True)
    tr.add_argument("--period", required=True)
    tr.add_argument("--model", choices=["everytick","ohlc1","open","math","realticks"], default="everytick")
    tr.add_argument("--opt", choices=["off","slow","fast","allsymbols"], default="off")
    tr.add_argument("--criterion", choices=["max_balance","balance_x_profit","balance_x_exp_payoff",
                                            "(100%-dd)xbal","balance_x_recovery","balance_x_sharpe",
                                            "custom_ontester","complex"])
    tr.add_argument("--date-from", dest="date_from")
    tr.add_argument("--date-to", dest="date_to")
    tr.add_argument("--forward", choices=["off","1/2","1/3","1/4","custom"])
    tr.add_argument("--forward-date", dest="forward_date")
    tr.add_argument("--deposit")
    tr.add_argument("--currency")
    tr.add_argument("--leverage")
    tr.add_argument("--visual", action="store_true", help="Ativa teste visual")
    tr.add_argument("--report", help=r"Caminho relativo ao diretório do terminal (use {ts} p/ carimbo de tempo)")
    tr.add_argument("--replace-report", action="store_true")
    tr.add_argument("--shutdown", action="store_true", help="Fecha terminal ao terminar")
    tr.add_argument("--use-local", action="store_true")
    tr.add_argument("--use-remote", action="store_true")
    tr.add_argument("--use-cloud", action="store_true")
    tr.add_argument("--exec-delay-ms", type=int, help="ExecutionMode (>0 atraso fixo; -1 aleatório)")
    tr.add_argument("--login", help="Número de conta emulado (opcional)")
    tr.add_argument("--port", type=int, help="Port do agente local (para rodar paralelos)")
    tr.add_argument("--inputs-json", help="Arquivo JSON com inputs/otimizações p/ [TesterInputs]")
    tr.add_argument("--ini", help="Salvar INI gerado neste caminho")
    tr.set_defaults(func=cmd_tester_run)

    tb = ts.add_parser("batch", help="Rodar várias combinações (grid) em série")
    tb.add_argument("--plan", required=True, help="JSON com 'base' e 'grid'")
    tb.add_argument("--ini-dir", default=str(Path.cwd()), help="Onde salvar os .ini gerados")
    tb.set_defaults(func=cmd_tester_batch)

    me = sub.add_parser("metaeditor", help="Ações do MetaEditor via CLI")
    mesub = me.add_subparsers(dest="mcmd", required=True)
    mc = mesub.add_parser("compile", help="Compilar arquivo .mq5/.mqh/.mqproj")
    mc.add_argument("--file", required=True)
    mc.add_argument("--log")
    mc.add_argument("--syntax-only", action="store_true", help="Somente checagem de sintaxe (/s)")
    mc.set_defaults(func=cmd_metaeditor_compile)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
