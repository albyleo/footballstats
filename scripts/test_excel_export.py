"""Excel format, value preservation and HTTP validation checks."""
import sys
from pathlib import Path
from io import BytesIO
import unittest
from zipfile import ZipFile
from xml.etree import ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from excel_export import workbook
from starlette.testclient import TestClient
from webapp import app


class ExcelTests(unittest.TestCase):
    def test_types_missing_values_and_literal_formula_names(self):
        data = [['Nome', 'Gol', 'Media', 'Assenti'], ['=1+1 & Città', 0, 1.25, None]]
        with ZipFile(BytesIO(workbook(data))) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        self.assertEqual(root.find('.//s:c[@r="A2"]', ns).get('t'), 'inlineStr')
        self.assertEqual(root.find('.//s:c[@r="A2"]//s:t', ns).text, '=1+1 & Città')
        self.assertEqual(root.find('.//s:c[@r="B2"]/s:v', ns).text, '0')
        self.assertEqual(root.find('.//s:c[@r="C2"]/s:v', ns).text, '1.25')
        self.assertIsNone(root.find('.//s:c[@r="D2"]', ns))
        self.assertEqual(root.findall('.//s:f', ns), [])

    def test_all_rows_and_download_response(self):
        with TestClient(app) as client:
            response = client.post('/api/export.xlsx', json=[['Gol']] + [[n] for n in range(65)])
            self.assertEqual(response.status_code, 200)
            self.assertIn('spreadsheetml.sheet', response.headers['content-type'])
            with ZipFile(BytesIO(response.content)) as archive:
                root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(len(root.findall('.//{*}row')), 66)
            for bad in [[], {'rows': []}, [[{}]], [['a'] * 81]]:
                self.assertEqual(client.post('/api/export.xlsx', json=bad).status_code, 400)


if __name__ == '__main__':
    unittest.main()
