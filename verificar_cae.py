"""
verificar_cae.py

Lee un CSV de resultados (como tu resultados_YYYYMMDD_HHMMSS.csv),
consulta a AFIP/ARCA por cada comprobante usando getVoucherInfo y
verifica que:
- exista información (ResultGet)
- el CAE coincida (si está en el CSV)
- el ImpTotal coincida (tolerancia por redondeo)
- el CAE no esté vencido (según CAEFchVto)

Genera un CSV de salida con el análisis.

Uso:
  python verificar_cae.py resultados_20260211_123000.csv

Requiere .env con:
  PRODUCTION=true|false
  CUIT=...
  ACCESS_TOKEN=...
  PUNTO_VENTA=...
  CERT_PATH=... (solo si PRODUCTION=true)
  KEY_PATH=...  (solo si PRODUCTION=true)
"""

import csv
import os
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from afip import Afip


# -------------------- Helpers --------------------

def d(value: str) -> Decimal:
    """Parse decimal safely."""
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_yyyymmdd(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def decimals_close(a: Decimal, b: Decimal, tol: Decimal = Decimal("0.01")) -> bool:
    return (a - b).copy_abs() <= tol


# -------------------- Main logic --------------------

def load_env():
    load_dotenv()
    production = os.environ.get("PRODUCTION", "false").lower() == "true"

    try:
        cuit = int(os.environ["CUIT"])
        access_token = os.environ["ACCESS_TOKEN"]
        pto_vta = int(os.environ["PUNTO_VENTA"])
    except KeyError as e:
        print(f"ERROR: falta variable de entorno requerida: {e}")
        sys.exit(1)

    cert_path = os.environ.get("CERT_PATH", "")
    key_path = os.environ.get("KEY_PATH", "")
    csv_separator = os.environ.get("CSV_SEPARATOR", ",")

    afip_options = {"CUIT": cuit, "access_token": access_token, "production": production}

    if production:
        if not cert_path or not os.path.exists(cert_path):
            print("ERROR: CERT_PATH requerido y debe existir en modo produccion")
            sys.exit(1)
        if not key_path or not os.path.exists(key_path):
            print("ERROR: KEY_PATH requerido y debe existir en modo produccion")
            sys.exit(1)

        afip_options["cert"] = open(cert_path, "r", encoding="utf-8").read()
        afip_options["key"] = open(key_path, "r", encoding="utf-8").read()

    return Afip(afip_options), production, cuit, pto_vta, csv_separator


def read_resultados_csv(path: str, separator: str = ","):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=separator)
        rows = list(reader)

    required = {"doc_nro", "imp_total", "cbte_nro", "cae", "cae_vto", "resultado"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV no tiene columnas requeridas: {sorted(missing)}")

    return rows


def analyze_row(afip: Afip, row: dict, pto_vta: int, cbte_tipo: int):
    """
    Devuelve dict con:
      - ws_ok (bool)
      - cae_match, total_match, cae_not_expired (bool/None)
      - ws_cae, ws_total, ws_cae_vto, ws_cbte_fch
      - status (string)
      - error (string)
    """
    cbte_nro_raw = (row.get("cbte_nro") or "").strip()
    if not cbte_nro_raw:
        return {
            "ws_ok": False,
            "status": "SKIP_NO_CBTE_NRO",
            "error": "Fila sin cbte_nro",
        }

    try:
        cbte_nro = int(cbte_nro_raw)
    except ValueError:
        return {
            "ws_ok": False,
            "status": "SKIP_BAD_CBTE_NRO",
            "error": f"cbte_nro invalido: {cbte_nro_raw!r}",
        }

    csv_cae = (row.get("cae") or "").strip()
    csv_total = d(row.get("imp_total") or "0")
    csv_cae_vto = parse_yyyymmdd(row.get("cae_vto") or "")

    try:
        info = afip.ElectronicBilling.getVoucherInfo(cbte_nro, pto_vta, cbte_tipo)
    except Exception as e:
        return {
            "ws_ok": False,
            "status": "WS_ERROR",
            "error": str(e),
        }

    # AfipSDK usualmente devuelve ResultGet para getVoucherInfo
    rg = (info or {}).get("ResultGet") or {}
    if not rg:
        return {
            "ws_ok": False,
            "status": "NOT_FOUND",
            "error": "getVoucherInfo no devolvio ResultGet",
        }

    ws_cae = (rg.get("CodAutorizacion") or "").strip()
    ws_total = d(rg.get("ImpTotal") or "0")
    ws_cbte_fch = (rg.get("CbteFch") or "").strip()

    # CAEFchVto no siempre viene en ResultGet; si no viene, usamos el del CSV
    ws_cae_vto = parse_yyyymmdd(rg.get("FchVto") or rg.get("CAEFchVto") or "") or csv_cae_vto

    cae_match = None
    if csv_cae and ws_cae:
        cae_match = (csv_cae == ws_cae)

    total_match = decimals_close(csv_total, ws_total)

    cae_not_expired = None
    if ws_cae_vto:
        cae_not_expired = (ws_cae_vto >= date.today())

    # Status composition
    problems = []
    if cae_match is False:
        problems.append("CAE_MISMATCH")
    if total_match is False:
        problems.append("TOTAL_MISMATCH")
    if cae_not_expired is False:
        problems.append("CAE_EXPIRED")

    status = "OK" if not problems else "WARN_" + "_".join(problems)

    return {
        "ws_ok": True,
        "status": status,
        "error": "",
        "ws_cae": ws_cae,
        "ws_total": f"{ws_total:.2f}",
        "ws_cae_vto": ws_cae_vto.strftime("%Y%m%d") if ws_cae_vto else "",
        "ws_cbte_fch": ws_cbte_fch,
        "cae_match": "" if cae_match is None else str(cae_match),
        "total_match": str(total_match),
        "cae_not_expired": "" if cae_not_expired is None else str(cae_not_expired),
    }


def write_output_csv(rows_out: list[dict], path_out: str, separator: str = ","):
    fieldnames = [
        # input context
        "doc_nro",
        "imp_total",
        "fecha",
        "cbte_nro",
        "cae",
        "cae_vto",
        "resultado",
        # analysis
        "ws_ok",
        "status",
        "error",
        "ws_cbte_fch",
        "ws_total",
        "ws_cae",
        "ws_cae_vto",
        "cae_match",
        "total_match",
        "cae_not_expired",
    ]
    with open(path_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=separator)
        writer.writeheader()
        for r in rows_out:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def main():
    if len(sys.argv) < 2:
        print("Uso: python verificar_cae.py resultados_YYYYMMDD_HHMMSS.csv")
        sys.exit(1)

    input_csv = sys.argv[1]
    if not os.path.exists(input_csv):
        print(f"ERROR: no existe el archivo: {input_csv}")
        sys.exit(1)

    # Ajustá si querés verificar otro tipo de comprobante
    CBTE_TIPO = 11  # Factura C

    afip, production, cuit, pto_vta, csv_separator = load_env()
    print(f"Entorno: {'PRODUCCION' if production else 'HOMOLOGACION'} | CUIT: {cuit} | PtoVta: {pto_vta} | CbteTipo: {CBTE_TIPO}")

    try:
        rows = read_resultados_csv(input_csv, csv_separator)
    except Exception as e:
        print(f"ERROR leyendo CSV: {e}")
        sys.exit(1)

    out = []
    ok_count = warn_count = err_count = 0

    for i, row in enumerate(rows, start=1):
        # Si tu CSV tiene filas con "resultado" ERROR, igual intentamos si hay cbte_nro
        analysis = analyze_row(afip, row, pto_vta, CBTE_TIPO)

        merged = dict(row)
        merged.update({
            "ws_ok": analysis.get("ws_ok", False),
            "status": analysis.get("status", ""),
            "error": analysis.get("error", ""),
            "ws_cbte_fch": analysis.get("ws_cbte_fch", ""),
            "ws_total": analysis.get("ws_total", ""),
            "ws_cae": analysis.get("ws_cae", ""),
            "ws_cae_vto": analysis.get("ws_cae_vto", ""),
            "cae_match": analysis.get("cae_match", ""),
            "total_match": analysis.get("total_match", ""),
            "cae_not_expired": analysis.get("cae_not_expired", ""),
        })
        out.append(merged)

        status = analysis.get("status", "")
        if status == "OK":
            ok_count += 1
        elif status.startswith("WARN"):
            warn_count += 1
        else:
            err_count += 1

        print(f"[{i}/{len(rows)}] cbte_nro={row.get('cbte_nro','')} -> {status}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = f"verificacion_{ts}.csv"
    write_output_csv(out, out_csv, csv_separator)

    print("\nResumen:")
    print(f"  OK:   {ok_count}")
    print(f"  WARN: {warn_count}")
    print(f"  ERR:  {err_count}")
    print(f"\nArchivo generado: {out_csv}")


if __name__ == "__main__":
    main()
