"""Lectura segura (solo lectura) de archivos y bases de datos SQL (Ficha 12)."""
from __future__ import annotations

import codecs
import hashlib
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import duckdb
import pandas as pd

from motor.seguridad import MAX_BYTES_SQL_DUMP, ErrorSeguridad, bloquear_duckdb_externo, citar_identificador_sql

ESQUEMAS_SQL = re.compile(
    r"^(sqlite|postgresql|postgres|mysql(\+[a-z0-9_]+)?|mssql(\+[a-z0-9_]+)?|"
    r"oracle(\+[a-z0-9_]+)?|mariadb(\+[a-z0-9_]+)?)://",
    re.IGNORECASE,
)
RE_ENV_URI = re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)$")
PALABRAS_PROHIBIDAS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "ATTACH",
    "DETACH", "PRAGMA", "COPY", "CALL", "VACUUM", "LOAD", "INSTALL",
    "INTO", "SET", "RESET", "EXPORT", "IMPORT", "CHECKPOINT", "PREPARE",
    "DEALLOCATE", "USE",
}
FUNCIONES_PROHIBIDAS_SQL = {
    "READ_CSV", "READ_CSV_AUTO", "READ_PARQUET", "READ_JSON", "READ_JSON_AUTO",
    "READ_NDJSON", "READ_NDJSON_AUTO", "READ_NDJSON_OBJECTS", "READ_TEXT", "READ_BLOB",
    "READ_OBJECTS", "GLOB", "GETENV", "CURRENT_SETTING", "DUCKDB_SETTINGS",
    "DUCKDB_SECRETS", "DUCKDB_EXTENSIONS", "DUCKDB_DATABASES", "SNIFF_CSV",
    "PARQUET_SCAN", "PARQUET_METADATA", "PARQUET_SCHEMA", "SQLITE_SCAN",
    "SQLITE_ATTACH", "POSTGRES_SCAN", "POSTGRES_ATTACH", "MYSQL_SCAN",
    "ICEBERG_SCAN", "DELTA_SCAN", "ST_READ", "LOAD_AWS_CREDENTIALS",
    "HTTP_GET", "HTTP_POST",
    "PG_READ_FILE", "PG_READ_BINARY_FILE", "PG_LS_DIR", "PG_STAT_FILE",
    "LO_IMPORT", "LO_EXPORT", "DBLINK", "DBLINK_EXEC",
    "XP_CMDSHELL", "SP_OACREATE", "SP_CONFIGURE", "OPENROWSET",
    "OPENDATASOURCE", "OPENQUERY", "BULK", "LOAD_FILE", "OUTFILE",
    "DUMPFILE", "LOAD_EXTENSION", "SQLITE_LOAD_EXTENSION",
}
IDENTIFICADOR_SQL = re.compile(r"^[A-Za-z_][A-Za-z0-9_$.]*$")
_RE_QUERY_SECRETO = re.compile(r"(?i)([?&](?:password|passwd|pwd|secret|token|pass)=)[^&]+")
_SQLITE_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)


def es_uri_sql(valor: str | Path) -> bool:
    """Indica si el valor recibido es una cadena de conexión SQL o referencia env:VAR."""
    if not isinstance(valor, str):
        return False
    limpia = valor.strip()
    return bool(ESQUEMAS_SQL.match(limpia) or RE_ENV_URI.match(limpia))


def resolver_uri_sql(uri: str) -> str:
    """Resuelve referencias env:NOMBRE_VAR y valida el esquema de la URI SQL."""
    if not isinstance(uri, str) or not uri.strip():
        raise ErrorSeguridad("Cadena de conexión SQL vacía.")
    limpia = uri.strip()
    m_env = RE_ENV_URI.match(limpia)
    if m_env:
        var = m_env.group(1)
        resuelta = (os.environ.get(var) or "").strip()
        if not resuelta:
            raise ErrorSeguridad(f"La variable de entorno {var!r} no está definida para la conexión SQL.")
        if not ESQUEMAS_SQL.match(resuelta):
            raise ErrorSeguridad(f"El valor de la variable de entorno {var!r} no es una URI SQL válida.")
        return resuelta
    if not ESQUEMAS_SQL.match(limpia):
        raise ErrorSeguridad(f"Cadena de conexión SQL no reconocida: {enmascarar_uri(limpia)}")
    return limpia


