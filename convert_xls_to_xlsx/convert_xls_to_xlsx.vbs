Option Explicit
Dim objFSO, objExcel, objWorkbook, strFilePath, strFileExt, strNewFilePath
Dim strFolderPath, strFileName

' Set the file path to your input Excel file
strFilePath = "C:\YourFolder\YourFile.xls" ' Change this to your file path

' Create FileSystemObject to handle file operations
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the file extension
strFileExt = LCase(objFSO.GetExtensionName(strFilePath))

' Extract folder path and file name without extension
strFolderPath = objFSO.GetParentFolderName(strFilePath)
strFileName = objFSO.GetBaseName(strFilePath)

' Check if the file is already in .xlsx format
If strFileExt = "xlsx" Then
    WScript.Echo "File is already in .xlsx format. No conversion needed."
ElseIf strFileExt = "xls" Then
    ' Create Excel application
    Set objExcel = CreateObject("Excel.Application")
    objExcel.Visible = False ' Hide Excel window
    objExcel.DisplayAlerts = False ' Suppress alerts

    ' Open the .xls file
    Set objWorkbook = objExcel.Workbooks.Open(strFilePath)

    ' Define the new file path for .xlsx
    strNewFilePath = strFolderPath & "\" & strFileName & ".xlsx"

    ' Save as .xlsx (FileFormat 51 corresponds to .xlsx)
    objWorkbook.SaveAs strNewFilePath, 51

    ' Close the workbook and quit Excel
    objWorkbook.Close
    objExcel.Quit

    ' Clean up objects
    Set objWorkbook = Nothing
    Set objExcel = Nothing

    WScript.Echo "File converted from .xls to .xlsx: " & strNewFilePath

    ' Optionally, delete the original .xls file
    ' objFSO.DeleteFile strFilePath
Else
    WScript.Echo "Unsupported file format: " & strFileExt
End If

' Clean up FileSystemObject
Set objFSO = Nothing