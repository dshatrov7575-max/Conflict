Unicode true
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetDatablockOptimize on
SetDateSave off
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "payload.nsh"
Name "Conflict — демонстрационная версия MVP7 R1"
OutFile "${OUTPUT_EXE}"
InstallDir "$LOCALAPPDATA\Programs\ConflictPartnerDemo\MVP7"
ShowInstDetails show
ShowUninstDetails show
BrandingText "Тестовый кандидат. Проверка Windows 11 + WSL2 ещё не выполнена."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"
Var Pwsh
Var VerifyOnly
Var PayloadOut
Function .onInit
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ConflictPartnerDemo\MVP7"
  StrCpy $VerifyOnly "0"
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/VERIFYONLY" $1
  IfErrors +2
  StrCpy $VerifyOnly "1"
  ClearErrors
  ${GetOptions} $0 "/PAYLOADOUT=" $PayloadOut
  SearchPath $Pwsh "pwsh.exe"
  StrCmp $Pwsh "" 0 +2
  StrCpy $Pwsh "$PROGRAMFILES64\PowerShell\7\pwsh.exe"
  IfFileExists "$Pwsh" +4
  MessageBox MB_ICONSTOP "Требуется установленный PowerShell 7. Установщик не устанавливает дополнительные компоненты." /SD IDOK
  SetErrorLevel 1
  Quit
FunctionEnd
Section "Установка"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=inner.zip "${INNER_ZIP}"
  File "Mvp7.Setup.psm1"
  File "Install-Mvp7.ps1"
  File "Launch-Mvp7.ps1"
  File "Uninstall-Mvp7.ps1"
  StrCmp $VerifyOnly "1" 0 install
  nsExec::ExecToStack '"$Pwsh" -NoLogo -NoProfile -NonInteractive -File "$PLUGINSDIR\Install-Mvp7.ps1" -Zip "$PLUGINSDIR\inner.zip" -Sha256 ${INNER_SHA256} -Bytes ${INNER_BYTES} -VerifyOnly'
  Pop $0
  Pop $1
  StrCmp $0 "0" 0 failed
  StrCmp $PayloadOut "" verified
  CopyFiles /SILENT "$PLUGINSDIR\inner.zip" "$PayloadOut"
  IfErrors failed
verified:
  SetErrorLevel 0
  Quit
install:
  nsExec::ExecToStack '"$Pwsh" -NoLogo -NoProfile -NonInteractive -File "$PLUGINSDIR\Install-Mvp7.ps1" -Zip "$PLUGINSDIR\inner.zip" -Sha256 ${INNER_SHA256} -Bytes ${INNER_BYTES}'
  Pop $0
  Pop $1
  StrCmp $0 "0" 0 failed
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Conflict MVP7"
  CreateShortCut "$SMPROGRAMS\Conflict MVP7\Запустить.lnk" "$Pwsh" '-NoLogo -NoProfile -File "$INSTDIR\installer\Launch-Mvp7.ps1" -Action Start'
  CreateShortCut "$SMPROGRAMS\Conflict MVP7\Остановить.lnk" "$Pwsh" '-NoLogo -NoProfile -File "$INSTDIR\installer\Launch-Mvp7.ps1" -Action Stop'
  CreateShortCut "$SMPROGRAMS\Conflict MVP7\Диагностика.lnk" "$Pwsh" '-NoLogo -NoProfile -File "$INSTDIR\installer\Launch-Mvp7.ps1" -Action Diagnostics'
  CreateShortCut "$SMPROGRAMS\Conflict MVP7\Удалить.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConflictPartnerDemoMVP7" "DisplayName" "Conflict MVP7 R1 — тестовый кандидат"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConflictPartnerDemoMVP7" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConflictPartnerDemoMVP7" "InstallLocation" "$INSTDIR"
  Goto done
failed:
  MessageBox MB_ICONSTOP "Установка остановлена. Проверьте Windows 11 x64, рабочую WSL2, PowerShell 7, Edge и целостность файла. Политики компьютера не изменялись." /SD IDOK
  SetErrorLevel 1
  Quit
done:
SectionEnd
Function un.onInit
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ConflictPartnerDemo\MVP7"
  SearchPath $Pwsh "pwsh.exe"
  StrCmp $Pwsh "" 0 +2
  StrCpy $Pwsh "$PROGRAMFILES64\PowerShell\7\pwsh.exe"
FunctionEnd
Section "Uninstall"
  nsExec::ExecToStack '"$Pwsh" -NoLogo -NoProfile -NonInteractive -File "$INSTDIR\installer\Uninstall-Mvp7.ps1"'
  Pop $0
  Pop $1
  StrCmp $0 "0" 0 unfailed
  Delete "$SMPROGRAMS\Conflict MVP7\Запустить.lnk"
  Delete "$SMPROGRAMS\Conflict MVP7\Остановить.lnk"
  Delete "$SMPROGRAMS\Conflict MVP7\Диагностика.lnk"
  Delete "$SMPROGRAMS\Conflict MVP7\Удалить.lnk"
  RMDir "$SMPROGRAMS\Conflict MVP7"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ConflictPartnerDemoMVP7"
  Goto unend
unfailed:
  MessageBox MB_ICONSTOP "Удаление остановлено. Закройте программу и проверьте доступность её среды. Состояние и резервные копии сохранены." /SD IDOK
  SetErrorLevel 1
unend:
SectionEnd
