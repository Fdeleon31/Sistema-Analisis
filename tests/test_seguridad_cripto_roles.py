"""Pruebas de criptografía local (Ed25519, scrypt, AES-256-GCM, DPAPI), RBAC y NIA 220/230 · Oleada 2 / Ficha 21."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from motor.bitacora import HASH_INICIAL, Bitacora, _hash_registro
from motor.cripto import (
    cifrar_aes_gcm,
    cifrar_clave_privada,
    clave_publica_ed25519,
    construir_manifiesto_corrida,
    derivar_clave_scrypt,
    descifrar_aes_gcm,
    descifrar_clave_privada,
    desproteger_dpapi,
    firmar_ed25519,
    generar_par_ed25519,
    hashear_contrasena,
    huella_clave_publica,
    proteger_dpapi,
    sellar_corrida,
    verificar_contrasena,
    verificar_ed25519,
    verificar_sello_corrida,
)
from motor.revision import (
    cargar_revisiones,
    estado_archivo_nia230,
    firmar_papel_trabajo,
    reabrir_papel_trabajo,
    registrar_revision_prueba,
)
from motor.seguridad import ErrorSeguridad
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar
from motor.usuarios import (
    PERFIL_ADMIN,
    PERFIL_PREPARADOR,
    PERFIL_REVISOR,
    PERFIL_SOCIO,
    GestorUsuarios,
    puede_firmar_rol,
    validar_politica_contrasena,
)


# ---------------------------------------------------------------------------
# 1. Ed25519 (RFC 8032 §7.1)
# ---------------------------------------------------------------------------


def test_ed25519_vectores_oficiales_rfc8032():
    # RFC 8032 §7.1 · TEST 1 (mensaje vacío)
    sk1 = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pk1 = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    sig1 = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    assert clave_publica_ed25519(sk1) == pk1
    assert firmar_ed25519(sk1, b"") == sig1
    assert verificar_ed25519(pk1, b"", sig1) is True

    # RFC 8032 §7.1 · TEST 2 (mensaje 0x72, 1 byte)
    sk2 = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    pk2 = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
    sig2 = bytes.fromhex(
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
    )
    assert clave_publica_ed25519(sk2) == pk2
    assert firmar_ed25519(sk2, b"\x72") == sig2
    assert verificar_ed25519(pk2, b"\x72", sig2) is True


def test_ed25519_rechaza_alteraciones_y_entradas_malformadas_sin_excepcion():
    sk, pk = generar_par_ed25519()
    msg = b"Evidencia determinista de auditoria"
    sig = firmar_ed25519(sk, msg)
    assert len(huella_clave_publica(pk)) == 64
    assert verificar_ed25519(pk, msg, sig) is True

    # Mutación de 1 bit en firma y mensaje
    sig_alt = bytes([sig[0] ^ 0x01]) + sig[1:]
    assert verificar_ed25519(pk, msg, sig_alt) is False
    assert verificar_ed25519(pk, msg + b"!", sig) is False

    # Entradas malformadas, puntos fuera de curva y punto identidad
    assert verificar_ed25519(b"corta", msg, sig) is False
    assert verificar_ed25519(pk, msg, b"corta") is False
    assert verificar_ed25519(b"\xff" * 32, msg, sig) is False
    punto_identidad = b"\x01" + b"\x00" * 31
    firma_nula = punto_identidad + b"\x00" * 32
    assert verificar_ed25519(punto_identidad, msg, firma_nula) is False


# ---------------------------------------------------------------------------
# 2. scrypt, AES-256-GCM (Windows CNG) y DPAPI
# ---------------------------------------------------------------------------


def test_scrypt_contrasenas_y_derivacion():
    sal = b"sal-sintetica-16"
    k1 = derivar_clave_scrypt("ClaveAuditoria2026!", sal, largo=32)
    k2 = derivar_clave_scrypt("ClaveAuditoria2026!", sal, largo=32)
    assert len(k1) == 32 and k1 == k2

    reg = hashear_contrasena("ClaveAuditoria2026!")
    assert reg["algoritmo"] == "scrypt"
    assert verificar_contrasena("ClaveAuditoria2026!", reg) is True
    assert verificar_contrasena("ClaveIncorrecta99!", reg) is False
    assert verificar_contrasena("ClaveAuditoria2026!", {"algoritmo": "otro"}) is False


def test_aes_gcm_ida_vuelta_y_deteccion_de_alteracion():
    clave = b"\x24" * 32
    aad = b"folio-aad-sintetico"
    plano = b"Asientos contables verificados para NIA 240."

    paquete = cifrar_aes_gcm(clave, plano, aad=aad)
    assert paquete["algoritmo"] == "AES-256-GCM"
    assert descifrar_aes_gcm(clave, paquete, aad=aad) == plano

    # Caso borde: texto plano vacío
    paq_vacio = cifrar_aes_gcm(clave, b"", aad=aad)
    assert descifrar_aes_gcm(clave, paq_vacio, aad=aad) == b""

    # Alterar 1 bit en texto cifrado
    cif_bytes = bytearray(base64.b64decode(paquete["cifrado_b64"]))
    cif_bytes[0] ^= 0x01
    paq_bad_cif = {**paquete, "cifrado_b64": base64.b64encode(bytes(cif_bytes)).decode("ascii")}
    with pytest.raises(ErrorSeguridad):
        descifrar_aes_gcm(clave, paq_bad_cif, aad=aad)

    # Alterar 1 bit en tag
    tag_bytes = bytearray(base64.b64decode(paquete["tag_b64"]))
    tag_bytes[5] ^= 0x80
    paq_bad_tag = {**paquete, "tag_b64": base64.b64encode(bytes(tag_bytes)).decode("ascii")}
    with pytest.raises(ErrorSeguridad):
        descifrar_aes_gcm(clave, paq_bad_tag, aad=aad)

    # Alterar AAD o clave
    with pytest.raises(ErrorSeguridad):
        descifrar_aes_gcm(clave, paquete, aad=b"folio-aad-alterado")
    with pytest.raises(ErrorSeguridad):
        descifrar_aes_gcm(b"\x25" * 32, paquete, aad=aad)


@pytest.mark.skipif(os.name != "nt", reason="DPAPI (crypt32.dll) solo existe en Windows")
def test_dpapi_y_clave_privada_cifrada():
    secreto = b"semilla-local-sintetica-dpapi-2026"
    protegido = proteger_dpapi(secreto)
    assert protegido != secreto
    assert desproteger_dpapi(protegido) == secreto

    # Buffer vacío soportado y entropía incorrecta falla
    assert desproteger_dpapi(proteger_dpapi(b"")) == b""
    with pytest.raises(ErrorSeguridad):
        desproteger_dpapi(protegido, entropia=b"EntropiaEquivocada")

    sk, _ = generar_par_ed25519()
    env = cifrar_clave_privada(sk, "ClaveSegura2026!")
    assert descifrar_clave_privada(env, "ClaveSegura2026!") == sk
    with pytest.raises(ErrorSeguridad):
        descifrar_clave_privada(env, "ClaveEquivocada2026!")


# ---------------------------------------------------------------------------
# 3. Sellado criptográfico cruzado de corrida (sello.json)
# ---------------------------------------------------------------------------


def _recalcular_cadena_bitacora(ruta_bitacora: Path, nuevo_evento: str) -> None:
    """Reconstruye toda la cadena SHA-256 de bitacora.jsonl simulando manipulación sofisticada."""
    lineas = [json.loads(ln) for ln in ruta_bitacora.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lineas
    lineas[0]["datos"]["cliente"] = nuevo_evento
    anterior = HASH_INICIAL
    nuevas: list[str] = []
    for reg in lineas:
        copia = {k: v for k, v in reg.items() if k != "hash"}
        copia["hash_anterior"] = anterior
        copia["hash"] = _hash_registro(copia)
        anterior = copia["hash"]
        nuevas.append(json.dumps(copia, ensure_ascii=False, default=str))
    ruta_bitacora.write_text("\n".join(nuevas) + "\n", encoding="utf-8")


def test_sellado_corrida_detecta_tampering_de_cedula_revisiones_y_recalculo_bitacora(tmp_path):
    mayor = generar(tmp_path / "mayor.csv")
    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": mayor},
        {"cliente": "Comercial Istmo, S.A."},
        tmp_path / "corrida_sello",
    )
    ids = [r.id for r in corrida.resultados if not r.omitida]
    for pid in ids:
        registrar_revision_prueba(
            corrida.carpeta, pid, "Aclarado con evidencia", "Documentado", "Ana Prep", "Preparador", corrida.bitacora
        )

    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "admin1",
        "Carlos Admin",
        "AdminClave2026!",
        preparador={"usuario": "ana.prep", "nombre_completo": "Ana Prep", "contrasena": "PrepClave2026!"},
    )
    ses_admin = gestor.autenticar("admin1", "AdminClave2026!", modo_acceso=PERFIL_ADMIN)
    gestor.crear_usuario(ses_admin, "luis.rev", "Luis Rev", "RevisorClave2026!", PERFIL_REVISOR)
    gestor.crear_usuario(ses_admin, "sofia.soc", "Sofía Socio", "SocioClave2026!", PERFIL_SOCIO)

    ses_prep = gestor.autenticar("ana.prep", "PrepClave2026!", modo_acceso=PERFIL_PREPARADOR)
    ses_rev = gestor.autenticar("luis.rev", "RevisorClave2026!", modo_acceso=PERFIL_PREPARADOR)
    ses_soc = gestor.autenticar("sofia.soc", "SocioClave2026!", modo_acceso=PERFIL_PREPARADOR)

    firmar_papel_trabajo(
        corrida.carpeta, "Preparador", ses_prep.nombre_completo,
        bitacora=corrida.bitacora, pruebas_ejecutadas=ids, exigir_segregacion=True, sesion=ses_prep,
    )
    firmar_papel_trabajo(
        corrida.carpeta, "Revisor", ses_rev.nombre_completo,
        bitacora=corrida.bitacora, pruebas_ejecutadas=ids, exigir_segregacion=True, sesion=ses_rev,
    )
    estado = firmar_papel_trabajo(
        corrida.carpeta, "Socio", ses_soc.nombre_completo,
        bitacora=corrida.bitacora, pruebas_ejecutadas=ids, exigir_segregacion=True, sesion=ses_soc,
    )
    assert estado["bloqueado"] is True
    assert (corrida.carpeta / "sello.json").exists()

    # Sello íntegro
    res_ok = verificar_sello_corrida(corrida.carpeta, clave_publica_esperada=ses_soc.clave_publica_bytes)
    assert res_ok["valido"] is True
    assert res_ok["usuario"] == "sofia.soc"
    assert res_ok["rol"] == "Socio"
    assert res_ok["huella_clave"] == ses_soc.huella_clave

    # Clave esperada distinta falla
    _, otra_pub = generar_par_ed25519()
    assert verificar_sello_corrida(corrida.carpeta, clave_publica_esperada=otra_pub)["valido"] is False

    # 1) Alterar 1 byte de cedula.xlsx
    cedula_orig = corrida.cedula.read_bytes()
    corrida.cedula.write_bytes(cedula_orig[:-1] + bytes([cedula_orig[-1] ^ 0x01]))
    assert verificar_sello_corrida(corrida.carpeta)["valido"] is False
    corrida.cedula.write_bytes(cedula_orig)
    assert verificar_sello_corrida(corrida.carpeta)["valido"] is True

    # 2) Editar revisiones.json
    rev_path = corrida.carpeta / "revisiones.json"
    rev_orig = rev_path.read_text(encoding="utf-8")
    rev_data = json.loads(rev_orig)
    rev_data["firmas"]["Preparador"]["observacion"] = "Editado sin permiso"
    rev_path.write_text(json.dumps(rev_data, indent=2, ensure_ascii=False), encoding="utf-8")
    assert verificar_sello_corrida(corrida.carpeta)["valido"] is False
    rev_path.write_text(rev_orig, encoding="utf-8")
    assert verificar_sello_corrida(corrida.carpeta)["valido"] is True

    # 3) Recalcular manualmente TODA la cadena SHA-256 de bitacora.jsonl
    bit_path = corrida.carpeta / "bitacora.jsonl"
    _recalcular_cadena_bitacora(bit_path, "Cliente Falsificado, S.A.")
    assert Bitacora(bit_path).verificar() is True
    res_recalc = verificar_sello_corrida(corrida.carpeta, clave_publica_esperada=ses_soc.clave_publica_bytes)
    assert res_recalc["valido"] is False

    # Verificar construir_manifiesto_corrida directamente
    man = construir_manifiesto_corrida(corrida.carpeta)
    assert "cedula.xlsx" in man["archivos"] and "revisiones.json" in man["archivos"]


# ---------------------------------------------------------------------------
# 4. GestorUsuarios, RBAC, Fuerza Bruta y Ciclo de Vida
# ---------------------------------------------------------------------------


def test_gestor_usuarios_rbac_bloqueo_y_cambio_contrasena(tmp_path):
    with pytest.raises(ErrorSeguridad):
        validar_politica_contrasena("corta")
    with pytest.raises(ErrorSeguridad):
        validar_politica_contrasena("todominuscula123")
    with pytest.raises(ErrorSeguridad):
        validar_politica_contrasena("TODOMAYUSCULA123")
    with pytest.raises(ErrorSeguridad):
        validar_politica_contrasena("SinDigitosAqui")
    validar_politica_contrasena("ValidaClave2026")

    gestor = GestorUsuarios(tmp_path)
    assert gestor.existe_configuracion() is False

    gestor.inicializar_firma(
        "admin.ti",
        "Laura TI",
        "AdminClave2026!",
        preparador={"usuario": "prep.uno", "nombre_completo": "Pedro Prep", "contrasena": "PrepClave2026!"},
    )
    assert gestor.existe_configuracion() is True

    # Modos de acceso estrictos
    with pytest.raises(ErrorSeguridad):
        gestor.autenticar("prep.uno", "PrepClave2026!", modo_acceso=PERFIL_ADMIN)
    with pytest.raises(ErrorSeguridad):
        gestor.autenticar("admin.ti", "AdminClave2026!", modo_acceso=PERFIL_PREPARADOR)

    ses_admin = gestor.autenticar("admin.ti", "AdminClave2026!", modo_acceso=PERFIL_ADMIN)
    ses_prep = gestor.autenticar("prep.uno", "PrepClave2026!", modo_acceso=PERFIL_PREPARADOR)
    assert ses_admin.es_admin is True
    assert puede_firmar_rol(ses_admin, PERFIL_PREPARADOR) is False
    assert puede_firmar_rol(ses_prep, PERFIL_PREPARADOR) is True
    assert puede_firmar_rol(ses_prep, PERFIL_REVISOR) is False

    # Solo Administrador crea usuarios, cambia políticas o desactiva
    with pytest.raises(ErrorSeguridad):
        gestor.crear_usuario(ses_prep, "otro", "Otro", "OtroClave2026!", PERFIL_REVISOR)
    with pytest.raises(ErrorSeguridad):
        gestor.actualizar_politicas(ses_prep, ventana_archivo_dias=45)

    gestor.crear_usuario(ses_admin, "rev.uno", "Marta Rev", "RevisorClave2026!", PERFIL_REVISOR)
    # No se puede desactivar al último administrador activo
    with pytest.raises(ErrorSeguridad):
        gestor.cambiar_estado_usuario(ses_admin, "admin.ti", False)

    # Cambio de contraseña conserva la clave pública Ed25519
    huella_antes = ses_prep.huella_clave
    pub_antes = ses_prep.clave_publica_b64
    gestor.cambiar_contrasena("prep.uno", "PrepClave2026!", "PrepNueva2026!")
    ses_prep_nueva = gestor.autenticar("prep.uno", "PrepNueva2026!", modo_acceso=PERFIL_PREPARADOR)
    assert ses_prep_nueva.huella_clave == huella_antes
    assert ses_prep_nueva.clave_publica_b64 == pub_antes

    # Bloqueo por 5 intentos fallidos consecutivos
    for _ in range(5):
        with pytest.raises(ErrorSeguridad):
            gestor.autenticar("rev.uno", "Incorrecta2026!", modo_acceso="Auditor")
    # Incluso con la contraseña correcta queda bloqueado
    with pytest.raises(ErrorSeguridad, match="bloqueada"):
        gestor.autenticar("rev.uno", "RevisorClave2026!", modo_acceso="Auditor")

    # Restablecimiento por admin desbloquea y rota par Ed25519
    gestor.restablecer_contrasena_admin(ses_admin, "rev.uno", "RevisorReset2026!")
    ses_rev_nueva = gestor.autenticar("rev.uno", "RevisorReset2026!", modo_acceso="Auditor")
    assert ses_rev_nueva.huella_clave != ""

    # Listado seguro nunca expone secretos
    lista = gestor.listar_usuarios()
    for item in lista:
        assert "contrasena_hash" not in item
        assert "clave_privada_cifrada" not in item

    eventos, integra = gestor.leer_bitacora_accesos()
    assert integra is True
    assert any(ev["evento"] == "cuenta_bloqueada" for ev in eventos)
    assert any(ev["evento"] == "restablecimiento_contrasena_admin" for ev in eventos)


# ---------------------------------------------------------------------------
# 5. Segregación NIA 220, reapertura y ventana NIA 230
# ---------------------------------------------------------------------------


def test_segregacion_nia220_reapertura_y_ventana_nia230(tmp_path):
    mayor = generar(tmp_path / "mayor.csv")
    corrida = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, {}, tmp_path / "corrida_nia")
    ids = [r.id for r in corrida.resultados if not r.omitida]
    for pid in ids:
        registrar_revision_prueba(
            corrida.carpeta, pid, "Aclarado con evidencia", "OK", "Ana Prep", "Preparador", corrida.bitacora
        )

    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "adm",
        "Admin",
        "AdminClave2026!",
        preparador={"usuario": "ana.p", "nombre_completo": "Ana Prep", "contrasena": "PrepClave2026!"},
    )
    ses_adm = gestor.autenticar("adm", "AdminClave2026!", modo_acceso=PERFIL_ADMIN)
    gestor.crear_usuario(ses_adm, "ana.rev", "Ana Prep", "RevisorClave2026!", PERFIL_REVISOR)
    gestor.crear_usuario(ses_adm, "carlos.s", "Carlos Socio", "SocioClave2026!", PERFIL_SOCIO)

    ses_prep = gestor.autenticar("ana.p", "PrepClave2026!")
    ses_rev = gestor.autenticar("ana.rev", "RevisorClave2026!")
    ses_soc = gestor.autenticar("carlos.s", "SocioClave2026!")

    # Admin puro no puede firmar papeles de trabajo
    with pytest.raises(ErrorSeguridad):
        firmar_papel_trabajo(corrida.carpeta, "Preparador", ses_adm.nombre_completo, sesion=ses_adm)

    # Preparador no puede firmar como Revisor
    with pytest.raises(ErrorSeguridad):
        firmar_papel_trabajo(corrida.carpeta, "Revisor", ses_prep.nombre_completo, sesion=ses_prep)

    # Misma persona (mismo usuario con rol dual) intentando auto-revisión con sesión falla
    gestor.crear_usuario(
        ses_adm,
        "dual.usr",
        "Auditor Dual",
        "DualClave2026!",
        PERFIL_PREPARADOR,
        rol_auditoria_extra=PERFIL_REVISOR,
    )
    ses_dual = gestor.autenticar("dual.usr", "DualClave2026!")
    carp_dual = tmp_path / "corrida_dual"
    corrida_dual = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, {}, carp_dual)
    ids_dual = [r.id for r in corrida_dual.resultados if not r.omitida]
    for pid in ids_dual:
        registrar_revision_prueba(
            corrida_dual.carpeta, pid, "Aclarado con evidencia", "OK", ses_dual.nombre_completo, "Preparador", corrida_dual.bitacora
        )
    firmar_papel_trabajo(
        corrida_dual.carpeta, "Preparador", ses_dual.nombre_completo,
        bitacora=corrida_dual.bitacora, pruebas_ejecutadas=ids_dual, exigir_segregacion=True, sesion=ses_dual,
    )
    with pytest.raises(ErrorSeguridad, match="Segregación"):
        firmar_papel_trabajo(
            corrida_dual.carpeta, "Revisor", ses_dual.nombre_completo,
            bitacora=corrida_dual.bitacora, pruebas_ejecutadas=ids_dual, exigir_segregacion=True, sesion=ses_dual,
        )

    # Misma persona sin sesión intentando auto-revisión por nombre normalizado falla con exigir_segregacion=True
    firmar_papel_trabajo(
        corrida.carpeta, "Preparador", "  Ana   López ", bitacora=corrida.bitacora,
        pruebas_ejecutadas=ids, exigir_segregacion=True,
    )
    with pytest.raises(ErrorSeguridad, match="Segregación"):
        firmar_papel_trabajo(
            corrida.carpeta, "Revisor", "ana lópez", bitacora=corrida.bitacora,
            pruebas_ejecutadas=ids, exigir_segregacion=True,
        )

    # Ahora con sesiones distintas (incluso si comparten nombre visible pero distinto usuario)
    carp2 = tmp_path / "corrida_nia2"
    corrida2 = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, {}, carp2)
    ids2 = [r.id for r in corrida2.resultados if not r.omitida]
    for pid in ids2:
        registrar_revision_prueba(
            corrida2.carpeta, pid, "Aclarado con evidencia", "OK", "Ana Prep", "Preparador", corrida2.bitacora
        )

    assert estado_archivo_nia230(corrida2.carpeta)["cerrado"] is False

    firmar_papel_trabajo(
        corrida2.carpeta, "Preparador", ses_prep.nombre_completo,
        bitacora=corrida2.bitacora, pruebas_ejecutadas=ids2, exigir_segregacion=True, sesion=ses_prep,
    )
    firmar_papel_trabajo(
        corrida2.carpeta, "Revisor", ses_rev.nombre_completo,
        bitacora=corrida2.bitacora, pruebas_ejecutadas=ids2, exigir_segregacion=True, sesion=ses_rev,
    )
    firmar_papel_trabajo(
        corrida2.carpeta, "Socio", ses_soc.nombre_completo,
        bitacora=corrida2.bitacora, pruebas_ejecutadas=ids2, exigir_segregacion=True, sesion=ses_soc,
    )
    assert (corrida2.carpeta / "sello.json").exists()
    assert verificar_sello_corrida(corrida2.carpeta, ses_soc.clave_publica_bytes)["valido"] is True

    nia_reciente = estado_archivo_nia230(corrida2.carpeta)
    assert nia_reciente["cerrado"] is True
    assert nia_reciente["dias_transcurridos"] == 0
    assert nia_reciente["dias_restantes"] == 60
    assert nia_reciente["archivado_definitivo"] is False

    # Reapertura bloqueada para Preparador/Revisor y permitida para Socio (elimina sello.json)
    with pytest.raises(ErrorSeguridad):
        reabrir_papel_trabajo(corrida2.carpeta, "Corrección", ses_rev.nombre_completo, bitacora=corrida2.bitacora, sesion=ses_rev)

    reabrir_papel_trabajo(corrida2.carpeta, "Evidencia tardía", ses_soc.nombre_completo, bitacora=corrida2.bitacora, sesion=ses_soc)
    assert not (corrida2.carpeta / "sello.json").exists()
    assert any(
        ev["evento"] == "reapertura_papel_trabajo" and ev["datos"].get("hash_sello_anterior")
        for ev in corrida2.bitacora.leer()
    )
    assert corrida2.bitacora.verificar() is True
    assert estado_archivo_nia230(corrida2.carpeta)["cerrado"] is False

    # Simular cierre hace 65 días para validar archivado_definitivo
    rev_state = cargar_revisiones(corrida2.carpeta)
    rev_state["bloqueado"] = True
    rev_state["fecha_cierre_utc"] = (datetime.now(timezone.utc) - timedelta(days=65)).isoformat(timespec="seconds")
    (corrida2.carpeta / "revisiones.json").write_text(json.dumps(rev_state, indent=2), encoding="utf-8")

    nia_vencida = estado_archivo_nia230(corrida2.carpeta, ventana_dias=60)
    assert nia_vencida["cerrado"] is True
    assert nia_vencida["dias_transcurridos"] >= 65
    assert nia_vencida["dias_restantes"] == 0
    assert nia_vencida["archivado_definitivo"] is True