def enmascarar_uri(uri: str) -> str:
    """Oculta la contraseña y secretos en una URI SQL antes de guardarla en bitácora o control."""
    limpia = uri.strip()
    if RE_ENV_URI.match(limpia):
        return limpia
    enmascarada = limpia
    try:
        partes = urlsplit(limpia)
        if partes.password is not None:
            usuario = partes.username or ""
            host = partes.hostname or ""
            puerto = f":{partes.port}" if partes.port else ""
            netloc = f"{usuario}:***@{host}{puerto}"
            enmascarada = urlunsplit((partes.scheme, netloc, partes.path, partes.query, partes.fragment))
    except ValueError:
        enmascarada = re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", limpia)
    return _RE_QUERY_SECRETO.sub(r"\1***", enmascarada)


def _sin_comentarios_ni_literales(sql: str) -> str:
    """Elimina comentarios SQL (incluidos anidados) y reemplaza literales por espacios."""
    salida: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if ch == "-" and nxt == "-":
            while i < n and sql[i] != "\n":
                i += 1
            salida.append(" ")
            continue
        if ch == "/" and nxt == "*":
            prof = 1
            i += 2
            while i < n and prof > 0:
                if i + 1 < n and sql[i] == "/" and sql[i + 1] == "*":
                    prof += 1
                    i += 2
                    continue
                if i + 1 < n and sql[i] == "*" and sql[i + 1] == "/":
                    prof -= 1
                    i += 2
                    continue
                i += 1
            if prof > 0:
                raise ErrorSeguridad("Consulta SQL rechazada por seguridad: comentario de bloque /* ... */ sin cerrar.")
            salida.append(" ")
            continue
        if ch == "$" and nxt == "$":
            raise ErrorSeguridad("Consulta SQL rechazada por seguridad: no se permite dollar-quoting ($$).")
        if ch == "'":
            i += 1
            cerrado = False
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    cerrado = True
                    break
                i += 1
            if not cerrado:
                raise ErrorSeguridad("Consulta SQL rechazada por seguridad: literal de texto sin cerrar.")
            salida.append(" '' ")
            continue
        salida.append(ch)
        i += 1
    return "".join(salida)


def validar_consulta_solo_lectura(sql: str) -> str:
    """Garantiza que una consulta SQL sea estrictamente de solo lectura (SELECT o WITH)."""
    if not isinstance(sql, str) or not sql.strip():
        raise ErrorSeguridad("La consulta SQL está vacía.")
    limpia = sql.strip().rstrip(";").strip()
    inspeccion = _sin_comentarios_ni_literales(limpia).strip()
    if not inspeccion:
        raise ErrorSeguridad("La consulta SQL no contiene instrucciones ejecutables.")
    if ";" in inspeccion:
        raise ErrorSeguridad("Solo se permite una única consulta SELECT de solo lectura (sin múltiples sentencias ';').")

    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", inspeccion.upper())
    if not tokens or tokens[0] not in ("SELECT", "WITH"):
        raise ErrorSeguridad("Por seguridad, solo se permiten consultas de solo lectura que inicien con SELECT o WITH.")

    bloqueadas = PALABRAS_PROHIBIDAS | FUNCIONES_PROHIBIDAS_SQL
    prohibidas = [t for t in tokens if t in bloqueadas]
    if prohibidas:
        raise ErrorSeguridad(
            f"Consulta SQL rechazada por seguridad (solo lectura): se detectó {', '.join(dict.fromkeys(prohibidas))}."
        )
    return limpia


def _autorizador_sqlite_solo_lectura(action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None) -> int:
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ("load_extension", "sqlite_load_extension"):
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, _SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _autorizador_sqlite_dump(action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None) -> int:
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ("load_extension", "sqlite_load_extension"):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_UPDATE and arg1 in ("sqlite_master", "sqlite_schema"):
        return sqlite3.SQLITE_OK
    if action in (
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    ):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _leer_texto_sql(ruta: Path) -> str:
    crudo = ruta.read_bytes()
    if crudo.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return crudo.decode("utf-16")
    if crudo.startswith(codecs.BOM_UTF8):
        return crudo.decode("utf-8-sig")
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("cp1252")


