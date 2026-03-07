from __future__ import annotations

from datetime import datetime


def _fmt_dt(value: datetime | None) -> str:
    return value.isoformat(sep=' ', timespec='seconds') if value else '-'


def _escape_pdf_text(value: str) -> str:
    return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def render_invoice_pdf_bytes(*, invoice_id: str, provider_invoice_id: str | None, username: str | None, email: str | None, amount_paid: float, currency: str, status: str, paid_at: datetime | None, period_start: datetime | None, period_end: datetime | None, hosted_invoice_url: str | None = None) -> bytes:
    lines = [
        'Parlay Bot Invoice',
        f'Invoice ID: {invoice_id}',
        f'Provider Invoice ID: {provider_invoice_id or "-"}',
        f'Customer: {username or "-"}',
        f'Email: {email or "-"}',
        f'Status: {status}',
        f'Amount Paid: {amount_paid:.2f} {currency.upper()}',
        f'Paid At: {_fmt_dt(paid_at)}',
        f'Period Start: {_fmt_dt(period_start)}',
        f'Period End: {_fmt_dt(period_end)}',
        f'Hosted Invoice URL: {hosted_invoice_url or "-"}',
        f'Generated: {_fmt_dt(datetime.utcnow())}',
    ]
    content_lines = ['BT', '/F1 12 Tf', '50 760 Td']
    first = True
    for line in lines:
        if not first:
            content_lines.append('0 -18 Td')
        first = False
        content_lines.append(f'({_escape_pdf_text(line)}) Tj')
    content_lines.append('ET')
    stream = '\n'.join(content_lines).encode('latin-1', errors='replace')

    objects = []
    def add_obj(body: bytes):
        objects.append(body)

    add_obj(b'<< /Type /Catalog /Pages 2 0 R >>')
    add_obj(b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>')
    add_obj(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>')
    add_obj(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    add_obj(f'<< /Length {len(stream)} >>\nstream\n'.encode('latin-1') + stream + b'\nendstream')

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{idx} 0 obj\n'.encode('latin-1'))
        pdf.extend(body)
        pdf.extend(b'\nendobj\n')
    xref_pos = len(pdf)
    pdf.extend(f'xref\n0 {len(objects)+1}\n'.encode('latin-1'))
    pdf.extend(b'0000000000 65535 f \n')
    for off in offsets[1:]:
        pdf.extend(f'{off:010d} 00000 n \n'.encode('latin-1'))
    pdf.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF'.encode('latin-1'))
    return bytes(pdf)
