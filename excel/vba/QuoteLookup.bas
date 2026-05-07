' QuoteLookup.bas - MSM 협가표 단가 조회 매크로
' 사용법: Excel에서 사양 입력 후 Ctrl+Shift+L 또는 버튼 클릭
'
' Column Layout:
'   B: BODY TYPE (GATE, GLOBE, SW-CHECK, Y-STRAINER)
'   C: RATING (10K, 20K, 150#, 300#)
'   D: SIZE (50A, 80A, 100A, ...)
'   E: END CONNECTION (FLGD RF)
'   F: DISCOUNT RATE (0.40, 0.45, ...)
'   G: UNIT PRICE ← auto-filled
'   H: STATUS ← auto-filled

Sub LookupPrice()

    Dim ws As Worksheet
    Set ws = ActiveSheet
    Dim r As Long
    r = ActiveCell.Row

    ' Read input cells
    Dim body    As String: body    = Trim(ws.Cells(r, 2).Value)
    Dim rating  As String: rating  = Trim(ws.Cells(r, 3).Value)
    Dim sz      As String: sz      = Trim(ws.Cells(r, 4).Value)
    Dim endconn As String: endconn = Trim(ws.Cells(r, 5).Value)
    Dim disc    As String: disc    = Trim(ws.Cells(r, 6).Value)

    ' Default values
    If endconn = "" Then endconn = "FLGD RF"
    If disc = "" Then disc = "0.40"

    ' Build JSON payload
    Dim payload As String
    payload = "{" & _
        Chr(34) & "body_type" & Chr(34) & ":" & Chr(34) & body & Chr(34) & "," & _
        Chr(34) & "rating" & Chr(34) & ":" & Chr(34) & rating & Chr(34) & "," & _
        Chr(34) & "size" & Chr(34) & ":" & Chr(34) & sz & Chr(34) & "," & _
        Chr(34) & "end_connection" & Chr(34) & ":" & Chr(34) & endconn & Chr(34) & "," & _
        Chr(34) & "discount_rate" & Chr(34) & ":" & disc & _
    "}"

    ' HTTP POST to FastAPI server
    Dim http As Object
    Set http = CreateObject("MSXML2.XMLHTTP")

    On Error GoTo ServerError
    http.Open "POST", "http://localhost:8000/quote/lookup", False
    http.setRequestHeader "Content-Type", "application/json"
    http.Send payload
    On Error GoTo 0

    ' Parse response
    Dim unitPrice As String: unitPrice = ExtractJson(http.responseText, "unit_price")
    Dim status    As String: status    = ExtractJson(http.responseText, "status")
    Dim msg       As String: msg       = ExtractJson(http.responseText, "message")

    ' Write results
    If unitPrice <> "" And unitPrice <> "null" Then
        ws.Cells(r, 7).Value = CLng(unitPrice)
        ws.Cells(r, 7).NumberFormat = "#,##0"
    Else
        ws.Cells(r, 7).Value = ""
    End If
    ws.Cells(r, 8).Value = status

    ' Color-code status
    Select Case status
        Case "FOUND":             ws.Cells(r, 8).Interior.Color = RGB(198, 239, 206)
        Case "NEEDS_MAKER_QUOTE": ws.Cells(r, 8).Interior.Color = RGB(255, 235, 156)
        Case "MISSING_INFO":      ws.Cells(r, 8).Interior.Color = RGB(255, 199, 206)
        Case "NOT_FOUND":         ws.Cells(r, 8).Interior.Color = RGB(255, 199, 206)
    End Select

    Exit Sub

ServerError:
    ws.Cells(r, 7).Value = ""
    ws.Cells(r, 8).Value = "SERVER_ERROR"
    ws.Cells(r, 8).Interior.Color = RGB(255, 199, 206)
    MsgBox "서버 연결 실패. localhost:8000 이 실행 중인지 확인하세요.", vbExclamation

End Sub


Sub LookupAll()
    ' Lookup all rows with data (from row 3 down)
    Dim ws As Worksheet
    Set ws = ActiveSheet
    Dim r As Long
    r = 3
    Do While Trim(ws.Cells(r, 2).Value) <> ""
        ws.Cells(r, 2).Select
        LookupPrice
        r = r + 1
    Loop
    MsgBox "조회 완료: " & (r - 3) & "건", vbInformation
End Sub


Function ExtractJson(jsonStr As String, key As String) As String
    Dim pattern As String
    pattern = Chr(34) & key & Chr(34) & ":"
    Dim pos As Long
    pos = InStr(jsonStr, pattern)
    If pos = 0 Then ExtractJson = "": Exit Function
    pos = pos + Len(pattern)
    Do While Mid(jsonStr, pos, 1) = " ": pos = pos + 1: Loop
    If Mid(jsonStr, pos, 1) = Chr(34) Then
        pos = pos + 1
        Dim endPos As Long
        endPos = InStr(pos, jsonStr, Chr(34))
        ExtractJson = Mid(jsonStr, pos, endPos - pos)
    ElseIf Mid(jsonStr, pos, 4) = "null" Then
        ExtractJson = ""
    Else
        endPos = pos
        Do While Mid(jsonStr, endPos, 1) <> "," And Mid(jsonStr, endPos, 1) <> "}"
            endPos = endPos + 1
        Loop
        ExtractJson = Mid(jsonStr, pos, endPos - pos)
    End If
End Function
