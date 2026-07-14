import { jsPDF } from 'jspdf';

export function downloadTextAsPdf(text: string, filename: string, title?: string) {
  const doc = new jsPDF({ unit: 'pt', format: 'letter' });
  const margin = 48;
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const maxWidth = pageWidth - margin * 2;
  let y = margin;

  if (title) {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(14);
    doc.text(title, margin, y);
    y += 24;
  }

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(11);
  const lines = doc.splitTextToSize(text || '', maxWidth) as string[];

  for (const line of lines) {
    if (y > pageHeight - margin) {
      doc.addPage();
      y = margin;
    }
    doc.text(line, margin, y);
    y += 14;
  }

  doc.save(filename.endsWith('.pdf') ? filename : `${filename}.pdf`);
}
