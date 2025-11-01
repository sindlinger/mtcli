//+------------------------------------------------------------------+
//|                                         CSV_Reader_Plot_v3_1.mq5 |
//| v3.1: Debug opcional, remoção de BOM, tolerância de barra.       |
//+------------------------------------------------------------------+
#property version   "1.21"
#property strict
#property indicator_separate_window
#property indicator_buffers 8
#property indicator_plots   8

input string In_FileName           = "wavelet_phase_m1_MT5.csv";          // Nome do CSV (relativo à pasta Files)
input bool   In_CommonFiles        = false;               // Usar Common Files?
input string In_Separator          = "\\t";               // ",", ";", "|" ou "\t" para TAB
input bool   In_HasHeader          = true;                // Primeira linha é header
// Tempo em 1 OU 2 colunas
input string In_TimeColumn         = "";                  // Se usar 1 coluna (ex.: "datetime" ou índice "0")
input string In_TimeDateColumn     = "<DATE>";            // Se usar 2 colunas: data
input string In_TimeTimeColumn     = "<TIME>";            // Se usar 2 colunas: hora
input int    In_TZ_AdjustMin       = 0;                   // Ajuste de timezone (minutos)
// Séries (valores a plotar)
input string In_ValueColumns       = "hilbert_trendline;hilbert_cycle;hilbert_amplitude;hilbert_period";
input int    In_AutoReloadSec      = 0;                   // Recarregar a cada N segundos (0=off)
input int    In_MaxSeries          = 8;                   // Máx. de séries (1..8)
input bool   In_InvertBars         = false;               // true: inverte índice das barras
// Mapeamento de barras
input bool   In_RequireExactBar    = false;               // true: exige barra exata; false: barra <= dt mais próxima
// Debug
input bool   In_Debug              = true;                // Loga mapeamentos (primeiros 20) e estatísticas
input bool   In_DebugDumpEmpty     = false;               // true: imprime dump mesmo se todos os valores estiverem EMPTY
input int    In_DebugMaxDump       = 10;                  // número máximo de linhas de dump por chamada (<=0 desliga)

// Séries computadas (A*ColA + B*ColB + C)
input bool   In_Comp1_Use          = false;
input string In_Comp1_Name         = "comp1";
input string In_Comp1_ColA         = "";
input double In_Comp1_A            = 1.0;
input string In_Comp1_ColB         = "";
input double In_Comp1_B            = 0.0;
input double In_Comp1_C            = 0.0;

input bool   In_Comp2_Use          = false;
input string In_Comp2_Name         = "comp2";
input string In_Comp2_ColA         = "";
input double In_Comp2_A            = 1.0;
input string In_Comp2_ColB         = "";
input double In_Comp2_B            = 0.0;
input double In_Comp2_C            = 0.0;

//---- buffers
double Buf0[],Buf1[],Buf2[],Buf3[],Buf4[],Buf5[],Buf6[],Buf7[];
string PlotNames[8];
int    UsedPlots = 0;
bool   NeedReload = true;
int    LastRatesTotal = 0;
int    BufferBars = 0;
datetime LatestBarTime = 0;
datetime OldestBarTime = 0;
datetime CsvEarliestTime = 0;
datetime CsvLatestTime = 0;
datetime LoadLatestBarAtLastLoad = 0;

string HeaderNames[];
ushort Sep = ',';

//---- cores padrão
color DEF_COLORS[8] = { clrDodgerBlue, clrOrangeRed, clrSeaGreen, clrDarkViolet,
                        clrSienna,     clrTeal,      clrCrimson,  clrGoldenrod };

//-------------------- helpers --------------------
string TrimAll(string s){ StringTrimLeft(s); StringTrimRight(s); return s; }
string Unquote(const string s){
   int n=(int)StringLen(s);
   if(n>=2 && StringGetCharacter(s,0)=='"' && StringGetCharacter(s,n-1)=='"')
      return StringSubstr(s,1,n-2);
   return s;
}
string BoolToString(const bool value){ return value ? "true" : "false"; }
string RemoveBOM(string s){
   if(StringLen(s)>0 && StringGetCharacter(s,0)==0xFEFF) return StringSubstr(s,1);
   return s;
}
bool IsDigits(const string s){
   int n=(int)StringLen(s);
   if(n<=0) return false;
   for(int i=0;i<n;i++){ ushort ch = StringGetCharacter(s,i); if(ch<'0' || ch>'9') return false; }
   return true;
}
int ToIntSafe(const string s, int def=-1){ return (IsDigits(s)? (int)StringToInteger(s) : def); }