def _dividir_sentencias_sql(texto: str) -> list[str]:
    """Divide un script SQL en sentencias respetando literales y comentarios."""
    sentencias: list[str] = []
    actual: list[str] = []
    i, n = 0, len(texto)
    en_comilla = False
    while i < n:
        ch = texto[i]
        nxt = texto[i + 1] if i + 1 < n else ""
        if not en_comilla and ch == "-" and nxt == "-":
            while i < n and texto[i] != "\n":
                i += 1
            actual.append(" ")
            continue
        if not en_comilla and ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (texto[i] == "*" and texto[i + 1] == "/"):
                i += 1
            i += 2
            actual.append(" ")
            continue
        if ch == "'":
            actual.append(ch)
            if en_comilla and nxt == "'":
                actual.append(nxt)
                i += 2
                continue
            if en_comilla and i > 0 and texto[i - 1] == "\\":
                i += 1
                continue
            en_comilla = not en_comilla
            i += 1
            continue
        if ch == ";" and not en_comilla:
            bloque = "".join(actual).strip()
            if bloque:
                sentencias.append(bloque)
            actual = []
            i += 1
            continue
        actual.append(ch)
        i += 1
    ultimo = "".join(actual).strip()
    if ultimo:
        sentencias.append(ultimo)
    return sentencias


def _normalizar_sentencia_dump(sentencia: str) -> str:
    """Adapta dialectos comunes de MySQL/PostgreSQL/SQL Server a SQLite."""
    s = re.sub(r"\b(?:dbo|public)\.", "", sentencia, flags=re.IGNORECASE)
    s = re.sub(r"\[(?:dbo|public)\]\.", "", s, flags=re.IGNORECASE)
    s = re.sub(r'"(?:dbo|public)"\.', "", s, flags=re.IGNORECASE)

    if re.match(r"^\s*CREATE\s+TABLE\b", s, flags=re.IGNORECASE):
        s = re.sub(r"\)\s*(?:ENGINE|DEFAULT\s+CHARSET|CHARSET|COLLATE|AUTO_INCREMENT|COMMENT)\b.*$", ")", s, flags=re.IGNORECASE | re.DOTALL)
        s = re.sub(r"\bAUTO_INCREMENT\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\bUNSIGNED\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\bCHARACTER\s+SET\s+[A-Za-z0-9_]+\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\bCOLLATE\s+[A-Za-z0-9_]+\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:NVARCHAR2?|VARCHAR2)\s*\(\s*\d+\s*\)", "TEXT", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:SMALLMONEY|MONEY)\b", "NUMERIC", s, flags=re.IGNORECASE)
        s = re.sub(r"\bDATETIME2?\b", "TEXT", s, flags=re.IGNORECASE)
    elif re.match(r"^\s*INSERT\s+INTO\b", s, flags=re.IGNORECASE):
        s = s.replace("\\'", "''")
    return s


def _cargar_dump_sql_en_memoria(ruta: Path, max_bytes: int = MAX_BYTES_SQL_DUMP) -> sqlite3.Connection:
    """Carga un volcado .sql en SQLite en memoria aceptando solo CREATE TABLE e INSERT INTO."""
    tamano = ruta.stat().st_size
    if tamano > max_bytes:
        raise ErrorSeguridad(
            f"El volcado SQL {ruta.name!r} excede el límite permitido ({tamano:,} > {max_bytes:,} bytes)."
        )
    texto = _leer_texto_sql(ruta)
    con = sqlite3.connect(":memory:")
    con.set_authorizer(_autorizador_sqlite_dump)
    ignorables = re.compile(
        r"^(SET|USE|LOCK\s+TABLES|UNLOCK\s+TABLES|BEGIN|COMMIT|START\s+TRANSACTION|GO|DELIMITER)\b",
        re.IGNORECASE,
    )
    permitidas = re.compile(r"^(CREATE\s+TABLE|INSERT\s+INTO)\b", re.IGNORECASE)
    try:
        for sentencia in _dividir_sentencias_sql(texto):
            limpia = sentencia.strip()
            if not limpia or ignorables.match(limpia):
                continue
            if not permitidas.match(limpia):
                raise ErrorSeguridad(
                    "El archivo .sql contiene una instrucción no permitida en modo solo lectura "
                    f"(solo se aceptan CREATE TABLE e INSERT INTO): {limpia[:60]!r}"
                )
            con.execute(_normalizar_sentencia_dump(limpia))
        con.set_authorizer(_autorizador_sqlite_solo_lectura)
        return con
    except Exception:
        con.close()
        raise


