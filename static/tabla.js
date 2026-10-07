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

  const celda = (tr, i) => tr.cells[i].textContent.trim();

  function filtrar() {
    const q = buscar.value.toLowerCase();
    let visibles = 0;
    filas.forEach(tr => {
      const ok =
        (!q || tr.textContent.toLowerCase().includes(q)) &&
        (!fClase.value || celda(tr, 4).startsWith(fClase.value)) &&
        (!fEstado.value || celda(tr, 6) === fEstado.value) &&
        (!fResp.value || celda(tr, 7).startsWith(fResp.value));
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
      filas.sort((a, b) =>
        celda(a, i).localeCompare(celda(b, i), "es", { numeric: true, sensitivity: "base" }) * (asc ? 1 : -1));
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
