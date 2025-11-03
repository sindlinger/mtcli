#!/usr/bin/env python3
# mtcli.py — CLI para MetaTrader 5 (Windows + WSL)
# v2 — ajuda por padrão + visual/tester avançado + batch + JSON->TesterInputs
import argparse, os, sys, shutil, subprocess, platform, json, itertools, time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

# ========= Configuração persistente =========

CONFIG_DIR = Path.home() / ".mtcli"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_KEYS = {
    "terminal": "Caminho para terminal64.exe",
    "metaeditor": "Caminho para metaeditor64.exe",
    "data_dir": "Caminho para a Data Folder"
}

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

def win_to_wsl(p: Path) -> Path:
    s = str(p)
    if not is_wsl() or s.startswith("/"):
        return Path(s)
    try:
        out = subprocess.check_output(["wslpath","-u", s]).decode().strip()
        if out:
            return Path(out)
    except Exception:
        pass
    if len(s) >= 3 and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest.lstrip('/')}")
    return Path(s)

def run_win_exe(exe: Path, args: list[str]) -> int:
    '''Executa um .exe do Windows tanto no Windows quanto no WSL.'''
    if is_wsl():
        # Executa o binário Windows diretamente via caminho WSL, evitando
        # as regras de quoting do cmd.exe (que quebram em paths com espaços).
        try:
            exe_wsl = subprocess.check_output(["wslpath", "-u", str(exe)]).decode().strip()
        except Exception:
            exe_wsl = str(exe)

        conv: list[str] = []
        for a in args:
            if a.startswith("/") and ":" in a:
                k, v = a.split(":", 1)
                converted = v
                # Aceita tanto paths Windows quanto WSL no parâmetro.
                if v.startswith("/"):
                    try:
                        converted = wsl_to_win(Path(v))
                    except Exception:
                        converted = v
                conv.append(f"{k}:{converted}")
            else:
                conv.append(a)

        return subprocess.call([exe_wsl] + conv)
    else:
        return subprocess.call([str(exe)] + args)

def powershell_executable() -> str:
    if is_wsl():
        return r"/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    return "powershell.exe"

def run_powershell(command: str) -> int:
    return subprocess.call([powershell_executable(), "-NoProfile", "-Command", command])

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

def to_local_path(value: str|Path) -> Path:
    path = Path(value)
    s = str(path)
    if is_wsl() and len(s) >= 2 and s[1] == ':':
        return win_to_wsl(path)
    if is_wsl() and s.startswith("\\\\"):
        return win_to_wsl(path)
    return path

