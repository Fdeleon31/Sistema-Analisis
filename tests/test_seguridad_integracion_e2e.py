"""Pruebas de integración end-to-end de todas las oleadas de ciberseguridad y login (Fichas 19–23)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from motor.ejecutor import cargar_encargo
from motor.revision import estado_archivo_nia230, firmar_papel_trabajo, registrar_revision_prueba
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar_diario_asientos
from motor.usuarios import (
    PERFIL_ADMIN,
    PERFIL_PREPARADOR,
    PERFIL_REVISOR,
    PERFIL_SOCIO,
    GestorUsuarios,
)

RAIZ = Path(__file__).resolve().parents[1]


def test_integracion_escritorio_rbac_sello_ed25519_y_nia230(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _ = QApplication.instance() or QApplication([])

    from app.escritorio import VentanaCuadra

    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "admin_ti",
        "Carlos Administrador",
        "AdminClave2026!",
        preparador={
            "usuario": "ana_prep",
            "nombre_completo": "Ana Preparadora",
            "contrasena": "PrepClave2026!",
        },
        segregacion_estricta=True,
    )
    ses_admin = gestor.autenticar("admin_ti", "AdminClave2026!", modo_acceso=PERFIL_ADMIN)
    gestor.crear_usuario(ses_admin, "luis_rev", "Luis Revisor", "RevClave2026!", PERFIL_REVISOR)
    gestor.crear_usuario(ses_admin, "sofia_soc", "Sofía Socia", "SocClave2026!", PERFIL_SOCIO)

    ses_prep = gestor.autenticar("ana_prep", "PrepClave2026!", modo_acceso=PERFIL_PREPARADOR)
    ses_rev = gestor.autenticar("luis_rev", "RevClave2026!", modo_acceso=PERFIL_PREPARADOR)
    ses_soc = gestor.autenticar("sofia_soc", "SocClave2026!", modo_acceso=PERFIL_PREPARADOR)

    v_admin = VentanaCuadra(sesion=ses_admin, gestor_usuarios=gestor)
    try:
        assert not v_admin.btn_admin_seg.isHidden()
        assert "Administrador" in v_admin.btn_perfil.text()
        assert "cuadra" not in v_admin.btn_perfil.text().lower()
    finally:
        v_admin.close()

    v_prep = VentanaCuadra(sesion=ses_prep, gestor_usuarios=gestor)
    try:
        assert v_prep.btn_admin_seg.isHidden()
        assert "Preparador" in v_prep.btn_perfil.text()
        assert hasattr(v_prep.vista_portafolio, "btn_seg_corrida")

        mayor, balanza = generar_diario_asientos(tmp_path / "datos", semilla=17)
        encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
        sal = tmp_path / "salidas" / "20261122-112000"
        corrida = ejecutar_encargo("asientos-nia240", {"mayor": mayor, "balanza": balanza}, encargo, sal)

        ids_pruebas = [r.id for r in corrida.resultados if not r.omitida]
        for pid in ids_pruebas:
            registrar_revision_prueba(
                sal,
                pid,
                "Aclarado con evidencia",
                "Verificado en integración E2E.",
                ses_prep.nombre_completo,
                "Preparador",
                bitacora=corrida.bitacora,
            )

        firmar_papel_trabajo(
            sal,
            "Preparador",
            ses_prep.nombre_completo,
            bitacora=corrida.bitacora,
            pruebas_ejecutadas=ids_pruebas,
            exigir_segregacion=True,
            sesion=ses_prep,
        )
        firmar_papel_trabajo(
            sal,
            "Revisor",
            ses_rev.nombre_completo,
            bitacora=corrida.bitacora,
            pruebas_ejecutadas=ids_pruebas,
            exigir_segregacion=True,
            sesion=ses_rev,
        )
        firmar_papel_trabajo(
            sal,
            "Socio",
            ses_soc.nombre_completo,
            bitacora=corrida.bitacora,
            pruebas_ejecutadas=ids_pruebas,
            exigir_segregacion=True,
            sesion=ses_soc,
            ventana_archivo_dias=60,
        )

        assert (sal / "sello.json").exists()
        nia = estado_archivo_nia230(sal, ventana_dias=60)
        assert nia["cerrado"] is True and nia["dias_restantes"] == 60

        v_prep.vista_portafolio._cargar_panel_revision(sal)
        assert "SELLO Ed25519 VÁLIDO" in v_prep.vista_portafolio.kpi_bloqueo.lbl_sub.text()
        assert "NIA 230: 60d rest." in v_prep.vista_portafolio.kpi_bloqueo.lbl_sub.text()
    finally:
        v_prep.close()


def test_cli_cuadra_verificar_y_seguridad_completo(tmp_path, monkeypatch):
    import cuadra
    from motor.cripto import sellar_corrida

    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "adm_cli",
        "Admin CLI",
        "AdminCli2026!",
        preparador={"usuario": "prep_cli", "nombre_completo": "Prep CLI", "contrasena": "PrepCli2026!"},
    )
    ses_prep = gestor.autenticar("prep_cli", "PrepCli2026!", modo_acceso=PERFIL_PREPARADOR)

    mayor, balanza = generar_diario_asientos(tmp_path / "datos_cli", semilla=19)
    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
    sal = tmp_path / "corrida_cli"
    corrida = ejecutar_encargo("asientos-nia240", {"mayor": mayor, "balanza": balanza}, encargo, sal)
    sellar_corrida(
        sal,
        ses_prep.usuario,
        "Preparador",
        ses_prep.semilla_privada_bytes,
        ses_prep.clave_publica_bytes,
        corrida.bitacora,
    )

    # Sin registro de claves no se puede afirmar quién firmó: íntegro pero firmante sin verificar (código 2)
    monkeypatch.setattr(cuadra, "RAIZ", tmp_path / "sin_usuarios")
    assert cuadra.main(["verificar", str(sal)]) == 2
    # Con el registro local de la firma (seguridad/usuarios.json) el firmante queda verificado
    monkeypatch.setattr(cuadra, "RAIZ", tmp_path)
    assert cuadra.main(["verificar", str(sal)]) == 0
    # Registro exportado para el auditor externo
    claves_path = tmp_path / "claves_firma.json"
    assert cuadra.main(["seguridad", "--exportar-claves", str(claves_path)]) == 0
    monkeypatch.setattr(cuadra, "RAIZ", tmp_path / "sin_usuarios")
    assert cuadra.main(["verificar", str(sal), "--claves", str(claves_path)]) == 0
    assert "contrasena_hash" not in claves_path.read_text(encoding="utf-8")
    monkeypatch.setattr(cuadra, "RAIZ", tmp_path)
    assert cuadra.main(["seguridad", "--escanear"]) == 0
    assert cuadra.main(["seguridad", "--entorno"]) == 0

    sbom_path = tmp_path / "sbom.cdx.json"
    lock_path = tmp_path / "requirements.lock"
    assert cuadra.main(["seguridad", "--sbom", str(sbom_path), "--lockfile", str(lock_path)]) == 0
    assert sbom_path.exists() and lock_path.exists()

    diag_path = tmp_path / "diag_soporte.json"
    assert cuadra.main(["seguridad", "--anonimizar", str(sal), "--salida", str(diag_path)]) == 0
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    assert diag["integridad_bitacora_sha256"] is True
    assert "Empresa" not in diag_path.read_text(encoding="utf-8")

    # Bóveda DPAPI con borrado de origen y restauración (DPAPI existe solo en Windows)
    if os.name != "nt":
        return
    carp_dpapi = tmp_path / "boveda_dpapi"
    carp_dpapi.mkdir()
    doc_a = carp_dpapi / "papel.txt"
    doc_a.write_text("contenido reservado de auditoria", encoding="utf-8")
    assert cuadra.main(["seguridad", "--cifrar", str(carp_dpapi), "--dpapi", "--borrar-origen"]) == 0
    assert not doc_a.exists() and (carp_dpapi / "papel.txt.folioenc").exists()
    assert cuadra.main(["seguridad", "--descifrar", str(carp_dpapi)]) == 0
    assert doc_a.read_text(encoding="utf-8") == "contenido reservado de auditoria"

    # Bóveda por variable de entorno FOLIO_BOVEDA_PASS (sin pasar clave en CLI)
    carp_pass = tmp_path / "boveda_pass"
    carp_pass.mkdir()
    doc_b = carp_pass / "cedula_demo.txt"
    doc_b.write_text("cifra confidencial 2025", encoding="utf-8")
    monkeypatch.setenv("FOLIO_BOVEDA_PASS", "ClaveBoveda2026!")
    assert cuadra.main(["seguridad", "--cifrar", str(carp_pass), "--borrar-origen"]) == 0
    assert not doc_b.exists() and (carp_pass / "cedula_demo.txt.folioenc").exists()
    assert cuadra.main(["seguridad", "--descifrar", str(carp_pass)]) == 0
    assert doc_b.read_text(encoding="utf-8") == "cifra confidencial 2025"

    # ACL y simulación de retención
    acl_dir = tmp_path / "acl_dir"
    acl_dir.mkdir()
    assert cuadra.main(["seguridad", "--aplicar-acl", str(acl_dir)]) == 0

    salidas_hist = tmp_path / "salidas_hist"
    (salidas_hist / "20180101-120000").mkdir(parents=True)
    assert cuadra.main(["seguridad", "--purgar-expiradas", str(salidas_hist), "--dias-retencion", "1825"]) == 0
    assert (salidas_hist / "20180101-120000").exists()  # sin --ejecutar-purga solo simula

    # Corrupción detectada tras modificar la cédula
    (sal / "cedula.xlsx").write_bytes(b"corrupto")
    assert cuadra.main(["verificar", str(sal)]) == 1


def test_cuadra_spec_incluye_modulos_ciberseguridad_y_login():
    spec = (RAIZ / "cuadra.spec").read_text(encoding="utf-8")
    for mod in (
        '"motor.seguridad"',
        '"motor.cripto"',
        '"motor.usuarios"',
        '"motor.privacidad"',
        '"app.login_qt"',
        '"herramientas"',
        '"herramientas.seguridad_build"',
        '"docs/seguridad"',
    ):
        assert mod in spec
