import zipfile

from app.eval.artifacts import VisualEvidence, collect_visual_evidence, extract_document_text
from app.eval.prompts import individual_messages


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_docx(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>实验结论：图表显示准确率提升。</w:t></w:r></w:p></w:body></w:document>""",
        )
        archive.writestr("word/media/chart.png", _PNG)


def _simple_pdf(text: str) -> bytes:
    stream = f"BT /F1 14 Tf 72 720 Td ({text}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    body += b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:])
    return body + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")


def test_docx_text_and_embedded_chart_are_available(tmp_path):
    report = tmp_path / "report.docx"
    _write_docx(report)

    assert "准确率提升" in extract_document_text(report)
    images = collect_visual_evidence(tmp_path)
    assert len(images) == 1
    assert images[0].mime_type == "image/png"


def test_pdf_text_is_extracted_when_pdf_support_is_installed(tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(_simple_pdf("PDF report conclusion"))

    assert "PDF report conclusion" in extract_document_text(report)
    images = collect_visual_evidence(tmp_path)
    assert len(images) == 1
    assert images[0].mime_type == "image/png"


def test_visual_report_evidence_is_sent_as_kimi_multimodal_content():
    messages = individual_messages(
        "报告正文",
        {},
        [],
        visual_evidence=[VisualEvidence("报告图 1", "image/png", _PNG)],
    )

    content = messages[-1]["content"]
    assert isinstance(content, list)
    assert any(part["type"] == "image_url" for part in content)
    assert any("报告图表证据" in part.get("text", "") for part in content)