def _listar_tablas_sqlite(con: sqlite3.Connection) -> list[str]:
    filas = con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [f[0] for f in filas]


def listar_tablas_archivo_sql(ruta: str | Path) -> list[str]:
    """Lista las tablas o vistas disponibles dentro de un archivo .sqlite, .duckdb o .sql."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext in (".sqlite", ".sqlite3", ".db"):
        con = sqlite3.connect(f"file:{ruta.resolve().as_posix()}?mode=ro", uri=True)
        con.set_authorizer(_autorizador_sqlite_solo_lectura)
        try:
            return _listar_tablas_sqlite(con)
        finally:
            con.close()
    if ext == ".duckdb":
        con = duckdb.connect(str(ruta), read_only=True)
        try:
            bloquear_duckdb_externo(con)
            filas = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') ORDER BY table_name"
            ).fetchall()
            return [f[0] for f in filas]
        finally:
            con.close()
    if ext == ".sql":
        con = _cargar_dump_sql_en_memoria(ruta)
        try:
            return _listar_tablas_sqlite(con)
        finally:
            con.close()
    raise ValueError(f"Extensión SQL no soportada: {ext}")


def _resolver_sql_objetivo(
    tablas_disponibles: list[str] | None,
    tabla_origen: str | None,
    consulta_sql: str | None,
    limite: int | None,
) -> tuple[str, str]:
    if consulta_sql and consulta_sql.strip():
        sql_base = validar_consulta_solo_lectura(consulta_sql)
    else:
        if tablas_disponibles is not None:
            if not tablas_disponibles:
                raise ValueError("El archivo SQL no contiene tablas.")
            if tabla_origen is None:
                if len(tablas_disponibles) == 1:
                    tabla_origen = tablas_disponibles[0]
                else:
                    raise ValueError(
                        f"El archivo SQL tiene varias tablas ({', '.join(tablas_disponibles)}). "
                        "Indica --tabla-origen o una --consulta-sql."
                    )
            if tabla_origen not in tablas_disponibles:
                raise ValueError(
                    f"La tabla {tabla_origen!r} no existe en el origen. "
                    f"Tablas disponibles: {', '.join(tablas_disponibles)}"
                )
        elif not tabla_origen:
            raise ValueError("Indica --tabla-origen o una --consulta-sql para consultar la base de datos.")
        if not IDENTIFICADOR_SQL.match(tabla_origen):
            raise ErrorSeguridad(f"Nombre de tabla no válido: {tabla_origen!r}")
        partes = ".".join(citar_identificador_sql(p) for p in tabla_origen.split("."))
        sql_base = f"SELECT * FROM {partes}"

    sql_ejecucion = f"SELECT * FROM ({sql_base}) AS _cuadra_q LIMIT {int(limite)}" if limite else sql_base
    return sql_base, sql_ejecucion


def leer_archivo_sql(
    ruta: str | Path,
    tabla_origen: str | None = None,
    consulta_sql: str | None = None,
    limite: int | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Lee un DataFrame desde un archivo .sqlite/.sqlite3/.db, .duckdb o .sql en modo solo lectura."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    ext = ruta.suffix.lower()
    tablas = listar_tablas_archivo_sql(ruta)
    sql_base, sql_ejecucion = _resolver_sql_objetivo(tablas, tabla_origen, consulta_sql, limite)

    if ext in (".sqlite", ".sqlite3", ".db"):
        con = sqlite3.connect(f"file:{ruta.resolve().as_posix()}?mode=ro", uri=True)
        con.set_authorizer(_autorizador_sqlite_solo_lectura)
        try:
            df = pd.read_sql_query(sql_ejecucion, con)
        finally:
            con.close()
        tipo = "SQLite"
    elif ext == ".duckdb":
        con = duckdb.connect(str(ruta), read_only=True)
        try:
            bloquear_duckdb_externo(con)
            df = con.execute(sql_ejecucion).df()
        finally:
            con.close()
        tipo = "DuckDB"
    elif ext == ".sql":
        con = _cargar_dump_sql_en_memoria(ruta)
        try:
            df = pd.read_sql_query(sql_ejecucion, con)
        finally:
            con.close()
        tipo = "SQL dump"
    else:
        raise ValueError(f"Extensión SQL no soportada: {ext}")

    return df, {"codificacion": tipo, "origen_sql": sql_base}


def leer_conexion_sql(
    uri: str,
    tabla_origen: str | None = None,
    consulta_sql: str | None = None,
    limite: int | None = None,
    timeout_segundos: int = 30,
    requerir_tls: bool = False,
    forzar_solo_lectura: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Ejecuta una consulta de solo lectura contra una URI SQL y devuelve (df, metadatos)."""
    if not es_uri_sql(uri):
        raise ErrorSeguridad(f"Cadena de conexión SQL no reconocida: {enmascarar_uri(uri)}")

    uri_limpia = enmascarar_uri(uri)
    uri_real = resolver_uri_sql(uri)
    sql_base, sql_ejecucion = _resolver_sql_objetivo(None, tabla_origen, consulta_sql, limite)

    if uri_real.lower().startswith("sqlite:///"):
        ruta_sqlite = Path(uri_real[len("sqlite:///"):])
        if not ruta_sqlite.exists():
            raise FileNotFoundError(f"No existe la base de datos SQLite: {ruta_sqlite}")
        con = sqlite3.connect(f"file:{ruta_sqlite.resolve().as_posix()}?mode=ro", uri=True)
        con.set_authorizer(_autorizador_sqlite_solo_lectura)
        try:
            df = pd.read_sql_query(sql_ejecucion, con)
        finally:
            con.close()
    else:
        try:
            import sqlalchemy
        except ImportError as exc:
            raise ValueError(
                "Para conectarte directamente a SQL Server, PostgreSQL o MySQL instala SQLAlchemy y el driver: "
                "pip install sqlalchemy pyodbc (SQL Server/Softland/SAP B1/GP), psycopg[binary] (PostgreSQL/Odoo) o pymysql (MySQL)."
            ) from exc
        esquema = urlsplit(uri_real).scheme.lower().split("+")[0]
        connect_args: dict[str, object] = {}
        if esquema in ("postgresql", "postgres"):
            connect_args["connect_timeout"] = int(timeout_segundos)
            if requerir_tls:
                connect_args["sslmode"] = "require"
        elif esquema in ("mysql", "mariadb"):
            connect_args["connect_timeout"] = int(timeout_segundos)
            if requerir_tls:
                connect_args["ssl"] = {}
        elif esquema == "mssql":
            connect_args["timeout"] = int(timeout_segundos)
            if requerir_tls:
                connect_args["Encrypt"] = "yes"

        engine = sqlalchemy.create_engine(uri_real, connect_args=connect_args)
        try:
            with engine.connect() as conn:
                tx = conn.begin()
                try:
                    if forzar_solo_lectura:
                        if esquema in ("postgresql", "postgres"):
                            conn.execute(sqlalchemy.text("SET TRANSACTION READ ONLY"))
                            conn.execute(sqlalchemy.text(f"SET LOCAL statement_timeout = {int(timeout_segundos * 1000)}"))
                        elif esquema in ("mysql", "mariadb"):
                            conn.execute(sqlalchemy.text("SET SESSION TRANSACTION READ ONLY"))
                    df = pd.read_sql_query(sqlalchemy.text(sql_ejecucion), conn)
                finally:
                    tx.rollback()
        finally:
            engine.dispose()

    etiqueta = tabla_origen or "consulta"
    contenido_hash = f"{uri_limpia}\n{sql_base}\n{df.to_csv(index=False)}".encode("utf-8")
    sha256 = hashlib.sha256(contenido_hash).hexdigest()
    return df, {
        "archivo": f"{uri_limpia} [{etiqueta}]",
        "codificacion": "SQL",
        "sha256": sha256,
        "origen_sql": sql_base,
    }
