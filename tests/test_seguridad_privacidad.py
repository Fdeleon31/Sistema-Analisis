"""Pruebas de privacidad, bóveda cifrada en reposo y cumplimiento Ley 81 (Ficha 22 · Oleada 3)."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket

import pytest

from motor.bitacora import Bitacora
from motor.privacidad import (
    anonimizar_texto_pii,
    aplicar_acl_solo_usuario_actual,
    cifrar_archivo_boveda,
    cifrar_carpeta_corrida,
    descifrar_archivo_boveda,
    descifrar_carpeta_corrida,
    detectar_carpeta_sincronizada,
    evaluar_postura_entorno,
    exportar_diagnostico_anonimizado,
    purgar_corridas_expiradas,
)
from motor.seguridad import ErrorSeguridad
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar_diario_asientos


# ---------------------------------------------------------------------------
# 1. Bóveda cifrada en reposo: scrypt + AES-256-GCM y Windows DPAPI
# ---------------------------------------------------------------------------


def test_boveda_archivo_scrypt_ida_vuelta_y_borrado_origen(tmp_path):
    origen = tmp_path / "cedula_sintetica.bin"
    datos = b"ENCABEZADO\x00\x01\x02DATOS-SINTETICOS-AUDITORIA\xff" * 25
    origen.write_bytes(datos)

    cifrado = cifrar_archivo_boveda(origen, contrasena="ClaveFuerte!2026", borrar_origen=True)
    assert cifrado == tmp_path / "cedula_sintetica.bin.folioenc"
    assert cifrado.exists()
    assert not origen.exists()

    meta = json.loads(cifrado.read_text(encoding="utf-8"))
    assert meta["modo"] == "scrypt"
    assert meta["algoritmo"] == "AES-256-GCM"
    assert meta["nombre_origen"] == "cedula_sintetica.bin"
    assert meta["sal_b64"]

    restaurado = descifrar_archivo_boveda(cifrado, contrasena="ClaveFuerte!2026")
    assert restaurado == origen
    assert restaurado.read_bytes() == datos

    with pytest.raises(ErrorSeguridad):
        descifrar_archivo_boveda(cifrado, contrasena="ClaveIncorrecta!2026")


@pytest.mark.skipif(os.name != "nt", reason="DPAPI solo está disponible en Windows")
def test_boveda_archivo_dpapi_ida_vuelta_y_archivo_vacio(tmp_path):
    origen = tmp_path / "papel_dpapi.json"
    contenido = b'{"cliente": "Cliente Sintetico S.A.", "hallazgos": 3}'
    origen.write_bytes(contenido)

    cifrado = cifrar_archivo_boveda(origen, usar_dpapi=True, borrar_origen=True)
    assert not origen.exists()

    meta = json.loads(cifrado.read_text(encoding="utf-8"))
    assert meta["modo"] == "dpapi"
    assert meta["clave_dpapi_b64"]

    destino = tmp_path / "restaurado.json"
    descifrar_archivo_boveda(cifrado, ruta_destino=destino)
    assert destino.read_bytes() == contenido

    vacio = tmp_path / "vacio.txt"
    vacio.write_bytes(b"")
    vacio_enc = cifrar_archivo_boveda(vacio, usar_dpapi=True)
    vacio_dec = descifrar_archivo_boveda(vacio_enc, ruta_destino=tmp_path / "vacio_dec.txt")
    assert vacio_dec.read_bytes() == b""


def test_boveda_valida_modalidades_y_detecta_alteracion_cifrado_y_aad(tmp_path):
    archivo = tmp_path / "muestra.txt"
    archivo.write_text("Contenido confidencial sintético de auditoría", encoding="utf-8")

    with pytest.raises(ErrorSeguridad):
        cifrar_archivo_boveda(archivo)
    with pytest.raises(ErrorSeguridad):
        cifrar_archivo_boveda(archivo, contrasena="")
    with pytest.raises(ErrorSeguridad):
        cifrar_archivo_boveda(archivo, contrasena="Clave123!", usar_dpapi=True)

    ruta_enc = cifrar_archivo_boveda(archivo, contrasena="ClavePrueba!99")
    original_json = json.loads(ruta_enc.read_text(encoding="utf-8"))

    # Alterar 1 byte en el texto cifrado
    alterado_ct = dict(original_json)
    raw_ct = bytearray(base64.b64decode(alterado_ct["cifrado_b64"]))
    raw_ct[0] ^= 0x01
    alterado_ct["cifrado_b64"] = base64.b64encode(bytes(raw_ct)).decode("ascii")
    ruta_ct_mal = tmp_path / "tamper_ct.folioenc"
    ruta_ct_mal.write_text(json.dumps(alterado_ct), encoding="utf-8")
    with pytest.raises(ErrorSeguridad):
        descifrar_archivo_boveda(ruta_ct_mal, ruta_destino=tmp_path / "out1.txt", contrasena="ClavePrueba!99")

    # Alterar el nombre de referencia AAD
    alterado_aad = dict(original_json)
    alterado_aad["nombre_origen"] = "otro_nombre.txt"
    ruta_aad_mal = tmp_path / "tamper_aad.folioenc"
    ruta_aad_mal.write_text(json.dumps(alterado_aad), encoding="utf-8")
    with pytest.raises(ErrorSeguridad):
        descifrar_archivo_boveda(ruta_aad_mal, ruta_destino=tmp_path / "out2.txt", contrasena="ClavePrueba!99")


def test_boveda_carpeta_corrida_scrypt_y_dpapi(tmp_path):
    carpeta = tmp_path / "corrida_2026"
    sub = carpeta / "anexos"
    sub.mkdir(parents=True)
    f1 = carpeta / "bitacora.jsonl"
    f2 = sub / "notas.txt"
    f1.write_text('{"evento":"inicio"}\n', encoding="utf-8")
    f2.write_text("Nota sintética", encoding="utf-8")

    # Encriptado con contraseña y borrado de origen
    generados = cifrar_carpeta_corrida(carpeta, contrasena="CarpetaSegura!2026", borrar_origen=True)
    assert len(generados) == 2
    assert all(p.suffix == ".folioenc" for p in generados)
    assert not f1.exists() and not f2.exists()

    # Segunda pasada no recifra archivos *.folioenc
    assert cifrar_carpeta_corrida(carpeta, contrasena="CarpetaSegura!2026") == []

    restaurados = descifrar_carpeta_corrida(carpeta, contrasena="CarpetaSegura!2026")
    assert set(restaurados) == {f1, f2}
    assert f1.read_text(encoding="utf-8") == '{"evento":"inicio"}\n'
    assert f2.read_text(encoding="utf-8") == "Nota sintética"

    if os.name == "nt":
        carpeta_dpapi = tmp_path / "corrida_dpapi"
        carpeta_dpapi.mkdir()
        f3 = carpeta_dpapi / "resumen.txt"
        f3.write_text("Resumen DPAPI", encoding="utf-8")
        enc_dpapi = cifrar_carpeta_corrida(carpeta_dpapi, usar_dpapi=True, borrar_origen=True)
        assert len(enc_dpapi) == 1
        assert not f3.exists()
        dec_dpapi = descifrar_carpeta_corrida(carpeta_dpapi)
        assert dec_dpapi == [f3]
        assert f3.read_text(encoding="utf-8") == "Resumen DPAPI"


# ---------------------------------------------------------------------------
# 2. Guardarraíles de entorno Windows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta,esperado_nube,proveedor",
    [
        (r"C:\Users\auditor\OneDrive\Documentos\Cliente", True, "OneDrive"),
        (r"C:\Users\auditor\OneDrive - Firma Panama\Encargos", True, "OneDrive"),
        (r"C:\Users\auditor\Dropbox\Auditoria\2025", True, "Dropbox"),
        (r"C:\Users\auditor\Google Drive\Mi unidad\Proyecto", True, "Google Drive"),
        (r"C:\Users\auditor\iCloudDrive\Papeles", True, "iCloud Drive"),
        (r"C:\Users\auditor\Box\Trabajo", True, "Box"),
        (r"C:\AuditoriaLocal\Proyecto", False, None),
        (r"C:\AuditoriaLocal\Sandbox\Proyecto", False, None),
    ],
)
def test_detectar_carpeta_sincronizada(ruta, esperado_nube, proveedor):
    res = detectar_carpeta_sincronizada(ruta)
    assert res["en_nube"] is esperado_nube
    assert res["proveedor"] == proveedor
    assert res["ruta"] == ruta
    assert isinstance(res["recomendacion"], str) and res["recomendacion"]


def test_aplicar_acl_solo_usuario_actual_y_evaluar_postura(tmp_path):
    carpeta = tmp_path / "espacio_aislado"
    carpeta.mkdir()
    archivo = carpeta / "secreto_sintetico.txt"
    archivo.write_text("datos", encoding="utf-8")

    r_dir = aplicar_acl_solo_usuario_actual(carpeta)
    r_file = aplicar_acl_solo_usuario_actual(archivo)
    assert r_dir["aplicado"] is True
    assert r_file["aplicado"] is True

    r_missing = aplicar_acl_solo_usuario_actual(tmp_path / "no_existe")
    assert r_missing["aplicado"] is False

    # Postura incompleta (sin config.toml ni usuarios.json)
    adv = evaluar_postura_entorno(carpeta)
    assert adv["estado"] == "ADVERTENCIA"
    assert len(adv["hallazgos"]) >= 2

    # Postura conforme en carpeta local aislada
    (carpeta / ".streamlit").mkdir()
    (carpeta / ".streamlit" / "config.toml").write_text(
        '[server]\naddress = "127.0.0.1"\nenableCORS = false\nenableXsrfProtection = true\n'
        '[browser]\ngatherUsageStats = false\n',
        encoding="utf-8",
    )
    (carpeta / "seguridad").mkdir()
    (carpeta / "seguridad" / "usuarios.json").write_text("{}", encoding="utf-8")

    ok = evaluar_postura_entorno(carpeta)
    if not ok["nube"]["en_nube"]:
        assert ok["estado"] == "OK"
        assert ok["hallazgos"] == []
    assert ok["streamlit_seguro"] is True
    assert ok["usuarios_configurados"] is True


# ---------------------------------------------------------------------------
# 3. Anonimización PII, diagnóstico técnico y retención (Ley 81)
# ---------------------------------------------------------------------------


def test_anonimizar_texto_pii_oculta_identificadores_panama_y_preserva_fechas():
    texto = (
        "Cliente: Distribuidora Sintética Istmo, S.A. | "
        "RUC 155678901-2-2024 DV 45 | "
        "Cédulas: 8-123-4567, PE-12-3456, E-8-123456 | "
        "Correo: contacto@istmo-sintetico.pa | "
        "Cuentas: 03-72-01-123456 y 0410987654321 | "
        "Teléfonos: +507 6612-3456 y 6789-0123 | "
        "Cierre: 2025-12-31 (Período 2025-2026)."
    )
    anon = anonimizar_texto_pii(texto, terminos_sensibles=["Distribuidora Sintética Istmo, S.A."])

    for sensible in (
        "Distribuidora Sintética Istmo",
        "155678901-2-2024",
        "8-123-4567",
        "PE-12-3456",
        "E-8-123456",
        "contacto@istmo-sintetico.pa",
        "03-72-01-123456",
        "0410987654321",
        "6612-3456",
        "6789-0123",
    ):
        assert sensible not in anon

    assert "[CONFIDENCIAL]" in anon
    assert "[ID-PA]" in anon
    assert "[EMAIL]" in anon
    assert "[CUENTA]" in anon
    assert "[TELEFONO]" in anon
    assert "2025-12-31" in anon
    assert "2025-2026" in anon


def test_exportar_diagnostico_anonimizado_oculta_cliente_pii_montos_y_rutas(tmp_path):
    corrida_dir = tmp_path / "corrida_diag"
    corrida_dir.mkdir()
    bit = Bitacora(corrida_dir / "bitacora.jsonl", usuario="auditor_local_demo")

    cliente = "Comercializadora Istmo Sintética, S.A."
    bit.registrar(
        "inicio",
        version_motor="0.8.0",
        paquete="asientos-nia240",
        version_paquete="1.0.0",
        cliente=cliente,
    )
    bit.registrar(
        "importacion",
        archivo="mayor.csv",
        tabla="mayor",
        codificacion="UTF-8",
        filas=2400,
        filas_excluidas=1,
        sha256="a" * 64,
        suma_monto=987654.32,
        transformaciones=[
            r"Cargado desde C:\Users\auditor_local_demo\OneDrive\Clientes\mayor.csv para Comercializadora Istmo Sintética, S.A."
        ],
        detalle_excluidas=[
            "Fila excluida de Juan Perez cédula 8-123-4567 RUC 155678901-2-2024 correo juan@istmo.pa cuenta 03-72-01-123456 por B/. 45,678.90"
        ],
    )
    bit.registrar(
        "diagnostico",
        estado_general="ADVERTENCIA",
        resumen=(
            "Diagnóstico de Comercializadora Istmo Sintética, S.A. (RUC 155678901-2-2024): "
            "diferencia de $12,345.67 en cuenta 0410987654321."
        ),
        conteos={"ok": 4, "advertencias": 1, "alertas": 0},
        hallazgos=[
            {
                "codigo": "cuadre_balanza",
                "nombre": "Cuadre de balanza",
                "tabla": "balanza",
                "estado": "ADVERTENCIA",
                "valor": "Dif. 12,345.67",
                "detalle": r"Revisar archivo C:\Users\auditor_local_demo\Documentos\balanza.csv contacto maria@istmo.pa",
                "accion_sugerida": "Validar con cédula PE-12-3456",
            }
        ],
    )
    bit.registrar(
        "prueba",
        prueba="asientos-puntaje",
        version_paquete="1.0.0",
        filas_resultado=11,
        sql_sha256="b" * 64,
        parametros={"materialidad_ejecucion": 112500},
    )

    destino = tmp_path / "soporte" / "diagnostico_soporte.json"
    rep = exportar_diagnostico_anonimizado(corrida_dir, destino=destino)

    assert destino.exists()
    serializado = destino.read_text(encoding="utf-8")
    assert json.loads(serializado) == rep

    assert rep["integridad_bitacora_sha256"] is True
    assert rep["paquete"] == "asientos-nia240"
    assert rep["version_motor"] == "0.8.0"
    assert rep["total_eventos"] == 4
    assert rep["conteos_eventos"]["diagnostico"] == 1
    assert rep["diagnostico"]["estado_general"] == "ADVERTENCIA"

    for dato_sensible in (
        cliente,
        "155678901-2-2024",
        "8-123-4567",
        "PE-12-3456",
        "juan@istmo.pa",
        "maria@istmo.pa",
        "03-72-01-123456",
        "0410987654321",
        "987654.32",
        "45,678.90",
        "12,345.67",
        "112500",
        "auditor_local_demo",
        r"C:\Users",
    ):
        assert dato_sensible not in serializado


def test_purgar_corridas_expiradas_simula_y_elimina_carpeta_antigua(tmp_path):
    salidas = tmp_path / "salidas"
    antigua = salidas / "20180101-101010"
    reciente = salidas / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    antigua.mkdir(parents=True)
    reciente.mkdir(parents=True)
    (antigua / "bitacora.jsonl").write_text("{}", encoding="utf-8")
    (reciente / "bitacora.jsonl").write_text("{}", encoding="utf-8")

    # Simulación: reporta la antigua pero no borra nada
    detectadas = purgar_corridas_expiradas(salidas, dias_retencion=1825, simular=True)
    assert detectadas == [antigua]
    assert antigua.exists()
    assert reciente.exists()

    # Ejecución real: elimina solo la antigua y conserva la reciente
    eliminadas = purgar_corridas_expiradas(salidas, dias_retencion=1825, simular=False)
    assert eliminadas == [antigua]
    assert not antigua.exists()
    assert reciente.exists()


# ---------------------------------------------------------------------------
# 4. Cero telemetría / cero sockets salientes
# ---------------------------------------------------------------------------


def test_ejecucion_sin_telemetria_ni_sockets_salientes(tmp_path, monkeypatch):
    intentos: list[tuple[str, object]] = []

    def _bloquear_connect(self, address):
        intentos.append(("connect", address))
        raise AssertionError(f"Conexión saliente no permitida hacia {address!r}")

    def _bloquear_connect_ex(self, address):
        intentos.append(("connect_ex", address))
        raise AssertionError(f"Conexión saliente no permitida hacia {address!r}")

    def _bloquear_create_connection(address, *args, **kwargs):
        intentos.append(("create_connection", address))
        raise AssertionError(f"create_connection no permitido hacia {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _bloquear_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _bloquear_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _bloquear_create_connection)

    mayor, balanza = generar_diario_asientos(tmp_path / "datos", semilla=7)
    encargo = {
        "cliente": "Empresa Sintética Sin Red, S.A.",
        "fecha_cierre": "2025-12-31",
        "materialidad_ejecucion": 112500,
        "umbral_trivial": 7500,
        "umbral_aprobacion": 10000,
    }
    corrida = ejecutar_encargo(
        "asientos-nia240",
        {"mayor": mayor, "balanza": balanza},
        encargo,
        tmp_path / "salidas",
    )

    assert intentos == []
    assert corrida.cedula.exists()
    assert corrida.bitacora.verificar()
