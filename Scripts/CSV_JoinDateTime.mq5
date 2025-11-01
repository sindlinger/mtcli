//+------------------------------------------------------------------+
//|                                         CSV_JoinDateTime.mq5     |
//| Lê CSV e grava outro com uma coluna "datetime" gerada a partir   |
//| de duas colunas separadas (ex.: <DATE> e <TIME>).                 |
//+------------------------------------------------------------------+
#property strict

input string In_InFileName     = "data.csv";              // Origem (MQL5\Files ou Common)
input string In_OutFileName    = "data_datetime.csv";     // Destino
input bool   In_CommonFiles    = false;                   // Usar Common Files?
input string In_Separator      = "\\t";                   // ",", ";", "|" ou "\t" para TAB
input bool   In_HasHeader      = true;
input string In_DateCol        = "<DATE>";
input string In_TimeCol        = "<TIME>";
input string In_OutColName     = "datetime";
input bool   In_InsertAsFirst  = true;                    // Inserir coluna no início? (senão, adiciona no fim)

string Header[];
ushort Sep=',';

string TrimAll(const string s){ string r=s; StringTrimLeft(r); StringTrimRight(r); return r; }
string Unquote(const string s){
   int n=(int)StringLen(s);
   if(n>=2 && StringGetCharacter(s,0)=='"' && StringGetCharacter(s,n-1)=='"')
      return StringSubstr(s,1,n-2);
   return s;
}
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

ushort ParseSep(const string s){
   if(StringLen(s)==0) return ',';
   if(s=="\\t" || s=="\t") return 9;
   return (ushort)StringGetCharacter(s,0);
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
   Sep = ParseSep(In_Separator);

   int flagsIn = FILE_READ | FILE_BIN;
   if(In_CommonFiles) flagsIn|=FILE_COMMON;
   int hi = FileOpen(In_InFileName, flagsIn);
   if(hi==INVALID_HANDLE){ Print("CSV_JoinDateTime: não consegui abrir origem: ", In_InFileName, " err=", GetLastError()); return; }

   int sz=(int)FileSize(hi);
   uchar bytes[]; ArrayResize(bytes, sz);
   int rd=(int)FileReadArray(hi, bytes, 0, sz);
   FileClose(hi);
   if(rd<=0){ Print("CSV_JoinDateTime: arquivo vazio."); return; }

   string txt = CharArrayToString(bytes, 0, rd);
   StringReplace(txt, "\r\n", "\n");
   StringReplace(txt, "\r", "\n");

   string lines[]; int nlines = StringSplit(txt, '\n', lines);
   if(nlines<=0){ Print("CSV_JoinDateTime: sem linhas."); return; }

   int flagsOut = FILE_WRITE | FILE_BIN | FILE_REWRITE;
   if(In_CommonFiles) flagsOut|=FILE_COMMON;
   int ho = FileOpen(In_OutFileName, flagsOut);
   if(ho==INVALID_HANDLE){ Print("CSV_JoinDateTime: não consegui abrir destino: ", In_OutFileName, " err=", GetLastError()); return; }

   int startLine=0;
   int dcol=-1, tcol=-1;

   if(In_HasHeader)
   {
      string hdr = Unquote(lines[0]);
      string f[]; int nf=StringSplit(hdr, Sep, f);
      for(int i=0;i<nf;i++) f[i]=TrimAll(Unquote(f[i]));
      if(nf>0)
      {
         ArrayResize(Header, nf);
         for(int i=0;i<nf;i++) Header[i]=f[i];
         dcol = ResolveColumn(In_DateCol);
         tcol = ResolveColumn(In_TimeCol);
         // escreve header com nova coluna
         if(In_InsertAsFirst){
            nf++; ArrayResize(f, nf);
            // shift right
            for(int j=nf-1;j>0;j--) f[j]=f[j-1];
            f[0]=In_OutColName;
         }else{
            nf++; ArrayResize(f, nf);
            f[nf-1]=In_OutColName;
         }
         WriteLine(ho, f, nf);
         startLine=1;
      }
   }

   if(dcol<0 || tcol<0){ // tentar resolver por índice
      dcol = ToIntSafe(In_DateCol, dcol);
      tcol = ToIntSafe(In_TimeCol, tcol);
   }

   for(int li=startLine; li<nlines; li++)
   {
      string line = TrimAll(lines[li]);
      if(line=="") continue;
      line = Unquote(line);
      string f[]; int nf=StringSplit(line, Sep, f);
      if(nf<=0) continue;
      for(int i=0;i<nf;i++) f[i]=TrimAll(Unquote(f[i]));

      string dttext = "";
      if(dcol>=0 && dcol<nf && tcol>=0 && tcol<nf)
         dttext = f[dcol] + " " + f[tcol];

      if(In_InsertAsFirst){
         nf++; ArrayResize(f, nf);
         for(int j=nf-1;j>0;j--) f[j]=f[j-1];
         f[0]=dttext;
      }else{
         nf++; ArrayResize(f, nf);
         f[nf-1]=dttext;
      }

      WriteLine(ho, f, nf);
   }

   FileClose(ho);
   Print("CSV_JoinDateTime: escrito arquivo: ", In_OutFileName);
}
//+------------------------------------------------------------------+
