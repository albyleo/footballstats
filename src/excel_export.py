"""Small, dependency-free XLSX export of already displayed data."""
from io import BytesIO
import math
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED


def workbook(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 10000:
        raise ValueError('Tabella vuota o troppo grande.')
    if any(not isinstance(r, list) or len(r) > 80 for r in rows):
        raise ValueError('Colonne non valide.')
    if sum(map(len, rows)) > 200000:
        raise ValueError('Troppe celle.')
    def column(n):
        name = ''
        while n:
            n, rem = divmod(n - 1, 26)
            name = chr(65 + rem) + name
        return name
    body = []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, value in enumerate(row, 1):
            ref = f'{column(j)}{i}'
            style = ' s="1"' if i == 1 else ''
            if value is None:
                continue
            if type(value) in (int, float) and math.isfinite(value):
                cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
            elif isinstance(value, str) and len(value) <= 32767:
                # Explicit strings: names beginning with = are never formulas.
                clean = ''.join(c for c in value if c in '\t\n\r' or 32 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(clean)}</t></is></c>')
            else:
                raise ValueError('Valore della cella non valido.')
        body.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    office = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    end = f'{column(max(map(len, rows)) or 1)}{len(rows)}'
    files = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' + ''.join(f'<Override PartName="/xl/{path}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.{kind}+xml"/>' for path, kind in [('workbook','sheet.main'),('worksheets/sheet1','worksheet'),('styles','styles')]) + '</Types>',
        '_rels/.rels': f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{office}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{ns}" xmlns:r="{office}"><sheets><sheet name="Dati" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{office}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{office}/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFB8F36A"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF111510"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{ns}"><dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="80" width="23" customWidth="1"/></cols><sheetData>{"".join(body)}</sheetData><autoFilter ref="A1:{end}"/></worksheet>',
    }
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path, xml in files.items():
            archive.writestr(path, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml)
    return output.getvalue()


async def export_excel(request):
    from starlette.responses import Response, JSONResponse
    from starlette.concurrency import run_in_threadpool
    import json
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4_000_000:
            return JSONResponse({'error': 'Tabella troppo grande.'}, status_code=413)
    try:
        rows = json.loads(body)
        content = await run_in_threadpool(workbook, rows)
    except (ValueError, TypeError):
        return JSONResponse({'error': 'Dati di esportazione non validi.'}, status_code=400)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="mycombo.xlsx"', 'Cache-Control': 'no-store'})
