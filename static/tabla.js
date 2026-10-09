(function () {
  const tabla = document.getElementById("tabla");
  if (!tabla) return;
  const cuerpo = tabla.tBodies[0];
  const filas = Array.from(cuerpo.rows);
  const buscar = document.getElementById("buscar");
  const fEstado = document.getElementById("filtro-estado");
  const fClase = document.getElementById("filtro-clase");
  const fResp = document.getElementById("filtro-resp");
  const contador = document.getElementById("contador");

  const cols = Array.from(tabla.tHead.querySelectorAll("th"));
  const idx = nombre => cols.findIndex(th => th.dataset.col === nombre);
  // valor "limpio" de una celda: las celdas con barra lo traen en data-valor
  const celda = (tr, i) => (tr.cells[i].dataset.valor ?? tr.cells[i].textContent).trim();
  const textoFila = tr => Array.from(tr.cells, (_, i) => celda(tr, i)).join(" ").toLowerCase();

  function filtrar() {
    const q = buscar.value.toLowerCase();
    let visibles = 0;
    filas.forEach(tr => {
      const ok =
        (!q || textoFila(tr).includes(q)) &&
        (!fClase.value || celda(tr, idx("clase")).startsWith(fClase.value)) &&
        (!fEstado.value || celda(tr, idx("estado")) === fEstado.value) &&
        (!fResp.value || celda(tr, idx("resp")).startsWith(fResp.value));
      tr.hidden = !ok;
      if (ok) visibles++;
    });
    contador.textContent = `${visibles} de ${filas.length}`;
  }

  tabla.tHead.querySelectorAll("th").forEach((th, i) => {
    th.addEventListener("click", () => {
      const asc = th.dataset.orden !== "asc";
      tabla.tHead.querySelectorAll("th").forEach(o => delete o.dataset.orden);
      th.dataset.orden = asc ? "asc" : "desc";
      // el estado se ordena por su posición en el proceso, no alfabéticamente
      const clave = (tr) => tr.cells[i].dataset.orden ?? celda(tr, i);
      filas.sort((a, b) =>
        String(clave(a)).localeCompare(String(clave(b)), "es", { numeric: true, sensitivity: "base" }) * (asc ? 1 : -1));
      filas.forEach(tr => cuerpo.appendChild(tr));
    });
  });

  cuerpo.addEventListener("click", e => {
    const tr = e.target.closest("tr");
    if (tr) location.href = tr.dataset.href;
  });

  [buscar, fClase, fEstado, fResp].forEach(el => el.addEventListener("input", filtrar));
  filtrar();
})();