int ResolveColumn(const string token)
{
   string t = TrimAll(token);
   StringToLower(t);
   if(t=="") return -1;
   int idx = ToIntSafe(t, -1);
   if(idx>=0) return idx;
   for(int i=0;i<ArraySize(HeaderNames);i++)
   {
      string h = TrimAll(HeaderNames[i]);
      StringToLower(h);
      if(h==t) return i;
   }
   return -1;
}

bool ParseNumber(const string s, double &out)
{
   string t = TrimAll(s);
   t = Unquote(t);
   if(t==""){ out=EMPTY_VALUE; return false; }
   out = StringToDouble(t);
   if(MathIsValidNumber(out)) return true;
   string u=t; StringReplace(u, ",", "."); out = StringToDouble(u);
   return MathIsValidNumber(out);
}

bool ParseDateTimeText(string s, datetime &dt)
{
   string t = TrimAll(Unquote(s));
   if(t==""){ return false; }
   bool allDigits = true;
   for(int i=0;i<(int)StringLen(t);i++){ ushort ch=StringGetCharacter(t,i); if(ch<'0'||ch>'9'){ allDigits=false; break; } }
   if(allDigits){
      long v = (long)StringToInteger(t);
      long threshold = 1000000000000; if(v>threshold) v/=1000;
      dt = (datetime)v; return true;
   }
   StringReplace(t, "T", " "); StringReplace(t, "-", "."); StringReplace(t, "/", ".");
   dt = StringToTime(t);
   return (dt>0);
}

ushort ParseSep(const string s){
   if(StringLen(s)==0) return ',';
   if(s=="\\t" || s=="\t") return (ushort)9; // TAB
   return (ushort)StringGetCharacter(s,0);
}

int SplitList(const string s, string &out[]){ string tmp=s; StringReplace(tmp, ",", ";"); return StringSplit(tmp, ';', out); }

void ClearAllBuffers(){
   int bars = MathMax(LastRatesTotal, Bars(_Symbol, _Period));
   if(bars <= 0) bars = 1;

   ArrayResize(Buf0, bars); ArrayResize(Buf1, bars);
   ArrayResize(Buf2, bars); ArrayResize(Buf3, bars);
   ArrayResize(Buf4, bars); ArrayResize(Buf5, bars);
   ArrayResize(Buf6, bars); ArrayResize(Buf7, bars);

   ArrayInitialize(Buf0, EMPTY_VALUE); ArrayInitialize(Buf1, EMPTY_VALUE);
   ArrayInitialize(Buf2, EMPTY_VALUE); ArrayInitialize(Buf3, EMPTY_VALUE);
   ArrayInitialize(Buf4, EMPTY_VALUE); ArrayInitialize(Buf5, EMPTY_VALUE);
   ArrayInitialize(Buf6, EMPTY_VALUE); ArrayInitialize(Buf7, EMPTY_VALUE);

   BufferBars = bars;
}

void EnsureBufferCapacity(const int required)
{
   if(required <= BufferBars)
      return;

   int oldSize = BufferBars;
   int newSize = required;

   ArrayResize(Buf0, newSize);
   ArrayResize(Buf1, newSize);
   ArrayResize(Buf2, newSize);
   ArrayResize(Buf3, newSize);
   ArrayResize(Buf4, newSize);
   ArrayResize(Buf5, newSize);
   ArrayResize(Buf6, newSize);
   ArrayResize(Buf7, newSize);

   for(int i=oldSize; i<newSize; i++)
   {
      Buf0[i] = EMPTY_VALUE;
      Buf1[i] = EMPTY_VALUE;
      Buf2[i] = EMPTY_VALUE;
      Buf3[i] = EMPTY_VALUE;
      Buf4[i] = EMPTY_VALUE;
      Buf5[i] = EMPTY_VALUE;
      Buf6[i] = EMPTY_VALUE;
      Buf7[i] = EMPTY_VALUE;
   }

   BufferBars = newSize;
}