def write_text_utf8(p: Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")

def write_text_utf16(p: Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-16-le")  # INIs: Unicode/Windows-friendly

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(cfg: dict):
    ensure_dir(CONFIG_DIR)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

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
    if expert: lines.append(f"Expert={_ini_escape(expert)}")
    if script: lines.append(f"Script={_ini_escape(script)}")
    if expert_params: lines.append(f"ExpertParameters={_ini_escape(expert_params)}")
    if script_params: lines.append(f"ScriptParameters={_ini_escape(script_params)}")
    if symbol: lines.append(f"Symbol={symbol}")
    if period: lines.append(f"Period={period}")
    if template: lines.append(f"Template={_ini_escape(template)}")
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
    lines.append(f"Expert={_ini_escape(ea)}")
    if ea_params: lines.append(f"ExpertParameters={_ini_escape(ea_params)}")
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
    if report:
        norm_report = _normalize_report_path(report)
        lines.append(f"Report={_ini_escape(norm_report)}")
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

# ========= Logs e comandos via CommandListener =========

LOG_SEPARATOR = "=" * 60

def collect_log_targets(data_dir: Path|None) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    if data_dir:
        base = win_to_wsl(data_dir)
        log_path = base / "MQL5" / "Logs" / time.strftime("%Y%m%d.log")
        targets.append(("terminal", log_path))
        for label in ("Gen4Engine", "EngineIV"):
            engine_log = base / label / "bin" / "logs" / "gpu_service.log"
            targets.append((f"engine:{label}", engine_log))
    return targets

def tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return [line.rstrip("\r\n") for line in deque(fh, maxlen=limit)]
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-16", errors="replace") as fh:
            return [line.rstrip("\r\n") for line in deque(fh, maxlen=limit)]

def print_log_tail(tag: str, limit: int = 20, data_dir: Path|None = None):
    print(LOG_SEPARATOR)
    print(f"[logs] Últimas {limit} linhas após '{tag}'")
    printed = False
    for label, path in collect_log_targets(data_dir):
        lines = tail_lines(path, limit)
        if not lines:
            continue
        printed = True
        try:
            win_path = to_windows_path(path)
        except Exception:
            win_path = str(path)
        print(f"--- {label}: {win_path} ---")
        for line in lines:
            print(line)
    if not printed:
        print("Nenhum log disponível.")
    print(LOG_SEPARATOR)

def send_listener_command(data_dir: Path, payload: str) -> Path:
    target_dir = data_dir
    if is_wsl():
        try:
            target_dir = win_to_wsl(data_dir)
        except Exception:
            target_dir = Path(str(data_dir))
    files_dir = target_dir / "MQL5" / "Files"
    ensure_dir(files_dir)
    cmdfile = files_dir / "cmd.txt"
    cmdfile.write_text(payload, encoding="ascii")
    return cmdfile

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

void CmdDetachInd(string sym, string s_tf, string ind, int subwin){
   ENUM_TIMEFRAMES tf = ParseTF(s_tf);
   long cid = FindChartId(sym, tf);
   if(cid==0){
      PrintFormat("Nenhum gráfico %s %s encontrado para remover indicador '%s'", sym, s_tf, ind);
      return;
   }
   if(!ChartIndicatorDelete(cid, subwin, ind))
      Print("ChartIndicatorDelete falhou: ", GetLastError());
   else
      PrintFormat("Indicador '%s' removido de %s %s (subjanela %d)", ind, sym, s_tf, subwin);
}

void CmdAttachEA(string sym, string s_tf, string ea_name, string tpl_name){
   ENUM_TIMEFRAMES tf = ParseTF(s_tf);
   long cid = FindChartId(sym, tf);
   if(cid==0) cid = ChartOpen(sym, tf);
   if(cid==0){ Print("Falha ChartOpen: ", GetLastError()); return; }
   string tpl = tpl_name;
   if(tpl == "") tpl = "CommandListenerEA.tpl";
   if(!ChartApplyTemplate(cid, tpl)){
      Print("Falha ChartApplyTemplate para EA: ", GetLastError());
      return;
   }
   PrintFormat("EA '%s' anexado via template '%s' em %s %s", ea_name, tpl, sym, s_tf);
}

void CmdDetachEA(string sym, string s_tf){
   ENUM_TIMEFRAMES tf = ParseTF(s_tf);
   long cid = FindChartId(sym, tf);
   if(cid==0){
      PrintFormat("Nenhum gráfico %s %s encontrado para remover EA", sym, s_tf);
      return;
   }
   if(!ChartApplyTemplate(cid, "")){
      Print("Falha ao remover EA via template vazio: ", GetLastError());
      ExpertRemove();
   }else{
      PrintFormat("EA removido de %s %s", sym, s_tf);
   }
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
   else if(cmd=="DETACH_IND" && n>=4){
      int sub = (n>=5 ? (int)StringToInteger(parts[4]) : 0);
      CmdDetachInd(parts[1], parts[2], parts[3], sub);
   }
   else if(cmd=="ATTACH_EA" && n>=4){
      string tpl = (n>=5 ? parts[4] : "");
      CmdAttachEA(parts[1], parts[2], parts[3], tpl);
   }
   else if(cmd=="DETACH_EA" && n>=3){
      CmdDetachEA(parts[1], parts[2]);
   }
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

def _coerce_path(value: str|Path|None) -> Path|None:
    if value in (None, ""):
        return None
    return Path(value)

def _ini_escape(value: str|None) -> str|None:
    if value is None:
        return None
    return value.replace("\\", "\\\\")

def _normalize_report_path(value: str|None) -> str|None:
    if not value:
        return value
    value = value.replace("/", "\\")
    if not value.startswith("\\"):
        value = "\\" + value
    return value

def to_windows_path(path: Path) -> str:
    try:
        return subprocess.check_output(["wslpath", "-w", str(path)]).decode().strip()
    except Exception:
        return str(path)

def resolve_paths(args):
    cfg = load_config()
    terminal = _coerce_path(
        args.terminal or os.environ.get("MTCLI_TERMINAL") or cfg.get("terminal")
    ) or find_default_terminal()
    metaeditor = _coerce_path(
        args.metaeditor or os.environ.get("MTCLI_METAEDITOR") or cfg.get("metaeditor")
    ) or find_default_metaeditor()
    data_dir = _coerce_path(
        args.data_dir or os.environ.get("MTCLI_DATA_DIR") or cfg.get("data_dir")
    ) or find_default_data_dir()

    if not terminal:
        print("[-] Não encontrei terminal64.exe. Use --terminal ou 'mtcli config set terminal' para informar o caminho.")
    if not metaeditor:
        print("[-] Não encontrei metaeditor64.exe. Use --metaeditor ou 'mtcli config set metaeditor' para informar o caminho.")
    if not data_dir:
        print("[-] Não encontrei Data Folder. Use --data-dir ou 'mtcli config set data_dir' para informar o caminho.")
    return terminal, metaeditor, data_dir


def find_gen4_cli(data_dir: Path|None) -> Path|None:
    candidates: list[Path] = []
    env_cli = os.environ.get("MTCLI_GEN4_CLI") or os.environ.get("MTCLI_ENGINEIV_CLI")
    if env_cli:
        candidates.append(Path(env_cli))
    if data_dir:
        data_path = Path(data_dir)
        candidates.append(data_path / "Gen4Engine" / "gen4_cli.py")
        candidates.append(data_path / "EngineIV" / "gen4_cli.py")
        base = win_to_wsl(data_path).parent
        if base.exists():
            for sub in base.glob("*/Gen4Engine/gen4_cli.py"):
                candidates.append(sub)
            for sub in base.glob("*/EngineIV/gen4_cli.py"):
                candidates.append(sub)
    candidates.append(Path.cwd() / "Gen4Engine" / "gen4_cli.py")
    candidates.append(Path.cwd() / "EngineIV" / "gen4_cli.py")
    for candidate in candidates:
        if not candidate:
            continue
        probe = win_to_wsl(candidate)
        if probe.exists():
            return probe
    return None


def run_gen4_cli(data_dir: Path|None, cli_args: list[str]) -> int:
    cli = find_gen4_cli(data_dir)
    if not cli:
        print("[-] gen4_cli.py não encontrado. Configure MTCLI_GEN4_CLI ou mantenha Gen4Engine/gen4_cli.py junto à Data Folder.")
        return 1
    env = os.environ.copy()
    env.setdefault("CMAKE_EXE_WIN", r"C:\\Program Files\\CMake\\bin\\cmake.exe")
    cmd = [sys.executable, str(cli)] + cli_args
    return subprocess.call(cmd, env=env)

def gen4_service_exe(data_dir: Path|None) -> Path:
    if not data_dir:
        raise SystemExit("Data Folder não configurada. Use --data-dir ou 'mtcli config set data_dir'.")
    base = Path(data_dir)
    candidates = [base / "Gen4Engine" / "bin" / "Gen4EngineService.exe",
                  base / "EngineIV" / "bin" / "Gen4EngineService.exe"]
    for path in candidates:
        wsl_path = win_to_wsl(path)
        if wsl_path.exists():
            return wsl_path
    raise SystemExit("Gen4EngineService.exe não encontrado. Execute o build em Gen4Engine/ primeiro.")

def tasklist_command() -> list[str]:
    if is_wsl():
        return [r"/mnt/c/Windows/System32/tasklist.exe"]
    return ["tasklist"]

def taskkill_command() -> list[str]:
    if is_wsl():
        return [r"/mnt/c/Windows/System32/taskkill.exe"]
    return ["taskkill"]

def service_running() -> bool:
    cmd = tasklist_command() + ["/FI", "IMAGENAME eq Gen4EngineService.exe"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(errors="ignore")
    except subprocess.CalledProcessError:
        return False
    return "Gen4EngineService.exe" in out

def start_service(exe_path: Path) -> int:
    exe_win = wsl_to_win(exe_path)
    ps_cmd = f"Start-Process -FilePath '{exe_win}'"
    return run_powershell(ps_cmd)

def stop_service() -> int:
    cmd = taskkill_command() + ["/IM", "Gen4EngineService.exe", "/F"]
    return subprocess.call(cmd)


def cmd_gen4_service(args):
    _, _, data_dir = resolve_paths(args)

    if args.action == "status":
        running = service_running()
        print(f"[Gen4Service] {'em execução' if running else 'parado'}")
        sys.exit(0 if running else 1)

    if args.action == "stop":
        if not service_running():
            print("[Gen4Service] já parado.")
            sys.exit(0)
        rc = stop_service()
        sys.exit(rc)

    exe_path = gen4_service_exe(data_dir)

    if args.action == "start":
        if service_running():
            print("[Gen4Service] já em execução.")
            sys.exit(0)
        rc = start_service(exe_path)
        sys.exit(rc)

    if args.action == "ensure":
        if service_running():
            print("[Gen4Service] já em execução.")
            sys.exit(0)
        rc = start_service(exe_path)
        sys.exit(rc)

def cmd_detect(args):
    terminal, metaeditor, data_dir = resolve_paths(args)
    print("[Detect]")
    print("Terminal :", terminal)
    print("MetaEditor:", metaeditor)
    print("DataDir  :", data_dir)

def cmd_config_show(args):
    cfg = load_config()
    if not cfg:
        print("[Config] Nenhum valor salvo. Utilize 'mtcli config set <chave> <valor>'.")
        return
    print("[Config]")
    for key in sorted(CONFIG_KEYS):
        val = cfg.get(key)
        status = val if val else "(não definido)"
        print(f"{key:10s}: {status}")

def cmd_config_set(args):
    cfg = load_config()
    cfg[args.key] = args.value
    save_config(cfg)
    print(f"[Config] {args.key} definido para: {args.value}")
    if args.key == "data_dir":
        try:
            ns = SimpleNamespace(terminal=None, metaeditor=None, data_dir=args.value)
            _, metaeditor, data_dir = resolve_paths(ns)
            if data_dir:
                bootstrap_instance(metaeditor, data_dir, force=False, quiet=False)
        except Exception as exc:
            print(f"[bootstrap] Falhou ao preparar CommandListener automaticamente: {exc}")

def cmd_config_unset(args):
    cfg = load_config()
    if args.key in cfg:
        cfg.pop(args.key)
        save_config(cfg)
        print(f"[Config] {args.key} removido.")
    else:
        print(f"[Config] {args.key} já estava vazio.")

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

def ensure_source(metaeditor: Path|None, data_path: Path, rel_path: str, code: str,
                  force: bool=False, quiet: bool=False, compile: bool=True) -> Path:
    target = data_path / "MQL5" / rel_path
    ensure_dir(target.parent)
    created = False
    if force or not target.exists():
        write_text_utf8(target, code)
        created = True
        if not quiet:
            print(f"[bootstrap] Fonte atualizado: {to_windows_path(target)}")
    elif not quiet:
        print(f"[bootstrap] Fonte mantido: {to_windows_path(target)}")

    if compile:
        if not metaeditor:
            if not quiet:
                print("[bootstrap] MetaEditor não configurado. Pulei compilação de", rel_path)
        else:
            log = target.with_suffix(".log")
            args = [f'/compile:{target}', f'/log:{log}']
            rc = run_win_exe(metaeditor, args)
            if rc != 0:
                if not quiet:
                    print(f"[bootstrap] Falha na compilação (código {rc}). Verifique {to_windows_path(log)}")
            elif not quiet:
                print(f"[bootstrap] Compilado: {to_windows_path(target.with_suffix('.ex5'))}")
    return target

def install_source(metaeditor: Path, data_dir: Path, rel_path: str, code: str):
    data_path = to_local_path(data_dir)
    return ensure_source(metaeditor, data_path, rel_path, code, force=True, quiet=False)

def cmd_listener_install(args):
    _, metaeditor, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    if not metaeditor:
        print("[-] MetaEditor não definido. Informe com --metaeditor ou 'mtcli config set metaeditor'.")
        raise SystemExit(1)
    bootstrap_instance(metaeditor, data_dir, force=True, quiet=False)

def cmd_script_install(args):
    _, metaeditor, data_dir = resolve_paths(args)
    if not (metaeditor and data_dir): raise SystemExit(1)
    install_source(metaeditor, data_dir, "Scripts/AplicarTemplate.mq5", SCRIPT_APLICAR_TEMPLATE)

def bootstrap_instance(metaeditor: Path|None, data_dir: Path|str, force: bool=False, quiet: bool=False) -> Path:
    data_path = to_local_path(data_dir)
    ensure_dir(data_path / "MQL5" / "Files")
    ensure_dir(data_path / "MQL5" / "Profiles" / "Templates")
    ensure_source(metaeditor, data_path, "Experts/CommandListenerEA.mq5", EA_LISTENER_CODE, force=force, quiet=quiet)
    ensure_source(metaeditor, data_path, "Scripts/AplicarTemplate.mq5", SCRIPT_APLICAR_TEMPLATE, force=force, quiet=quiet, compile=False)
    return data_path

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
    if args.subcmd == "apply-template":
        tf = timeframe_ok(args.period)
        line = f"APPLY_TPL;{args.symbol};{tf};{args.template}"
    elif args.subcmd == "attach-indicator":
        tf = timeframe_ok(args.period)
        sub = str(args.subwindow if args.subwindow is not None else 0)
        line = f"ATTACH_IND;{args.symbol};{tf};{args.indicator};{sub}"
    else:
        raise SystemExit("Comando desconhecido.")
    cmdfile = send_listener_command(data_dir, line)
    print(f"[>] Comando enviado: {line}")
    print(f"[i] O EA lê e apaga {to_windows_path(cmdfile)}.")

def cmd_bootstrap(args):
    _, metaeditor, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit("Data Folder não configurada. Use --data-dir ou 'mtcli config set data_dir'.")
    bootstrap_instance(metaeditor, data_dir, force=args.force, quiet=False)
    print("[bootstrap] Finalizado.")

def chart_indicator_attach(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    line = f"ATTACH_IND;{args.symbol};{timeframe_ok(args.period)};{args.indicator};{args.subwindow}"
    cmdfile = send_listener_command(data_dir, line)
    print(f"[cmd] {line}")
    print(f"[cmd] escrito em {to_windows_path(cmdfile)}")
    time.sleep(0.5)
    print_log_tail("chart indicator attach", data_dir=data_dir)

def chart_indicator_detach(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    sub = args.subwindow if args.subwindow is not None else 0
    line = f"DETACH_IND;{args.symbol};{timeframe_ok(args.period)};{args.indicator};{sub}"
    cmdfile = send_listener_command(data_dir, line)
    print(f"[cmd] {line}")
    print(f"[cmd] escrito em {to_windows_path(cmdfile)}")
    time.sleep(0.5)
    print_log_tail("chart indicator detach", data_dir=data_dir)

def chart_raw_send(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    line = args.payload
    cmdfile = send_listener_command(data_dir, line)
    print(f"[cmd] {line}")
    print(f"[cmd] escrito em {to_windows_path(cmdfile)}")
    time.sleep(0.5)
    print_log_tail("chart raw", data_dir=data_dir)

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

    sub = p.add_subparsers(dest="cmd")

    d = sub.add_parser("detect", help="Detecta caminhos padrão")
    d.set_defaults(func=cmd_detect)

    cfg = sub.add_parser("config", help="Gerenciar defaults do mtcli")
    cfgsub = cfg.add_subparsers(dest="ccmd", required=True)
    cfg_show = cfgsub.add_parser("show", help="Listar caminhos configurados")
    cfg_show.set_defaults(func=cmd_config_show)
    cfg_set = cfgsub.add_parser("set", help="Salvar um caminho padrão")
    cfg_set.add_argument("key", choices=sorted(CONFIG_KEYS))
    cfg_set.add_argument("value")
    cfg_set.set_defaults(func=cmd_config_set)
    cfg_unset = cfgsub.add_parser("unset", help="Remover um caminho salvo")
    cfg_unset.add_argument("key", choices=sorted(CONFIG_KEYS))
    cfg_unset.set_defaults(func=cmd_config_unset)

    boot = sub.add_parser("bootstrap", help="Prepara instância: CommandListenerEA, scripts e pastas")
    boot.add_argument("--force", action="store_true", help="Sobrescreve fontes mesmo se existirem")
    boot.set_defaults(func=cmd_bootstrap)

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

    chart = sub.add_parser("chart", help="Operações diretas via CommandListenerEA")
    chart_sub = chart.add_subparsers(dest="chart_cmd", required=True)

    ci = chart_sub.add_parser("indicator", help="Anexar/remover indicadores")
    ci_sub = ci.add_subparsers(dest="indicator_cmd", required=True)

    cia = ci_sub.add_parser("attach", help="Anexar indicador (sem reiniciar MT5)")
    cia.add_argument("--symbol", required=True)
    cia.add_argument("--period", required=True)
    cia.add_argument("--indicator", required=True)
    cia.add_argument("--subwindow", type=int, default=0)
    cia.set_defaults(func=chart_indicator_attach)

    cid = ci_sub.add_parser("detach", help="Remover indicador")
    cid.add_argument("--symbol", required=True)
    cid.add_argument("--period", required=True)
    cid.add_argument("--indicator", required=True)
    cid.add_argument("--subwindow", type=int, default=0)
    cid.set_defaults(func=chart_indicator_detach)

    craw = chart_sub.add_parser("send", help="Enviar payload cru ao CommandListener (cmd.txt)")
    craw.add_argument("payload", help="Linha completa (ex.: ATTACH_IND;... )")
    craw.set_defaults(func=chart_raw_send)

    eng = sub.add_parser("gen4", help="Integração com o serviço Gen4")
    engsub = eng.add_subparsers(dest="ecmd", required=True)
    engsvc = engsub.add_parser("service", help="Gerencia Gen4_GpuEngineService")
    engsvc.add_argument("action", choices=["start", "stop", "ensure", "status"], help="Ação do serviço")
    engsvc.set_defaults(func=cmd_gen4_service)

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
    if not hasattr(args, "func"):
        # Sem subcomando explícito, assume detect
        args.func = cmd_detect
    args.func(args)

if __name__ == "__main__":
    main()
def chart_expert_attach(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    tpl_name = args.template if args.template else create_template_for_expert(data_dir, args.expert, args.symbol, args.period, args.preset)
    line = f"ATTACH_EA;{args.symbol};{timeframe_ok(args.period)};{args.expert};{tpl_name}"
    cmdfile = send_listener_command(data_dir, line)
    print(f"[cmd] {line}")
    print(f"[cmd] escrito em {to_windows_path(cmdfile)}")
    time.sleep(1.0)
    print_log_tail("chart expert attach", data_dir=data_dir)

def chart_expert_detach(args):
    _, _, data_dir = resolve_paths(args)
    if not data_dir:
        raise SystemExit(1)
    line = f"DETACH_EA;{args.symbol};{timeframe_ok(args.period)}"
    cmdfile = send_listener_command(data_dir, line)
    print(f"[cmd] {line}")
    print(f"[cmd] escrito em {to_windows_path(cmdfile)}")
    time.sleep(0.5)
    print_log_tail("chart expert detach", data_dir=data_dir)
