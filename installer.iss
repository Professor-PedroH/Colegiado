; Script do Inno Setup (https://jrsoftware.org/isinfo.php) - gera Instalador_ColegiadoDemandas.exe
[Setup]
AppName=Colegiado - Controle de Demandas
AppVersion=1.0
DefaultDirName={autopf}\ColegiadoDemandas
DefaultGroupName=Colegiado - Controle de Demandas
OutputDir=installer
OutputBaseFilename=Instalador_ColegiadoDemandas
SetupIconFile=assets\icon.ico
Compression=lzma
SolidCompression=yes
[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Files]
Source: "dist\ColegiadoDemandas\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\Colegiado - Demandas"; Filename: "{app}\ColegiadoDemandas.exe"
Name: "{autodesktop}\Colegiado - Demandas"; Filename: "{app}\ColegiadoDemandas.exe"
[Run]
Filename: "{app}\ColegiadoDemandas.exe"; Description: "Abrir o programa"; Flags: nowait postinstall skipifsilent
