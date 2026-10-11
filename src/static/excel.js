// Export the current table snapshot; no data-feed or database request is needed.
window.exportTable = async function(button, table, filename) {
  if (!table || !table.tBodies[0]?.rows.length) return;
  const original = button.textContent;
  button.disabled = true; button.textContent = 'Esportazione…';
  try {
    const columns = [...table.tHead.rows[0].cells];
    const dataRows = [...table.tBodies[0].rows];
    const notes = columns.map((_, i) => dataRows.some(row => row.cells[i]?.querySelector('small')));
    const rows = [columns.flatMap((cell, i) => notes[i] ? [cell.textContent, cell.textContent + ' / note e copertura'] : [cell.textContent])];
    for (const row of dataRows) rows.push([...row.cells].flatMap((cell, i) => {
      const clone = cell.cloneNode(true); clone.querySelectorAll('small').forEach(el => el.remove());
      const value = cell.dataset.excel !== undefined ? JSON.parse(cell.dataset.excel) : clone.textContent;
      return notes[i] ? [value, cell.querySelector('small')?.textContent ?? null] : [value];
    }));
    const response = await fetch('/api/export.xlsx', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(rows)});
    if (!response.ok) throw new Error('Esportazione non riuscita. Riprova.');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = url;
    link.download = filename + '.xlsx'; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; button.textContent = original; }
};