void SetupPlots()
{
   UsedPlots = MathMin(MathMax(In_MaxSeries,1), 8);

   SetIndexBuffer(0, Buf0, INDICATOR_DATA); ArraySetAsSeries(Buf0, true);
   SetIndexBuffer(1, Buf1, INDICATOR_DATA); ArraySetAsSeries(Buf1, true);
   SetIndexBuffer(2, Buf2, INDICATOR_DATA); ArraySetAsSeries(Buf2, true);
   SetIndexBuffer(3, Buf3, INDICATOR_DATA); ArraySetAsSeries(Buf3, true);
   SetIndexBuffer(4, Buf4, INDICATOR_DATA); ArraySetAsSeries(Buf4, true);
   SetIndexBuffer(5, Buf5, INDICATOR_DATA); ArraySetAsSeries(Buf5, true);
   SetIndexBuffer(6, Buf6, INDICATOR_DATA); ArraySetAsSeries(Buf6, true);
   SetIndexBuffer(7, Buf7, INDICATOR_DATA); ArraySetAsSeries(Buf7, true);

   for(int i=0;i<8;i++)
   {
      PlotIndexSetInteger(i, PLOT_DRAW_TYPE, (i<UsedPlots)?DRAW_LINE:DRAW_NONE);
      PlotIndexSetInteger(i, PLOT_LINE_WIDTH, 1);
      PlotIndexSetInteger(i, PLOT_LINE_STYLE, STYLE_SOLID);
      PlotIndexSetInteger(i, PLOT_LINE_COLOR, DEF_COLORS[i%8]);
      string lbl = (i<UsedPlots && PlotNames[i]!="")?PlotNames[i]:("Series"+(string)(i+1));
      PlotIndexSetString(i, PLOT_LABEL, lbl);
   }
}

void SetBufValue(const int idx, const int bar, const double value){
   int target = bar;
   if(In_InvertBars && BufferBars>0)
   {
      target = BufferBars-1-bar;
      if(target<0 || target>=BufferBars)
         return;
   }

   if(target<0)
      return;

   switch(idx){
      case 0: if(target<(int)ArraySize(Buf0)) Buf0[target]=value; break;
      case 1: if(target<(int)ArraySize(Buf1)) Buf1[target]=value; break;
      case 2: if(target<(int)ArraySize(Buf2)) Buf2[target]=value; break;
      case 3: if(target<(int)ArraySize(Buf3)) Buf3[target]=value; break;
      case 4: if(target<(int)ArraySize(Buf4)) Buf4[target]=value; break;
      case 5: if(target<(int)ArraySize(Buf5)) Buf5[target]=value; break;
      case 6: if(target<(int)ArraySize(Buf6)) Buf6[target]=value; break;
      case 7: if(target<(int)ArraySize(Buf7)) Buf7[target]=value; break;
      default: break;
   }
}

double GetBufValue(const int idx, const int bar)
{
   int source = bar;
   if(In_InvertBars && BufferBars>0)
      source = BufferBars-1-bar;

   if(source<0)
      return EMPTY_VALUE;

   switch(idx){
      case 0: return (source<(int)ArraySize(Buf0)) ? Buf0[source] : EMPTY_VALUE;
      case 1: return (source<(int)ArraySize(Buf1)) ? Buf1[source] : EMPTY_VALUE;
      case 2: return (source<(int)ArraySize(Buf2)) ? Buf2[source] : EMPTY_VALUE;
      case 3: return (source<(int)ArraySize(Buf3)) ? Buf3[source] : EMPTY_VALUE;
      case 4: return (source<(int)ArraySize(Buf4)) ? Buf4[source] : EMPTY_VALUE;
      case 5: return (source<(int)ArraySize(Buf5)) ? Buf5[source] : EMPTY_VALUE;
      case 6: return (source<(int)ArraySize(Buf6)) ? Buf6[source] : EMPTY_VALUE;
      case 7: return (source<(int)ArraySize(Buf7)) ? Buf7[source] : EMPTY_VALUE;
      default: return EMPTY_VALUE;
   }
}

