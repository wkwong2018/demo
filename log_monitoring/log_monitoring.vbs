' Configuration
Const LogDir = "H:/Exotics Logs"
Const CheckInterval = 600000  ' 10 minutes in milliseconds
Const TimeThreshold = 20 * 60 ' 20 minutes in seconds
Const AlertLogFile = LogDir & "\monitoring_alerts.log"
Const ErrorLogFile = LogDir & "\error_log.txt"

' Function to check if within operating hours (8 AM - 8 PM HKT)
Function IsWithinOperatingHours()
    Dim nowTime
    nowTime = Hour(Now) * 3600 + Minute(Now) * 60 + Second(Now)
    IsWithinOperatingHours = (nowTime >= 8 * 3600 And nowTime <= 20 * 3600)
End Function

' Function to extract timestamp and PIDs from file
Function GetFileDetails(filePath)
    Dim fso, file, fileName, startTime, processIds, hasKeyword, content, regEx, matches
    
    Set fso = CreateObject("Scripting.FileSystemObject")
    fileName = fso.GetFileName(filePath)
    Set file = fso.GetFile(filePath)
    startTime = 0
    processIds = Array()
    hasKeyword = False

    WScript.Echo "Processing file: " & fileName
    
    ' Extract date and timestamp (e.g., ...cli.2025-07-09.08.53.18.log)
    Set regEx = New RegExp
    regEx.Pattern = ".*CLI.*(\d{4}-\d{2}-\d{2})\.(\d{2})\.(\d{2})\.(\d{2})\.log"
    regEx.IgnoreCase = True
    regEx.Global = False
    If regEx.Test(fileName) Then
        Set matches = regEx.Execute(fileName)
        Dim dateParts, year, month, day, hour, minute, second
        dateParts = Split(matches(0).SubMatches(0), "-")
        year = CInt(dateParts(0))
        month = CInt(dateParts(1))
        day = CInt(dateParts(2))
        hour = CInt(matches(0).SubMatches(1))
        minute = CInt(matches(0).SubMatches(2))
        second = CInt(matches(0).SubMatches(3))
        startTime = DateSerial(year, month, day) + TimeSerial(hour, minute, second)
        WScript.Echo "Extracted start time from " & fileName & ": " & startTime
    Else
        WScript.Echo "No valid date/time format with 'CLI' before date in " & fileName
    End If

    ' Read file content and extract PIDs/keywords
    If Not file Is Nothing Then
        Set content = fso.OpenTextFile(filePath, 1, False)
        Dim fileContent
        fileContent = content.ReadAll
        content.Close

        ' Check for keywords
        If InStr(1, fileContent, "Complete Success", vbTextCompare) > 0 Or InStr(1, fileContent, "Complete Failure", vbTextCompare) > 0 Then
            hasKeyword = True
            If hasKeyword Then
                WScript.Echo "Keyword found in " & fileName & ": Complete Success or Failure"
            End If
        End If

        ' Extract PIDs
        regEx.Pattern = "Process id:\s*\[(\d+)\]"
        If regEx.Test(fileContent) Then
            Set matches = regEx.Execute(fileContent)
            Dim i
            ReDim processIds(matches.Count - 1)
            For i = 0 To matches.Count - 1
                processIds(i) = matches(i).SubMatches(0)
            Next
            WScript.Echo "Extracted ProcessIDs from " & fileName & ": " & Join(processIds, ", ")
        End If
    Else
        WScript.Echo "File " & filePath & " not found or inaccessible"
    End If

    Set GetFileDetails = Array(startTime, processIds, hasKeyword)
End Function

' Function to kill process
Function KillProcessById(processId)
    Dim shell, proc
    On Error Resume Next
    Set shell = CreateObject("WScript.Shell")
    shell.Run "taskkill /PID " & processId & " /F", 0, True
    If Err.Number = 0 Then
        WScript.Echo "Terminated process with PID " & processId
        KillProcessById = True
    Else
        WScript.Echo "Process with PID " & processId & " not found or invalid"
        KillProcessById = False
    End If
    On Error GoTo 0
End Function

' Function to write alert to log file
Sub WriteAlertLog(fileName, processId)
    Dim fso, alertFile
    Set fso = CreateObject("Scripting.FileSystemObject")
    On Error Resume Next
    Set alertFile = fso.OpenTextFile(AlertLogFile, 8, True)
    alertFile.WriteLine Now & " - Auto-killed job with PID " & processId & " in log file " & fileName & " due to runtime exceeding 20 minutes."
    alertFile.Close
    If Err.Number = 0 Then
        WScript.Echo "Alert logged to " & AlertLogFile & " for PID " & processId
    Else
        WScript.Echo "Error writing alert log: " & Err.Description
        Set alertFile = fso.OpenTextFile(ErrorLogFile, 8, True)
        alertFile.WriteLine Now & " - Error in WriteAlertLog: " & Err.Description
        alertFile.Close
    End If
    On Error GoTo 0
End Sub

' Main monitoring loop
Dim fso, folder, files, file, details, startTime, processIds, hasKeyword, nowTime, elapsedSeconds, i
Set fso = CreateObject("Scripting.FileSystemObject")
today = Year(Now) & "-" & Right("0" & Month(Now), 2) & "-" & Right("0" & Day(Now), 2)

Do While True
    If IsWithinOperatingHours Then
        Set folder = fso.GetFolder(LogDir)
        Set files = folder.Files
        WScript.Echo "Matched files: "
        For Each file In files
            If InStr(1, file.Name, "CLI") > 0 And InStr(1, file.Name, today) > 0 And InStr(1, file.Name, ".log") > 0 Then
                WScript.Echo "  " & file.Name
                details = GetFileDetails(file.Path)
                If Not IsEmpty(details) Then
                    startTime = details(0)
                    processIds = details(1)
                    hasKeyword = details(2)

                    If Not IsNull(startTime) And startTime > 0 Then
                        nowTime = Now
                        elapsedSeconds = DateDiff("s", startTime, nowTime)
                        WScript.Echo "File " & file.Name & " started at " & startTime & ", elapsed: " & elapsedSeconds & " seconds"

                        If elapsedSeconds > TimeThreshold And Not hasKeyword Then
                            For i = 0 To UBound(processIds)
                                If KillProcessById(processIds(i)) Then
                                    WriteAlertLog file.Name, processIds(i)
                                End If
                            Next
                        End If
                    Else
                        WScript.Echo "No valid start time or keyword present in " & file.Name
                    End If
                End If
            End If
        Next
    Else
        WScript.Echo "Outside operating hours (8 AM - 8 PM), waiting. Current time: " & Now
    End If
    WScript.Sleep CheckInterval
Loop