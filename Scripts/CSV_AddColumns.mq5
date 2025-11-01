//+------------------------------------------------------------------+
//|                                                   CSV_AddColumns |
//| Lê um CSV de entrada e grava um novo CSV acrescentando até       |
//| duas colunas computadas (A*ColA + B*ColB + C).                   |
//| Use para "materializar" colunas extras sem mexer no arquivo base.|
//+------------------------------------------------------------------+
#property strict

#include <Arrays\ArrayString.mqh>

input string In_InFileName     = "data.csv";            // CSV origem (em MQL5\Files)
input string In_OutFileName    = "data_with_cols.csv";  // CSV destino
input bool   In_CommonFiles    = false;                 // Usar Common Files?
input string In_Separator      = ",";                   // Separador (1o caractere)
input bool   In_HasHeader      = true;                  // Primeira linha é header?

// Coluna computada 1
input bool   In_Comp1_Use      = true;
input string In_Comp1_Name     = "comp1";
input string In_Comp1_ColA     = "1";
input double In_Comp1_A        = 1.0;
input string In_Comp1_ColB     = "";
input double In_Comp1_B        = 0.0;
input double In_Comp1_C        = 0.0;

// Coluna computada 2
input bool   In_Comp2_Use      = false;
input string In_Comp2_Name     = "comp2";
input string In_Comp2_ColA     = "2";
input double In_Comp2_A        = 1.0;
input string In_Comp2_ColB     = "";
input double In_Comp2_B        = 0.0;
input double In_Comp2_C        = 0.0;

string Header[];
ushort Sep=',';

string TrimAll(const string s){ string r=s; StringTrimLeft(r); StringTrimRight(r); return r; }
bool IsDigits(const string s){ int n=(int)StringLen(s); if(n<=0) return false; for(int i=0;i<n;i++){ ushort ch=StringGetCharacter(s,i); if(ch<'0'||ch>'9') return false; } return true; }
int ToIntSafe(const string s, int def=-1){ return (IsDigits(s)? (int)StringToInteger(s) : def); }

int ResolveColumn(const string token)
{
   string t = StringToLower(TrimAll(token));
   if(t=="") return -1;
   int idx = ToIntSafe(t, -1);
   if(idx>=0) return idx;
   for(int i=0;i<ArraySize(Header);i++)
   {
      string h = StringToLower(TrimAll(Header[i]));
      if(h==t) return i;
   }
   return -1;
}

bool ParseNumber(const string s, double &out)
{
   string t = TrimAll(s);
   if(t==""){ out=0.0; return false; }
   out = StringToDouble(t);
   if(MathIsValidNumber(out)) return true;
   string u=t; StringReplace(u, ",", ".");
   out = StringToDouble(u);
   return MathIsValidNumber(out);
}

void WriteLine(int h, string &fields[], int nf)
{
   for(int i=0;i<nf;i++)
   {
      if(i>0) FileWriteString(h, string(Sep));
      FileWriteString(h, fields[i]);
   }
   FileWriteString(h, "\r\n");
}

void OnStart()
{
   Sep = (ushort)StringGetCharacter(In_Separator,0);
   int flagsIn = FILE_READ | FILE_BIN;
   if(In_CommonFiles) flagsIn|=FILE_COMMON;
   int hi = FileOpen(In_InFileName, flagsIn);
   if(hi==INVALID_HANDLE){ Print("CSV_AddColumns: não consegui abrir origem: ", In_InFileName, " err=", GetLastError()); return; }

   int sz=(int)FileSize(hi);
   uchar bytes[]; ArrayResize(bytes, sz);
   int rd=(int)FileReadArray(hi, bytes, 0, sz);
   FileClose(hi);
   if(rd<=0){ Print("CSV_AddColumns: arquivo vazio."); return; }

   string txt = CharArrayToString(bytes, 0, rd);
   StringReplace(txt, "\r\n", "\n");
   StringReplace(txt, "\r", "\n");

   string lines[]; int nlines = StringSplit(txt, '\n', lines);
   if(nlines<=0){ Print("CSV_AddColumns: sem linhas."); return; }

   int flagsOut = FILE_WRITE | FILE_BIN | FILE_REWRITE;
   if(In_CommonFiles) flagsOut|=FILE_COMMON;
   int ho = FileOpen(In_OutFileName, flagsOut);
   if(ho==INVALID_HANDLE){ Print("CSV_AddColumns: não consegui abrir destino: ", In_OutFileName, " err=", GetLastError()); return; }

   int startLine=0;
   if(In_HasHeader)
   {
      string hdr = lines[0];
      string f[]; int nf=StringSplit(hdr, Sep, f);
      if(nf>0)
      {
         ArrayResize(Header, nf);
         for(int i=0;i<nf;i++) Header[i]=TrimAll(f[i]);
         // adiciona nomes das novas colunas
         if(In_Comp1_Use){ nf++; ArrayResize(f, nf); f[nf-1]=In_Comp1_Name; }
         if(In_Comp2_Use){ nf++; ArrayResize(f, nf); f[nf-1]=In_Comp2_Name; }
         WriteLine(ho, f, nf);
         startLine=1;
      }
   }

   int a1=-1,b1=-1,a2=-1,b2=-1;
   if(In_Comp1_Use){ a1=ResolveColumn(In_Comp1_ColA); b1=ResolveColumn(In_Comp1_ColB); }
   if(In_Comp2_Use){ a2=ResolveColumn(In_Comp2_ColA); b2=ResolveColumn(In_Comp2_ColB); }

   for(int li=startLine; li<nlines; li++)
   {
      string line = TrimAll(lines[li]);
      if(line=="") continue;
      string f[]; int nf=StringSplit(line, Sep, f);
      if(nf<=0) continue;

      if(In_Comp1_Use)
      {
         double va=0,vb=0; bool oka=false, okb=false;
         if(a1>=0 && a1<nf) oka = ParseNumber(f[a1], va);
         if(b1>=0 && b1<nf) okb = ParseNumber(f[b1], vb);
         double res = (oka?In_Comp1_A*va:0.0) + (okb?In_Comp1_B*vb:0.0) + In_Comp1_C;
         nf++; ArrayResize(f, nf); f[nf-1] = DoubleToString(res, 8);
      }
      if(In_Comp2_Use)
      {
         double va=0,vb=0; bool oka=false, okb=false;
         if(a2>=0 && a2<nf) oka = ParseNumber(f[a2], va);
         if(b2>=0 && b2<nf) okb = ParseNumber(f[b2], vb);
         double res = (oka?In_Comp2_A*va:0.0) + (okb?In_Comp2_B*vb:0.0) + In_Comp2_C;
         nf++; ArrayResize(f, nf); f[nf-1] = DoubleToString(res, 8);
      }
      WriteLine(ho, f, nf);
   }

   FileClose(ho);
   Print("CSV_AddColumns: escrito arquivo: ", In_OutFileName);
}
//+------------------------------------------------------------------+
