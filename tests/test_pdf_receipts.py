"""Synthetic PDF fixtures only; no private invoices."""
import base64
import io
import unittest
from unittest.mock import patch
from PIL import Image
import receipts


def pdf_bytes(pages=2):
    images=[Image.new('RGB',(600,800),'red' if i%2==0 else 'blue') for i in range(pages)]
    out=io.BytesIO()
    images[0].save(out,format='PDF',save_all=True,append_images=images[1:])
    for image in images: image.close()
    return out.getvalue()


def encoded(raw):
    return base64.b64encode(raw).decode('ascii')


class PdfReceiptTests(unittest.TestCase):
    def test_all_pages_archived_readably_as_standard_jpeg(self):
        jpeg=receipts.prepare_jpeg(encoded(pdf_bytes()))
        self.assertLessEqual(len(jpeg),4_000_000)
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.format,'JPEG')
            self.assertEqual(image.width,1600)
            self.assertGreater(image.height,4000)
            red=image.getpixel((800,100));blue=image.getpixel((800,image.height-100))
            self.assertGreater(red[0],red[2]+100)
            self.assertGreater(blue[2],blue[0]+100)

    def test_no_silent_truncation_and_invalid_pdf_rejected(self):
        with self.assertRaisesRegex(ValueError,'1 bis 5'):
            receipts.prepare_jpeg(encoded(pdf_bytes(6)))
        with self.assertRaisesRegex(ValueError,'PDF nicht lesbar'):
            receipts.prepare_jpeg(encoded(b'%PDF-broken'))

    def test_password_protected_document_is_rejected(self):
        from pathlib import Path
        raw=(Path(__file__).parent/'fixtures/protected-receipt.pdf').read_bytes()
        with self.assertRaisesRegex(ValueError,'PDF nicht lesbar'):
            receipts.prepare_jpeg(encoded(raw))

    def test_ocr_reads_each_page_in_order_without_downscaling_whole_document(self):
        with patch('receipts.subprocess.run') as process:
            process.return_value.returncode=0
            process.return_value.stdout='Synthetic page'
            result=receipts.recognize_text(encoded(pdf_bytes()))
            self.assertEqual(process.call_count,2)
            self.assertEqual(result,'Synthetic page\n\nSynthetic page')

class PdfReceiptHttpTests(unittest.TestCase):
    def test_save_reopen_reject_invalid_replacement_and_backup_restore(self):
        import tempfile
        from pathlib import Path
        import app as ledger
        from server import create_app
        previous=ledger.DB
        with tempfile.TemporaryDirectory() as folder:
            try:
                ledger.DB=Path(folder)/'expenses.sqlite3'
                web=create_app(password='pdf-test-password-only',public_url='')
                client=web.test_client()
                csrf=client.post('/api/login',json={'password':'pdf-test-password-only'},headers={'Origin':'http://localhost'}).json['csrf']
                headers={'Origin':'http://localhost','X-CSRF-Token':csrf}
                data=dict(merchant='Synthetic PDF',date='2026-11-01',amount='30',category='Shopping',receipt_image=encoded(pdf_bytes()))
                response=client.post('/api/transaction',json=data,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
                txid=response.json['id'];url=f'/api/receipt/{txid}'
                saved=client.get(url)
                self.assertEqual(saved.content_type,'image/jpeg')
                with Image.open(io.BytesIO(saved.data)) as image:
                    self.assertGreater(image.height,4000)
                self.assertEqual(web.test_client().get(url).status_code,401)
                self.assertEqual(client.get(url+'?dataset=demo').status_code,404)
                for raw in [b'%PDF-invalid',pdf_bytes(6)]:
                    data.update(id=txid,amount='999',receipt_image=encoded(raw))
                    self.assertEqual(client.post('/api/transaction',json=data,headers=headers).status_code,400)
                    self.assertEqual(client.get(url).data,saved.data)
                    self.assertEqual(client.get('/api/data').json['transactions'][0]['amount'],3000)
                with client.get('/api/backup') as backup:
                    archive=backup.data
                self.assertEqual(client.post('/api/delete',json={'id':txid},headers=headers).status_code,200)
                restore=client.post('/api/backup-restore',data=archive,headers={**headers,'Content-Type':'application/zip','X-Backup-Confirm':'private'})
                self.assertEqual(restore.status_code,200,restore.text)
                self.assertEqual(client.get(url).data,saved.data)
            finally:
                ledger.DB=previous