//-------------------- loader --------------------
bool LoadCSVToBuffers()
{
   ClearAllBuffers();
   for(int i=0;i<8;i++) PlotNames[i]="";

   int flags = FILE_READ | FILE_BIN;
   if(In_CommonFiles) flags |= FILE_COMMON;
   int h = FileOpen(In_FileName, flags);
   if(h==INVALID_HANDLE){ Print("CSV_Reader_Plot_v3_1: não consegui abrir: ", In_FileName, " (err ", GetLastError(), ")"); return false; }

   int sz = (int)FileSize(h);
   uchar data[]; ArrayResize(data, sz);
   int readed = (int)FileReadArray(h, data, 0, sz);
   FileClose(h);
   if(readed<=0){ Print("CSV_Reader_Plot_v3_1: arquivo vazio."); return false; }

   string txt = CharArrayToString(data, 0, readed);
   txt = RemoveBOM(txt);
   StringReplace(txt, "\r\n", "\n");
   StringReplace(txt, "\r", "\n");
   Sep = ParseSep(In_Separator);

   string lines[];
   int nlines = StringSplit(txt, '\n', lines);
   if(nlines<=0){ Print("CSV_Reader_Plot_v3_1: sem linhas."); return false; }

   int startLine = 0;
   ArrayFree(HeaderNames);

   // header
   if(In_HasHeader && nlines>0)
   {
      string hdr = RemoveBOM(Unquote(lines[0]));
      string fields[];
      StringSplit(hdr, Sep, fields);
      int nf = ArraySize(fields);
      if(nf>0)
      {
         ArrayResize(HeaderNames, nf);
         for(int i=0;i<nf;i++) HeaderNames[i] = TrimAll(Unquote(fields[i]));
         startLine = 1;
         if(In_Debug){
            string joined="";
            for(int i=0;i<nf;i++){ if(i>0) joined += "|"; joined += HeaderNames[i]; }
            Print("CSV v3.1 header [", nf, "]: ", joined);
         }
      }
   }

   // resolve time columns
   int timeCol = -1, dateCol=-1, clockCol=-1;
   if(StringLen(In_TimeColumn)>0) timeCol = ResolveColumn(In_TimeColumn);
   else { dateCol = ResolveColumn(In_TimeDateColumn); clockCol = ResolveColumn(In_TimeTimeColumn); }

   // resolve value columns
   string vcTokens[];
   int nvc = SplitList(In_ValueColumns, vcTokens);
   int valCols[8]; ArrayInitialize(valCols, -1);
   int used = 0;
   for(int i=0;i<nvc && used<8;i++)
   {
      int idx = ResolveColumn(TrimAll(vcTokens[i]));
      if(idx>=0){ valCols[used++] = idx; }
   }

   int comp_start = used;
   if(In_Comp1_Use && used<8) { valCols[used++] = -100; PlotNames[comp_start] = In_Comp1_Name; }
   if(In_Comp2_Use && used<8) { valCols[used++] = -200; PlotNames[comp_start + (In_Comp1_Use?1:0)] = In_Comp2_Name; }
   UsedPlots = MathMin(used, In_MaxSeries);

   int p=0;
   for(int i=0;i<used && p<UsedPlots;i++)
   {
      if(valCols[i]>=0)
      {
         string nm = (In_HasHeader && valCols[i] < ArraySize(HeaderNames)) ? HeaderNames[valCols[i]] : ("C"+(string)valCols[i]);
         PlotNames[p++] = nm;
      }
      else { p++; }
   }

   SetupPlots();

   int colA1=-1,colB1=-1,colA2=-1,colB2=-1;
   if(In_Comp1_Use){ colA1 = ResolveColumn(In_Comp1_ColA); colB1 = ResolveColumn(In_Comp1_ColB); }
   if(In_Comp2_Use){ colA2 = ResolveColumn(In_Comp2_ColA); colB2 = ResolveColumn(In_Comp2_ColB); }

   int ok=0, miss_time=0, miss_bar=0, miss_num=0, miss_future=0, miss_past=0;

   CsvEarliestTime = 0;
   CsvLatestTime   = 0;
   int dbg_shown=0;

   for(int li=startLine; li<nlines; li++)
   {
      string line = TrimAll(lines[li]);
      if(line=="") continue;
      line = Unquote(line);
      string fields[];
      int nf = StringSplit(line, Sep, fields);
      if(nf<=0) continue;

      datetime dt = 0;
      bool okTime=false;
      if(timeCol>=0 && timeCol < nf)
      {
         okTime = ParseDateTimeText(fields[timeCol], dt);
      }
      else if(dateCol>=0 && clockCol>=0 && dateCol<nf && clockCol<nf)
      {
         string dttext = TrimAll(Unquote(fields[dateCol])) + " " + TrimAll(Unquote(fields[clockCol]));
         okTime = ParseDateTimeText(dttext, dt);
      }

      if(!okTime){ miss_time++; continue; }
      dt += In_TZ_AdjustMin*60;

      if(CsvEarliestTime==0 || dt<CsvEarliestTime) CsvEarliestTime = dt;
      if(CsvLatestTime==0  || dt>CsvLatestTime)   CsvLatestTime   = dt;

      int bar = iBarShift(_Symbol, _Period, dt, In_RequireExactBar);
      if(bar<0)
      {
         if(LatestBarTime>0 && dt>LatestBarTime)      miss_future++;
         else if(OldestBarTime>0 && dt<OldestBarTime) miss_past++;
         else                                        miss_bar++;
         continue;
      }

      int outPlot = 0;
      for(int i=0;i<used && outPlot<UsedPlots;i++)
      {
         if(valCols[i]>=0)
         {
            int c = valCols[i];
            double v = EMPTY_VALUE;
            bool okVal = (c<nf && ParseNumber(fields[c], v));
            SetBufValue(outPlot, bar, okVal ? v : EMPTY_VALUE);
            if(!okVal) miss_num++;
         }
         else if(valCols[i]==-100) // comp1
         {
            double a=0,b=0; bool okA=false, okB=false;
            if(colA1>=0 && colA1<nf) okA = ParseNumber(fields[colA1], a);
            if(colB1>=0 && colB1<nf) okB = ParseNumber(fields[colB1], b);
            double res = (okA?In_Comp1_A*a:0.0) + (okB?In_Comp1_B*b:0.0) + In_Comp1_C;
            SetBufValue(outPlot, bar, res);
         }
         else if(valCols[i]==-200) // comp2
         {
            double a=0,b=0; bool okA=false, okB=false;
            if(colA2>=0 && colA2<nf) okA = ParseNumber(fields[colA2], a);
            if(colB2>=0 && colB2<nf) okB = ParseNumber(fields[colB2], b);
            double res = (okA?In_Comp2_A*a:0.0) + (okB?In_Comp2_B*b:0.0) + In_Comp2_C;
            SetBufValue(outPlot, bar, res);
         }
         outPlot++;
      }

      ok++;

      if(In_Debug && dbg_shown<20){
         PrintFormat("CSV v3.1 map[%d]: dt=%s -> bar=%d, nf=%d", li, TimeToString(dt, TIME_DATE|TIME_MINUTES|TIME_SECONDS), bar, nf);
         dbg_shown++;
      }
   }

   if(In_Debug){
      PrintFormat("CSV v3.1 stats: ok=%d, miss_time=%d, miss_bar=%d, miss_num=%d, miss_future=%d, miss_past=%d, UsedPlots=%d",
                  ok, miss_time, miss_bar, miss_num, miss_future, miss_past, UsedPlots);
      PrintFormat("CSV v3.1 range: csv=%s -> %s | chart=%s -> %s",
                  (CsvEarliestTime>0 ? TimeToString(CsvEarliestTime, TIME_DATE|TIME_SECONDS) : "n/a"),
                  (CsvLatestTime>0   ? TimeToString(CsvLatestTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (LatestBarTime>0   ? TimeToString(LatestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (OldestBarTime>0   ? TimeToString(OldestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"));
   }

   return (ok>0);
}

//-------------------- events --------------------
int OnInit()
{
   SetupPlots();
   if(In_AutoReloadSec>0) EventSetTimer(In_AutoReloadSec);
   NeedReload = true;
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(In_AutoReloadSec>0) EventKillTimer();
}

void OnTimer()
{
   if(In_AutoReloadSec>0){ NeedReload = true; ChartRedraw(); }
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   int bars_available = Bars(_Symbol, _Period);
   LastRatesTotal = MathMax(rates_total, bars_available);

   if(LastRatesTotal <= 0)
      return(prev_calculated);

   if(rates_total>0)
   {
      OldestBarTime = time[0];
      LatestBarTime = time[rates_total-1];
   }
   else
   {
      LatestBarTime = 0;
      OldestBarTime = 0;
   }

   EnsureBufferCapacity(rates_total);

   bool reloaded = false;
   if(NeedReload)
   {
      if(LoadCSVToBuffers())
      {
         Print("CSV_Reader_Plot_v3_1: arquivo carregado: ", In_FileName);
         NeedReload = false;
         reloaded = true;
         LoadLatestBarAtLastLoad = LatestBarTime;
      }
      else
      {
         Print("CSV_Reader_Plot_v3_1: carregou mas não mapeou nenhum ponto; verifique debug.");
      }
   }

   if(!NeedReload && CsvEarliestTime>0 && LatestBarTime>LoadLatestBarAtLastLoad && LatestBarTime>=CsvEarliestTime)
   {
      PrintFormat("CSV v3.1 ranges: csv=%s -> %s | chart=%s -> %s",
                  (CsvEarliestTime>0 ? TimeToString(CsvEarliestTime, TIME_DATE|TIME_SECONDS) : "n/a"),
                  (CsvLatestTime>0   ? TimeToString(CsvLatestTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (LatestBarTime>0   ? TimeToString(LatestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (OldestBarTime>0   ? TimeToString(OldestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"));
      PrintFormat("CSV v3.1 notice: novo histórico alcança o CSV (chart_max=%s). Recarregando...",
                  TimeToString(LatestBarTime, TIME_DATE|TIME_SECONDS));
      LastRatesTotal = rates_total;
      NeedReload = true;
      return(rates_total);
   }

   if(In_Debug)
   {
      int start = prev_calculated;
      if(start>0) start--;
      if(start<0) start=0;

      PrintFormat("CSV v3.1 OnCalc: rates_total=%d prev_calculated=%d start=%d BufferBars=%d NeedReload=%s",
                  rates_total,
                  prev_calculated,
                  start,
                  BufferBars,
                  BoolToString(NeedReload));
      PrintFormat("CSV v3.1 ranges: csv=%s -> %s | chart=%s -> %s",
                  (CsvEarliestTime>0 ? TimeToString(CsvEarliestTime, TIME_DATE|TIME_SECONDS) : "n/a"),
                  (CsvLatestTime>0   ? TimeToString(CsvLatestTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (LatestBarTime>0   ? TimeToString(LatestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"),
                  (OldestBarTime>0   ? TimeToString(OldestBarTime,   TIME_DATE|TIME_SECONDS) : "n/a"));

      int dumps = 0;
      for(int bar=start; bar<rates_total; bar++)
      {
         if(In_DebugMaxDump>0 && dumps>=In_DebugMaxDump)
            break;

         string msg = StringFormat("bar=%d", bar);
         if(ArraySize(time)>bar)
            msg += StringFormat(" time=%s", TimeToString(time[bar], TIME_DATE|TIME_SECONDS));

         bool hasValue = false;
         for(int plot=0; plot<UsedPlots; plot++)
         {
            string label = (PlotNames[plot] != "") ? PlotNames[plot] : ("Series" + (string)(plot+1));
            double val = GetBufValue(plot, bar);
            if(val==EMPTY_VALUE)
               msg += StringFormat(" | %s=EMPTY", label);
            else
            {
               msg += StringFormat(" | %s=%.6f", label, val);
               hasValue = true;
            }
         }

         if(hasValue || In_DebugDumpEmpty)
         {
            Print("CSV v3.1 dump: ", msg);
            dumps++;
         }
      }
   }
   return(rates_total);
}
//+------------------------------------------------------------------+
