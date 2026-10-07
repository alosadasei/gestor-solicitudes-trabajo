import os
import sqlite3
import uuid
from datetime import date

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "solicitudes.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
CLASES = ["Presencial", "Híbrido", "Remoto"]
ESTADOS = ["Enviada", "En proceso", "Entrevista", "Oferta", "Rechazada", "Sin respuesta"]

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
        db.executescript(f.read())
        # migración para bases de datos creadas antes de añadir estos campos
        cols = {r[1] for r in db.execute("PRAGMA table_info(solicitudes)")}
        if "clase" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN clase TEXT NOT NULL DEFAULT 'Presencial'")
        if "localizacion" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN localizacion TEXT")
        if "dias_presenciales" not in cols:
            db.execute("ALTER TABLE solicitudes ADD COLUMN dias_presenciales INTEGER")


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


@app.route("/")
def index():
    filas = get_db().execute("SELECT * FROM solicitudes ORDER BY fecha_envio DESC, id DESC").fetchall()
    return render_template("index.html", filas=filas, estados=ESTADOS, clases=CLASES)


@app.route("/nueva", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        d = form_solicitud()
        if not d["empresa"] or not d["puesto"]:
            flash("Empresa y puesto son obligatorios.", "error")
            return render_template("nueva.html", estados=ESTADOS, clases=CLASES, s=d), 400
        cur = get_db().execute(
            """INSERT INTO solicitudes (empresa, puesto, fecha_envio, canal, enlace, clase, localizacion,
                  dias_presenciales, estado, notas)
               VALUES (:empresa, :puesto, :fecha_envio, :canal, :enlace, :clase, :localizacion,
                  :dias_presenciales, :estado, :notas)""", d)
        get_db().commit()
        flash("Solicitud añadida.", "ok")
        return redirect(url_for("detalle", sid=cur.lastrowid))
    return render_template("nueva.html", estados=ESTADOS, clases=CLASES,
                           s={"fecha_envio": date.today().isoformat(), "estado": "Enviada"})


@app.route("/solicitud/<int:sid>")
def detalle(sid):
    return render_template("detalle.html", s=get_or_404(sid), estados=ESTADOS, clases=CLASES)


@app.post("/solicitud/<int:sid>/editar")
def editar(sid):
    get_or_404(sid)
    d = form_solicitud()
    if not d["empresa"] or not d["puesto"]:
        flash("Empresa y puesto son obligatorios.", "error")
        return redirect(url_for("detalle", sid=sid))
    d["id"] = sid
    get_db().execute(
        """UPDATE solicitudes SET empresa=:empresa, puesto=:puesto, fecha_envio=:fecha_envio,
           canal=:canal, enlace=:enlace, clase=:clase, localizacion=:localizacion,
           dias_presenciales=:dias_presenciales, estado=:estado, notas=:notas WHERE id=:id""", d)
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
    get_db().execute("DELETE FROM solicitudes WHERE id = ?", (sid,))
    get_db().commit()
    flash("Solicitud eliminada.", "ok")
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
