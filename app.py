import os
import sqlite3
import uuid
from datetime import date, timedelta

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("GESTOR_DB", os.path.join(BASE_DIR, "solicitudes.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
CLASES = ["Presencial", "Híbrido", "Remoto"]
ETAPAS = ["Enviada", "En proceso", "Entrevista", "Oferta"]   # las que forman la barra de progreso
ESTADOS = ETAPAS + ["Rechazada", "Ignorada"]                # Rechazada e Ignorada detienen el proceso
DIAS_PARA_IGNORAR = 14

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-local")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db, open(os.path.join(BASE_DIR, "schema.sql")) as f:
        tenia_historial = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'historial_estados'").fetchone()
        db.executescript(f.read())
        # migración para bases de datos creadas antes de añadir estos campos
        cols = {r[1] for r in db.execute("PRAGMA table_info(solicitudes)")}
        if "clase" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN clase TEXT NOT NULL DEFAULT 'Presencial'")
        if "localizacion" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN localizacion TEXT")
        if "dias_presenciales" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN dias_presenciales INTEGER")
        if "estado_fecha" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN estado_fecha TEXT")
        # sin histórico, la mejor aproximación es la fecha de envío
        db.execute("UPDATE solicitudes SET estado_fecha = fecha_envio WHERE estado_fecha IS NULL")
        # el estado 'Sin respuesta' desapareció: su función la cumple 'Ignorada'
        db.execute("UPDATE solicitudes SET estado = 'Ignorada' WHERE estado = 'Sin respuesta'")
        if not tenia_historial:
            # sin histórico real: toda solicitud empezó en 'Enviada' y el estado actual es el último conocido
            db.execute("""INSERT INTO historial_estados (solicitud_id, estado, fecha)
                          SELECT id, 'Enviada', fecha_envio FROM solicitudes""")
            db.execute("""INSERT INTO historial_estados (solicitud_id, estado, fecha)
                          SELECT id, estado, estado_fecha FROM solicitudes WHERE estado != 'Enviada'""")


def form_solicitud():
    f = request.form
    clase = f.get("clase") if f.get("clase") in CLASES else "Presencial"
    try:
        dias = max(1, min(5, int(f.get("dias_presenciales", ""))))
    except ValueError:
        dias = None
    return {
        "empresa": f.get("empresa", "").strip(),
        "puesto": f.get("puesto", "").strip(),
        "fecha_envio": f.get("fecha_envio") or date.today().isoformat(),
        "canal": f.get("canal", "").strip(),
        "enlace": f.get("enlace", "").strip(),
        "clase": clase,
        "localizacion": f.get("localizacion", "").strip() if clase != "Remoto" else "",
        "dias_presenciales": dias if clase == "Híbrido" else None,
        "estado": f.get("estado") if f.get("estado") in ESTADOS else "Enviada",
        "notas": f.get("notas", "").strip(),
    }


def get_or_404(sid):
    row = get_db().execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    if row is None:
        abort(404)
    return row


def borrar_archivo(nombre):
    if nombre:
        try:
            os.remove(os.path.join(UPLOAD_DIR, nombre))
        except FileNotFoundError:
            pass


def registrar_estado(sid, estado, fecha):
    get_db().execute("INSERT INTO historial_estados (solicitud_id, estado, fecha) VALUES (?, ?, ?)",
                     (sid, estado, fecha))


def fechas_de_estados(sid=None):
    """{solicitud_id: {estado: fecha}}; si un estado se alcanzó varias veces, vale la última."""
    sql = "SELECT solicitud_id, estado, fecha FROM historial_estados"
    args = ()
    if sid is not None:
        sql, args = sql + " WHERE solicitud_id = ?", (sid,)
    fechas = {}
    for r in get_db().execute(sql + " ORDER BY id", args):
        fechas.setdefault(r["solicitud_id"], {})[r["estado"]] = r["fecha"]
    return fechas


@app.template_global()
def barra_proceso(s, fechas):
    """Datos para dibujar la barra: progreso por etapas, o barra llena si el proceso está parado/terminado."""
    fechas = fechas or {}
    if s["estado"] not in ETAPAS:
        return {"fin": s["estado"], "fecha": fechas.get(s["estado"]) or s["estado_fecha"]}
    actual = ETAPAS.index(s["estado"])
    return {"etapas": [
        {"nombre": e, "fecha": fechas.get(e) if i <= actual else None,
         "situacion": "actual" if i == actual else "hecha" if i < actual else "pendiente"}
        for i, e in enumerate(ETAPAS)]}


@app.template_filter("corta")
def fecha_corta(iso):
    """2026-10-09 -> 09/10/26"""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%y")
    except (TypeError, ValueError):
        return ""


@app.before_request
def marcar_ignoradas():
    """Las solicitudes que llevan 14 días o más en 'Enviada' pasan a 'Ignorada'."""
    if request.endpoint == "static":
        return
    limite = (date.today() - timedelta(days=DIAS_PARA_IGNORAR)).isoformat()
    db = get_db()
    vencidas = db.execute(
        "SELECT id, estado_fecha FROM solicitudes WHERE estado = 'Enviada' AND estado_fecha <= ?",
        (limite,)).fetchall()
    for r in vencidas:
        # la fecha del cambio es el día en que se cumplió el plazo, no el de la comprobación
        cuando = (date.fromisoformat(r["estado_fecha"]) + timedelta(days=DIAS_PARA_IGNORAR)).isoformat()
        db.execute("UPDATE solicitudes SET estado = 'Ignorada', estado_fecha = ? WHERE id = ?", (cuando, r["id"]))
        registrar_estado(r["id"], "Ignorada", cuando)
    if vencidas:
        db.commit()


@app.route("/")
def index():
    filas = get_db().execute("SELECT * FROM solicitudes ORDER BY fecha_envio DESC, id DESC").fetchall()
    return render_template("index.html", filas=filas, estados=ESTADOS, clases=CLASES,
                           fechas=fechas_de_estados())


@app.route("/nueva", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        d = form_solicitud()
        # una solicitud nueva 'Enviada' lleva en ese estado desde su fecha de envío
        d["estado_fecha"] = d["fecha_envio"] if d["estado"] == "Enviada" else date.today().isoformat()
        if not d["empresa"] or not d["puesto"]:
            flash("Empresa y puesto son obligatorios.", "error")
            return render_template("nueva.html", estados=ESTADOS, clases=CLASES, s=d), 400
        cur = get_db().execute(
            """INSERT INTO solicitudes (empresa, puesto, fecha_envio, canal, enlace, clase, localizacion,
                  dias_presenciales, estado, estado_fecha, notas)
               VALUES (:empresa, :puesto, :fecha_envio, :canal, :enlace, :clase, :localizacion,
                  :dias_presenciales, :estado, :estado_fecha, :notas)""", d)
        registrar_estado(cur.lastrowid, "Enviada", d["fecha_envio"])
        if d["estado"] != "Enviada":
            registrar_estado(cur.lastrowid, d["estado"], d["estado_fecha"])
        get_db().commit()
        flash("Solicitud añadida.", "ok")
        return redirect(url_for("detalle", sid=cur.lastrowid))
    return render_template("nueva.html", estados=ESTADOS, clases=CLASES,
                           s={"fecha_envio": date.today().isoformat(), "estado": "Enviada"})


@app.route("/solicitud/<int:sid>")
def detalle(sid):
    return render_template("detalle.html", s=get_or_404(sid), estados=ESTADOS, clases=CLASES,
                           fechas=fechas_de_estados(sid).get(sid))


@app.post("/solicitud/<int:sid>/editar")
def editar(sid):
    actual = get_or_404(sid)
    d = form_solicitud()
    d["estado_fecha"] = actual["estado_fecha"] if d["estado"] == actual["estado"] else date.today().isoformat()
    if not d["empresa"] or not d["puesto"]:
        flash("Empresa y puesto son obligatorios.", "error")
        return redirect(url_for("detalle", sid=sid))
    d["id"] = sid
    get_db().execute(
        """UPDATE solicitudes SET empresa=:empresa, puesto=:puesto, fecha_envio=:fecha_envio,
           canal=:canal, enlace=:enlace, clase=:clase, localizacion=:localizacion,
           dias_presenciales=:dias_presenciales, estado=:estado, estado_fecha=:estado_fecha,
           notas=:notas WHERE id=:id""", d)
    if d["estado"] != actual["estado"]:
        registrar_estado(sid, d["estado"], d["estado_fecha"])
    get_db().commit()
    flash("Solicitud actualizada.", "ok")
    return redirect(url_for("detalle", sid=sid))


@app.post("/solicitud/<int:sid>/respuesta")
def respuesta(sid):
    s = get_or_404(sid)
    texto = request.form.get("respuesta_texto", "").strip()
    fecha = request.form.get("respuesta_fecha") or date.today().isoformat()
    archivo = request.files.get("archivo")
    guardado, original = s["respuesta_archivo"], s["respuesta_nombre"]

    if request.form.get("quitar_archivo"):
        borrar_archivo(guardado)
        guardado = original = None
    if archivo and archivo.filename:
        original = secure_filename(archivo.filename) or "adjunto"
        nuevo = f"{uuid.uuid4().hex}_{original}"
        archivo.save(os.path.join(UPLOAD_DIR, nuevo))
        borrar_archivo(guardado)
        guardado = nuevo

    if not texto and not guardado:
        fecha = None
    get_db().execute(
        """UPDATE solicitudes SET respuesta_texto=?, respuesta_fecha=?,
           respuesta_archivo=?, respuesta_nombre=? WHERE id=?""",
        (texto or None, fecha, guardado, original, sid))
    get_db().commit()
    flash("Respuesta guardada.", "ok")
    return redirect(url_for("detalle", sid=sid))


@app.get("/solicitud/<int:sid>/archivo")
def archivo(sid):
    s = get_or_404(sid)
    if not s["respuesta_archivo"]:
        abort(404)
    return send_from_directory(UPLOAD_DIR, s["respuesta_archivo"],
                               as_attachment=True, download_name=s["respuesta_nombre"])


@app.post("/solicitud/<int:sid>/eliminar")
def eliminar(sid):
    s = get_or_404(sid)
    borrar_archivo(s["respuesta_archivo"])
    get_db().execute("DELETE FROM historial_estados WHERE solicitud_id = ?", (sid,))
    get_db().execute("DELETE FROM solicitudes WHERE id = ?", (sid,))
    get_db().commit()
    flash("Solicitud eliminada.", "ok")
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
