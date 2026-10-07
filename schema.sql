CREATE TABLE IF NOT EXISTS solicitudes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa         TEXT NOT NULL,
    puesto          TEXT NOT NULL,
    fecha_envio     TEXT NOT NULL,              -- YYYY-MM-DD
    canal           TEXT,                       -- LinkedIn, email, web...
    enlace          TEXT,
    clase           TEXT NOT NULL DEFAULT 'Presencial',  -- Presencial | Híbrido | Remoto
    localizacion    TEXT,                       -- solo si no es Remoto
    dias_presenciales INTEGER,                  -- solo si es Híbrido
    estado          TEXT NOT NULL DEFAULT 'Enviada',
    notas           TEXT,
    respuesta_texto   TEXT,
    respuesta_fecha   TEXT,
    respuesta_archivo TEXT,                     -- nombre guardado en uploads/
    respuesta_nombre  TEXT,                     -- nombre original del archivo
    creada_en       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
